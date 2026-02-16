from __future__ import annotations

import json
import subprocess
import threading
from enum import Enum
from pathlib import Path
from typing import Callable

from local_translate._python import find_python

AVAILABLE_MODELS: dict[str, dict[str, str | int | float]] = {
    "4b": {
        "name": "TranslateGemma 4B (4-bit)",
        "repo_id": "mlx-community/translategemma-4b-it-4bit",
        "ram_gb": 4,
        "description": "Default model, fast and lightweight (~2.2GB download)",
    },
    "4b-8bit": {
        "name": "TranslateGemma 4B (8-bit)",
        "repo_id": "mlx-community/translategemma-4b-it-8bit",
        "ram_gb": 6,
        "description": "Higher precision 4B variant (~4.1GB download)",
    },
    "27b": {
        "name": "TranslateGemma 27B (4-bit)",
        "repo_id": "mlx-community/translategemma-27b-it-4bit",
        "ram_gb": 18,
        "description": "Best quality, requires significant RAM (~15.2GB download)",
    },
}


class ModelStatus(str, Enum):
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


class ModelManager:
    _instance: ModelManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> ModelManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._current_model_id: str | None = None
        self._worker: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._cmd_lock = threading.Lock()
        self._status: dict[str, ModelStatus] = {}
        self._error: dict[str, str] = {}
        self._model_paths: dict[str, str] = {}

        from huggingface_hub import snapshot_download

        for model_id, info in AVAILABLE_MODELS.items():
            try:
                path = snapshot_download(
                    str(info["repo_id"]), local_files_only=True
                )
                self._model_paths[model_id] = path
                self._status[model_id] = ModelStatus.DOWNLOADED
            except Exception:
                self._status[model_id] = ModelStatus.NOT_DOWNLOADED

    def get_status(self, model_id: str) -> ModelStatus:
        return self._status.get(model_id, ModelStatus.NOT_DOWNLOADED)

    def get_error(self, model_id: str) -> str | None:
        return self._error.get(model_id)

    def get_current_model_id(self) -> str | None:
        return self._current_model_id

    def _send_worker_cmd(self, cmd: dict) -> dict:
        """Send a JSON command to the worker subprocess and read the response."""
        with self._cmd_lock:
            worker = self._worker
            if worker is None or worker.stdin is None or worker.stdout is None:
                raise RuntimeError("Worker process is not running")
            worker.stdin.write(json.dumps(cmd) + "\n")
            worker.stdin.flush()
            resp_line = worker.stdout.readline()
            if not resp_line:
                stderr = ""
                try:
                    worker.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()
                if worker.stderr:
                    stderr = worker.stderr.read()
                raise RuntimeError(f"Worker process exited unexpectedly: {stderr}")
            return json.loads(resp_line)

    def _stop_worker(self) -> None:
        """Stop the current worker subprocess."""
        if self._worker is not None:
            try:
                self._worker.stdin.write(json.dumps({"cmd": "quit"}) + "\n")  # type: ignore[union-attr]
                self._worker.stdin.flush()  # type: ignore[union-attr]
                self._worker.wait(timeout=5)
            except Exception:
                self._worker.kill()
            self._worker = None

    def download_model(
        self,
        model_id: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> None:
        if model_id not in AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_id}")

        self._status[model_id] = ModelStatus.DOWNLOADING
        self._error.pop(model_id, None)
        model_info = AVAILABLE_MODELS[model_id]
        repo_id = str(model_info["repo_id"])

        try:
            from huggingface_hub import HfApi, hf_hub_download, snapshot_download

            if progress_callback:
                progress_callback(0.0, "Fetching model info...")

            api = HfApi()
            info = api.repo_info(repo_id)
            files = [
                (s.rfilename, s.size)
                for s in (info.siblings or [])
            ]
            total_files = len(files)
            total_size = sum(s for _, s in files if s)
            downloaded_size = 0

            for i, (filename, size) in enumerate(files):
                hf_hub_download(repo_id=repo_id, filename=filename)
                if progress_callback:
                    if total_size > 0 and size:
                        downloaded_size += size
                        progress = min(downloaded_size / total_size, 0.99)
                        downloaded_gb = downloaded_size / 1e9
                        total_gb = total_size / 1e9
                        progress_callback(
                            progress,
                            f"Downloading... {downloaded_gb:.1f}/{total_gb:.1f} GB",
                        )
                    else:
                        progress = min((i + 1) / total_files, 0.99)
                        progress_callback(
                            progress,
                            f"Downloading file {i + 1}/{total_files}...",
                        )

            model_path = snapshot_download(repo_id, local_files_only=True)
            self._model_paths[model_id] = model_path

            if progress_callback:
                progress_callback(1.0, "Download complete")

            self._status[model_id] = ModelStatus.DOWNLOADED
        except Exception as e:
            self._status[model_id] = ModelStatus.ERROR
            self._error[model_id] = str(e)
            raise

    def load_model(self, model_id: str) -> None:
        if model_id not in AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_id}")

        if self.get_status(model_id) not in (ModelStatus.DOWNLOADED, ModelStatus.READY):
            raise RuntimeError(f"Model {model_id} is not downloaded yet")

        self._status[model_id] = ModelStatus.LOADING

        try:
            model_dir = self._model_paths[model_id]

            # Stop existing worker if switching models
            if self._current_model_id and self._current_model_id != model_id:
                old_id = self._current_model_id
                self._stop_worker()
                self._current_model_id = None
                self._status[old_id] = ModelStatus.DOWNLOADED

            # Spawn a new worker subprocess with its own Metal context.
            # Run the script directly by path (not -m) to avoid importing
            # the package __init__.py which requires the pytauri native module.
            python = find_python()
            worker_script = str(Path(__file__).resolve().parent / "mlx_worker.py")
            self._worker = subprocess.Popen(
                [python, worker_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            resp = self._send_worker_cmd({"cmd": "load", "model_path": model_dir})
            if resp.get("status") != "ok":
                raise RuntimeError(resp.get("message", "Worker failed to load model"))

            self._current_model_id = model_id
            self._status[model_id] = ModelStatus.READY
        except Exception as e:
            self._stop_worker()
            self._status[model_id] = ModelStatus.ERROR
            self._error[model_id] = str(e)
            raise

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if self._worker is None or self._current_model_id is None:
            raise RuntimeError("No model loaded")

        from local_translate.languages import SUPPORTED_LANGUAGES

        src_name = SUPPORTED_LANGUAGES.get(source_lang, source_lang)
        tgt_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)

        prompt = (
            f"<bos><start_of_turn>user\n"
            f"You are a professional {src_name} ({source_lang}) to "
            f"{tgt_name} ({target_lang}) translator. Your goal is to "
            f"accurately convey the meaning and nuances of the original "
            f"{src_name} text while adhering to {tgt_name} grammar, "
            f"vocabulary, and cultural sensitivities.\n"
            f"Produce only the {tgt_name} translation, without any "
            f"additional explanations or commentary. Please translate the "
            f"following {src_name} text into {tgt_name}:\n\n\n"
            f"{text.strip()}<end_of_turn>\n"
            f"<start_of_turn>model\n"
        )

        resp = self._send_worker_cmd({"cmd": "translate", "prompt": prompt})
        if resp.get("status") != "ok":
            raise RuntimeError(resp.get("message", "Translation failed"))

        return resp["result"].strip()
