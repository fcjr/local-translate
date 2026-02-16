from __future__ import annotations

import json
import subprocess
import threading
from enum import Enum
from pathlib import Path
from typing import Callable

CACHE_DIR = Path.home() / ".cache" / "local-translate" / "tts-models"

DEFAULT_MODEL_REPO = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"

# Qwen3-TTS supports these languages (full English names).
# Map ISO codes to the names the model expects.
TTS_LANGUAGE_MAP: dict[str, str] = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}

# Default voice per language
TTS_VOICE_MAP: dict[str, str] = {
    "zh": "Vivian",
    "en": "Chelsie",
}


def _find_venv_python() -> str:
    """Find the venv Python executable for spawning the TTS worker subprocess."""
    pkg_dir = Path(__file__).resolve().parent
    project_root = pkg_dir.parent.parent.parent
    venv_python = project_root / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    raise FileNotFoundError(
        f"Could not find venv Python at {venv_python}. Run `uv sync` first."
    )


class TtsStatus(str, Enum):
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


class TtsManager:
    _instance: TtsManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> TtsManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._worker: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._status: TtsStatus = TtsStatus.NOT_DOWNLOADED
        self._error: str | None = None

        model_dir = CACHE_DIR / "default"
        if model_dir.exists() and any(model_dir.iterdir()):
            self._status = TtsStatus.DOWNLOADED

    def get_status(self) -> TtsStatus:
        return self._status

    def get_error(self) -> str | None:
        return self._error

    def is_language_supported(self, lang_code: str) -> bool:
        return lang_code in TTS_LANGUAGE_MAP

    def _send_worker_cmd(self, cmd: dict) -> dict:
        worker = self._worker
        if worker is None or worker.stdin is None or worker.stdout is None:
            raise RuntimeError("TTS worker process is not running")
        try:
            worker.stdin.write(json.dumps(cmd) + "\n")
            worker.stdin.flush()
        except BrokenPipeError:
            # Worker already exited — try to read any fatal message it left
            resp_line = worker.stdout.readline() if worker.stdout else ""
            if resp_line:
                resp = json.loads(resp_line)
                raise RuntimeError(resp.get("message", "TTS worker crashed"))
            raise RuntimeError("TTS worker process crashed before receiving command")
        resp_line = worker.stdout.readline()
        if not resp_line:
            raise RuntimeError("TTS worker process exited unexpectedly")
        resp = json.loads(resp_line)
        if resp.get("status") == "fatal":
            raise RuntimeError(resp.get("message", "TTS worker fatal error"))
        return resp

    def _stop_worker(self) -> None:
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
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> None:
        self._status = TtsStatus.DOWNLOADING
        self._error = None
        local_dir = CACHE_DIR / "default"

        try:
            from huggingface_hub import snapshot_download

            if progress_callback:
                progress_callback(0.0, "Starting TTS model download...")

            snapshot_download(
                repo_id=DEFAULT_MODEL_REPO,
                local_dir=str(local_dir),
                local_dir_use_symlinks=False,
            )

            if progress_callback:
                progress_callback(1.0, "TTS model download complete")

            self._status = TtsStatus.DOWNLOADED
        except Exception as e:
            self._status = TtsStatus.ERROR
            self._error = str(e)
            raise

    def load_model(self) -> None:
        if self._status not in (TtsStatus.DOWNLOADED, TtsStatus.READY):
            raise RuntimeError("TTS model is not downloaded yet")

        self._status = TtsStatus.LOADING

        try:
            model_dir = str(CACHE_DIR / "default")

            self._stop_worker()

            python = _find_venv_python()
            worker_script = str(Path(__file__).resolve().parent / "tts_worker.py")
            self._worker = subprocess.Popen(
                [python, worker_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )

            resp = self._send_worker_cmd({"cmd": "load", "model_path": model_dir})
            if resp.get("status") != "ok":
                raise RuntimeError(resp.get("message", "TTS worker failed to load model"))

            self._status = TtsStatus.READY
        except Exception as e:
            self._stop_worker()
            self._status = TtsStatus.ERROR
            self._error = str(e)
            raise

    def synthesize(self, text: str, language: str) -> str:
        """Synthesize speech from text. Returns base64-encoded WAV string."""
        if self._worker is None or self._status != TtsStatus.READY:
            raise RuntimeError("TTS model is not loaded")

        tts_lang = TTS_LANGUAGE_MAP.get(language, "auto")
        voice = TTS_VOICE_MAP.get(language)

        cmd: dict = {
            "cmd": "synthesize",
            "text": text,
            "language": tts_lang,
        }
        if voice:
            cmd["voice"] = voice

        resp = self._send_worker_cmd(cmd)
        if resp.get("status") != "ok":
            raise RuntimeError(resp.get("message", "TTS synthesis failed"))

        return resp["audio"]
