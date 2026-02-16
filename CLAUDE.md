# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local Translate is a privacy-first, offline desktop translation app for macOS using TranslateGemma models with optional Qwen3 TTS. It combines a Tauri 2 desktop shell (Rust) with a Svelte 5 frontend and a Python ML backend connected via PyTauri.

## Development Commands

```bash
# Install dependencies
pnpm install
uv sync

# Run the app in development mode (frontend + Tauri + Python backend)
pnpm tauri dev

# Build frontend only
pnpm build

# Full release build
pnpm tauri build

# Standalone macOS build (embeds Python runtime)
bash scripts/macos/download-py.sh   # one-time: downloads python-build-standalone
bash scripts/macos/build.sh
```

Python requires version >=3.10, <3.13 (3.13 is incompatible with mlx-audio). The `.cargo/config.toml` sets `PYO3_PYTHON` to `.venv/bin/python3`.

## Architecture

### Three-layer stack

1. **Frontend** (`src/`): Svelte 5 + TypeScript. `App.svelte` owns all state (languages, models, translation text, TTS status) using Svelte 5 runes (`$state`, `$derived`). Components communicate via props/events, not a store.

2. **Rust shell** (`src-tauri/src/`): Thin Tauri 2 layer. `main.rs` initializes the embedded Python interpreter and sets up `PYTHONPATH` and `LOCAL_TRANSLATE_PYTHON` env vars (differently for dev vs release). `lib.rs` exports the PyO3 module and wires up the Tauri builder. No business logic lives here.

3. **Python backend** (`src-tauri/src-python/local_translate/`): All ML logic. `commands.py` defines 14 IPC command handlers invoked from the frontend via PyTauri channels. `model_manager.py` and `tts_manager.py` are thread-locked singletons managing model lifecycle. `__main__.py` creates an asyncio event loop via anyio and builds the Tauri app with PyTauri integration.

### Frontend → Python IPC

`src/lib/api.ts` provides typed TypeScript bindings that call Python command handlers in `commands.py` through PyTauri's JavaScript Channel mechanism. All Pydantic models inherit from `CamelModel` which auto-serializes snake_case to camelCase for JS compatibility. Async handlers wrap sync/CPU-bound operations with `anyio.to_thread.run_sync()`.

For progress-reporting operations (model downloads), JavaScript `Channel<DownloadProgress>` objects are passed to Python, which calls `channel.send_model()` for real-time progress updates.

### Subprocess isolation

MLX inference (`mlx_worker.py`) and TTS generation (`tts_worker.py`) run in separate subprocesses to avoid Metal GPU context conflicts with the WebView. Communication uses JSON-lines over stdin/stdout. Workers redirect stdout to /dev/null on startup (saving real stdout first) to prevent import log noise from corrupting the JSON protocol.

The Python executable path for subprocess spawning is resolved via `_python.py`: first checks `LOCAL_TRANSLATE_PYTHON` env var (set by `main.rs`), then `sys.executable`, then `.venv/bin/python3`.

### Model storage

Models are cached in `~/.cache/local-translate/models/{model_id}` (translation) and `~/.cache/local-translate/tts-models/default` (TTS), downloaded from Hugging Face on demand. A `.download_complete` marker file prevents re-downloading.

## Key Patterns

- **Singleton managers**: `ModelManager` and `TtsManager` use thread-locked singletons (`threading.Lock` + `_instance`) for global state across async command handlers.
- **Debounced translation**: 500ms debounce on source text/language changes before triggering translation.
- **Progressive model loading**: First launch auto-downloads the default 4B model with progress UI. Models transition through: not_downloaded → downloading → downloaded → loading → ready (can error at any step).
- **localStorage persistence**: Favorite languages (`lt-favorite-langs`) and recent languages (`lt-recent-langs`, last 5) stored client-side.
- **Worker JSON-lines protocol**: Each command is one line of JSON in, one line JSON out. Responses use `{"status": "ok", "result": ...}`, `{"status": "error", "message": ...}`, or `{"status": "fatal", "message": ...}` for crashes.

## Supported Models

- TranslateGemma 4B (4-bit) — default, ~2.2GB download, 4GB RAM
- TranslateGemma 4B (8-bit) — ~4.1GB download, 6GB RAM
- TranslateGemma 27B (4-bit) — ~15.2GB download, 18GB RAM
- Qwen3-TTS-12Hz-0.6B (TTS, 10 languages: zh, en, ja, ko, de, fr, ru, pt, es, it)

## Type Checking

- **TypeScript**: tsconfig.json with strict mode, noUnusedLocals, noUnusedParameters enabled
- **Python**: pyright configured in root pyproject.toml (excludes node_modules, __pycache__, dist, pyembed, target)

## Release Build Notes

The standalone macOS build (`scripts/macos/build.sh`) sets `PYTAURI_STANDALONE=1`, enables the `pytauri/standalone` Cargo feature, and embeds `pyembed/python/` into the app bundle's Resources directory with custom RUSTFLAGS for rpath linking. The `tauri.bundle.json` configures macOS-specific bundling (dmg, app).
