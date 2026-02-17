from __future__ import annotations

import json
import subprocess
import threading
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from local_translate._python import find_python

def _safetensors_complete(model_dir: Path) -> bool:
    """Check that all expected safetensors weight files are present.

    Supports three layouts:
    1. Index file (``model.safetensors.index.json``) — verify every listed shard.
    2. Sharded without index (``model-XXXXX-of-NNNNN.safetensors``) — parse the
       total from the filename pattern and verify all shards exist.
    3. Single-file model — just needs at least one safetensors file.
    """
    import re

    index_file = model_dir / "model.safetensors.index.json"
    if index_file.exists():
        with open(index_file) as f:
            index = json.load(f)
        shard_files = set(index.get("weight_map", {}).values())
        return all((model_dir / name).exists() for name in shard_files)

    # Check for sharded naming pattern: model-00001-of-00003.safetensors
    shard_files = sorted(model_dir.glob("model-*-of-*.safetensors"))
    if shard_files:
        # Parse total shard count from any filename
        m = re.search(r"-of-(\d+)\.safetensors$", shard_files[0].name)
        if m:
            expected = int(m.group(1))
            return len(shard_files) == expected

    # Single-file model — just needs at least one safetensors file
    return any(model_dir.glob("*.safetensors"))


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
                # Verify the snapshot actually contains all model weights.
                # An interrupted download can leave metadata or only some
                # shard files, causing mlx_lm.load() to fail.
                if not _safetensors_complete(Path(path)):
                    self._status[model_id] = ModelStatus.NOT_DOWNLOADED
                    continue
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

    def delete_model(self, model_id: str) -> None:
        if model_id not in AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_id}")

        if model_id == self._current_model_id:
            raise RuntimeError("Cannot delete the currently loaded model")

        if self.get_status(model_id) == ModelStatus.NOT_DOWNLOADED:
            raise RuntimeError(f"Model {model_id} is not downloaded")

        repo_id = str(AVAILABLE_MODELS[model_id]["repo_id"])

        from huggingface_hub import scan_cache_dir

        cache_info = scan_cache_dir()
        revisions_to_delete = []
        for repo_info in cache_info.repos:
            if repo_info.repo_id == repo_id:
                for revision in repo_info.revisions:
                    revisions_to_delete.append(revision.commit_hash)

        if revisions_to_delete:
            strategy = cache_info.delete_revisions(*revisions_to_delete)
            strategy.execute()

        self._status[model_id] = ModelStatus.NOT_DOWNLOADED
        self._model_paths.pop(model_id, None)
        self._error.pop(model_id, None)

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
            info = api.repo_info(repo_id, timeout=30, files_metadata=True)
            files = [
                (s.rfilename, s.size)
                for s in (info.siblings or [])
            ]
            total_size = sum(s for _, s in files if s)

            if progress_callback and total_size > 0:
                import time

                from tqdm.auto import tqdm as _tqdm_base

                completed_bytes = [0]

                # Track bytes ourselves instead of relying on tqdm's
                # self.n, which stays at 0 when tqdm is internally
                # disabled (e.g. no tty in a bundled .app).
                file_bytes = [0]

                class _ByteTqdm(_tqdm_base):  # type: ignore[type-arg]
                    """Reports byte-level download progress via callback."""

                    _last_report = 0.0

                    def __init__(self, *args: Any, **kwargs: Any) -> None:
                        kwargs.pop("name", None)
                        kwargs["disable"] = False
                        file_bytes[0] = 0
                        super().__init__(*args, **kwargs)

                    def display(self, *args: object, **kwargs: object) -> None:
                        pass

                    def update(self, n: float | None = 1) -> bool | None:
                        result = super().update(n)
                        if n:
                            file_bytes[0] += int(n)
                        now = time.monotonic()
                        if now - _ByteTqdm._last_report >= 0.1:
                            _ByteTqdm._last_report = now
                            current = completed_bytes[0] + file_bytes[0]
                            progress = min(current / total_size, 0.99)
                            downloaded_gb = current / 1e9
                            total_gb = total_size / 1e9
                            progress_callback(  # type: ignore[misc]
                                progress,
                                f"Downloading... {downloaded_gb:.1f}/{total_gb:.1f} GB",
                            )
                        return result

                for filename, size in files:
                    hf_hub_download(
                        repo_id=repo_id,
                        filename=filename,
                        tqdm_class=_ByteTqdm,
                    )
                    if size:
                        completed_bytes[0] += size
                        progress = min(completed_bytes[0] / total_size, 0.99)
                        downloaded_gb = completed_bytes[0] / 1e9
                        total_gb = total_size / 1e9
                        progress_callback(
                            progress,
                            f"Downloading... {downloaded_gb:.1f}/{total_gb:.1f} GB",
                        )
            else:
                for filename, _ in files:
                    hf_hub_download(repo_id=repo_id, filename=filename)

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

            # Guard against corrupt/incomplete cache missing weight files.
            if not _safetensors_complete(Path(model_dir)):
                self._model_paths.pop(model_id, None)
                self._status[model_id] = ModelStatus.NOT_DOWNLOADED
                raise RuntimeError(
                    f"Model {model_id} cache is incomplete (missing safetensors shards). "
                    "Please re-download the model."
                )

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
