"""Subprocess worker that runs TTS inference in its own process.

Same JSON-lines-over-stdin/stdout pattern as mlx_worker.py, but for
text-to-speech using mlx-audio with Qwen3-TTS.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import traceback

# Save the real stdout for JSON-line communication before any library imports
# can pollute it with progress bars, warnings, etc.
_json_out = os.fdopen(os.dup(sys.stdout.fileno()), "w")


def _respond(obj: dict) -> None:
    _json_out.write(json.dumps(obj) + "\n")
    _json_out.flush()


def main() -> None:
    # Redirect stdout → /dev/null so library prints don't corrupt the JSON protocol.
    sys.stdout = open(os.devnull, "w")

    try:
        import numpy as np
        from mlx_audio.tts.utils import load_model
    except Exception:
        # If imports fail, report over JSON so the parent sees the error
        # instead of a mysterious empty-readline crash.
        _respond({"status": "fatal", "message": traceback.format_exc()})
        return

    model = None

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            _respond({"status": "error", "message": f"Invalid JSON: {e}"})
            continue

        cmd = req.get("cmd")

        if cmd == "load":
            try:
                model = load_model(req["model_path"])
                _respond({"status": "ok"})
            except Exception as e:
                _respond({"status": "error", "message": str(e)})

        elif cmd == "synthesize":
            if model is None:
                _respond({"status": "error", "message": "No model loaded"})
                continue
            try:
                text = req["text"]
                language = req.get("language", "auto")
                voice = req.get("voice")

                kwargs: dict = {
                    "text": text,
                    "language": language,
                    "temperature": 0.2,
                }
                if voice:
                    kwargs["voice"] = voice

                # model.generate() returns a generator of GenerationResult
                results = list(model.generate(**kwargs))

                if not results:
                    _respond({"status": "error", "message": "No audio generated"})
                    continue

                # Concatenate all audio segments
                audio_arrays = [np.array(r.audio) for r in results]
                audio_np = np.concatenate(audio_arrays) if len(audio_arrays) > 1 else audio_arrays[0]
                sample_rate = results[0].sample_rate

                # Convert to WAV bytes
                import soundfile as sf

                buf = io.BytesIO()
                sf.write(buf, audio_np, sample_rate, format="WAV")
                wav_bytes = buf.getvalue()

                wav_b64 = base64.b64encode(wav_bytes).decode("ascii")
                _respond({"status": "ok", "audio": wav_b64})
            except Exception as e:
                _respond({"status": "error", "message": str(e)})

        elif cmd == "quit":
            break

        else:
            _respond({"status": "error", "message": f"Unknown command: {cmd}"})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Last resort — catch crashes in main() itself
        _respond({"status": "fatal", "message": traceback.format_exc()})
