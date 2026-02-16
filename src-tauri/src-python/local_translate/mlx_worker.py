"""Subprocess worker that runs MLX inference in its own process.

This avoids Metal command buffer conflicts between MLX and Tauri's WebView,
which both use Metal in the main process. Communication is via JSON lines
over stdin/stdout.
"""

from __future__ import annotations

import json
import os
import sys

# Save the real stdout for JSON-line communication before any library imports
# can pollute it with progress bars, warnings, etc.
_json_out = os.fdopen(os.dup(sys.stdout.fileno()), "w")


def main() -> None:
    # Redirect stdout → /dev/null so library prints don't corrupt the JSON protocol.
    _devnull = open(os.devnull, "w")
    sys.stdout = _devnull

    import mlx_lm

    model = None
    tokenizer = None

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
                model, tokenizer = mlx_lm.load(req["model_path"])
                # Add <end_of_turn> to EOS tokens so generation stops
                # after the model's response (only <eos> is set by default).
                end_of_turn_id = tokenizer.encode(
                    "<end_of_turn>", add_special_tokens=False
                )
                if end_of_turn_id:
                    tokenizer.eos_token_ids.add(end_of_turn_id[0])
                _respond({"status": "ok"})
            except Exception as e:
                _respond({"status": "error", "message": str(e)})

        elif cmd == "translate":
            if model is None or tokenizer is None:
                _respond({"status": "error", "message": "No model loaded"})
                continue
            try:
                result = mlx_lm.generate(
                    model, tokenizer, prompt=req["prompt"], max_tokens=2048
                )
                _respond({"status": "ok", "result": result})
            except Exception as e:
                _respond({"status": "error", "message": str(e)})

        elif cmd == "quit":
            break

        else:
            _respond({"status": "error", "message": f"Unknown command: {cmd}"})


def _respond(obj: dict) -> None:
    _json_out.write(json.dumps(obj) + "\n")
    _json_out.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        _respond({"status": "fatal", "message": traceback.format_exc()})
