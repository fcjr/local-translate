from __future__ import annotations

import json
import queue
import subprocess
import threading
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from local_translate._python import find_python

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
        self._cmd_lock = threading.Lock()
        self._resp_queue: queue.Queue[str | None] = queue.Queue()
        self._status: TtsStatus = TtsStatus.NOT_DOWNLOADED
        self._error: str | None = None
        self._model_path: str | None = None

        from huggingface_hub import snapshot_download

        try:
            self._model_path = snapshot_download(
                DEFAULT_MODEL_REPO, local_files_only=True
            )
            self._status = TtsStatus.DOWNLOADED
        except Exception:
            pass

    def get_status(self) -> TtsStatus:
        return self._status

    def get_error(self) -> str | None:
        return self._error

    def is_language_supported(self, lang_code: str) -> bool:
        return lang_code in TTS_LANGUAGE_MAP

    def _kill_worker(self) -> None:
        """Kill the worker and reset status so it can be restarted."""
        w = self._worker
        if w is not None:
            self._worker = None
            try:
                w.kill()
                w.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            for pipe in (w.stdin, w.stdout, w.stderr):
                if pipe:
                    try:
                        pipe.close()
                    except OSError:
                        pass
        if self._status in (TtsStatus.READY, TtsStatus.LOADING):
            self._status = TtsStatus.DOWNLOADED

    def _start_reader(self) -> None:
        """Spawn a daemon thread that continuously reads worker stdout.

        The thread discards non-JSON lines (C/Metal library noise) and
        enqueues valid JSON lines for ``_send_worker_cmd`` to consume.
        This keeps the pipe drained so the worker never blocks on writes.

        A fresh queue is created each time so old reader threads (still
        draining a dead worker's pipe) cannot poison the new worker.
        """
        self._resp_queue = queue.Queue()
        worker = self._worker
        q = self._resp_queue

        def _reader() -> None:
            assert worker is not None and worker.stdout is not None
            try:
                for raw_line in worker.stdout:
                    line = raw_line.rstrip("\n")
                    if not line:
                        continue
                    # C/Metal libraries may write to fd 1 without a
                    # trailing newline, so their output gets prepended
                    # to the next JSON line.  Find the first '{' and
                    # try to parse from there.
                    start = line.find("{")
                    if start < 0:
                        continue  # pure non-JSON noise
                    try:
                        obj = json.loads(line[start:])
                        q.put(json.dumps(obj))
                    except json.JSONDecodeError:
                        pass  # still not valid JSON — discard
            except (ValueError, OSError):
                pass  # pipe closed
            finally:
                q.put(None)  # EOF sentinel

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

    def _send_worker_cmd(self, cmd: dict, timeout: float = 120) -> dict:
        with self._cmd_lock:
            worker = self._worker
            if worker is None or worker.stdin is None:
                raise RuntimeError("TTS worker process is not running")
            try:
                worker.stdin.write(json.dumps(cmd) + "\n")
                worker.stdin.flush()
            except BrokenPipeError:
                self._kill_worker()
                raise RuntimeError(
                    "TTS worker process crashed before receiving command"
                )
            try:
                resp_line = self._resp_queue.get(timeout=timeout)
            except queue.Empty:
                self._kill_worker()
                raise RuntimeError(
                    f"TTS worker did not respond within {int(timeout)}s"
                )
            if resp_line is None:
                self._kill_worker()
                raise RuntimeError("TTS worker process exited unexpectedly")
            resp = json.loads(resp_line)
            if resp.get("status") == "fatal":
                self._kill_worker()
                raise RuntimeError(resp.get("message", "TTS worker fatal error"))
            return resp

    def _stop_worker(self) -> None:
        self._kill_worker()

    def download_model(
        self,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> None:
        self._status = TtsStatus.DOWNLOADING
        self._error = None

        try:
            from huggingface_hub import HfApi, hf_hub_download, snapshot_download

            if progress_callback:
                progress_callback(0.0, "Fetching TTS model info...")

            api = HfApi()
            info = api.repo_info(DEFAULT_MODEL_REPO, timeout=30, files_metadata=True)
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
                                f"Downloading TTS... {downloaded_gb:.1f}/{total_gb:.1f} GB",
                            )
                        return result

                for filename, size in files:
                    hf_hub_download(
                        repo_id=DEFAULT_MODEL_REPO,
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
                            f"Downloading TTS... {downloaded_gb:.1f}/{total_gb:.1f} GB",
                        )
            else:
                for filename, _ in files:
                    hf_hub_download(repo_id=DEFAULT_MODEL_REPO, filename=filename)

            self._model_path = snapshot_download(
                DEFAULT_MODEL_REPO, local_files_only=True
            )

            if progress_callback:
                progress_callback(1.0, "TTS model download complete")

            self._status = TtsStatus.DOWNLOADED
        except Exception as e:
            self._status = TtsStatus.ERROR
            self._error = str(e)
            raise

    def load_model(self) -> None:
        if self._status not in (TtsStatus.DOWNLOADED, TtsStatus.READY, TtsStatus.ERROR):
            raise RuntimeError("TTS model is not downloaded yet")

        self._status = TtsStatus.LOADING

        try:
            if not self._model_path:
                raise RuntimeError("TTS model path not found")
            model_dir = self._model_path

            self._stop_worker()

            python = find_python()
            worker_script = str(Path(__file__).resolve().parent / "tts_worker.py")
            self._worker = subprocess.Popen(
                [python, worker_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._start_reader()

            resp = self._send_worker_cmd(
                {"cmd": "load", "model_path": model_dir}, timeout=300
            )
            if resp.get("status") != "ok":
                raise RuntimeError(resp.get("message", "TTS worker failed to load model"))

            self._status = TtsStatus.READY
        except Exception as e:
            self._stop_worker()
            self._status = TtsStatus.ERROR
            self._error = str(e)
            raise

    def synthesize(self, text: str, language: str) -> str:
        """Synthesize speech from text. Returns base64-encoded WAV string.

        The worker is restarted after every synthesis because
        ``model.generate()`` in mlx-audio hangs on the second invocation
        within the same process (likely a Metal/MLX state issue).
        """
        # (Re-)start a fresh worker for every call.
        self.load_model()

        tts_lang = TTS_LANGUAGE_MAP.get(language, "auto")
        voice = TTS_VOICE_MAP.get(language)

        cmd: dict = {
            "cmd": "synthesize",
            "text": text,
            "language": tts_lang,
        }
        if voice:
            cmd["voice"] = voice

        resp = self._send_worker_cmd(cmd, timeout=120)
        if resp.get("status") != "ok":
            raise RuntimeError(resp.get("message", "TTS synthesis failed"))

        return resp["audio"]
