#!/bin/bash

set -e

cd "$(dirname "$0")/../.."

PROJECT_NAME="local-translate"
PYLIB_DIR="$(realpath src-tauri/pyembed/python/lib)"

export PYTAURI_STANDALONE="1"
export PYO3_PYTHON="$(realpath src-tauri/pyembed/python/bin/python3)"
export RUSTFLAGS=" \
    -C link-arg=-Wl,-rpath,@executable_path/../Resources/lib \
    -L $PYLIB_DIR"

uv pip install \
    --exact \
    --compile-bytecode \
    --python="$PYO3_PYTHON" \
    --reinstall-package="$PROJECT_NAME" \
    ./src-tauri

# Remove packages not needed at runtime — these are transitive deps
# of librosa/transformers that our Qwen3-TTS code path never imports
uv pip uninstall --python="$PYO3_PYTHON" \
    scipy scikit-learn numba llvmlite joblib \
    pillow pip

# Remove tkinter/tcl/tk (not needed for headless Python backend)
rm -rf src-tauri/pyembed/python/lib/libtcl* \
       src-tauri/pyembed/python/lib/libtk* \
       src-tauri/pyembed/python/lib/tcl* \
       src-tauri/pyembed/python/lib/tk* \
       src-tauri/pyembed/python/lib/python*/lib-dynload/_tkinter*

# Clean up test dirs and bytecode caches
find src-tauri/pyembed -type d \( -name "test" -o -name "tests" -o -name "testing" -o -name "__pycache__" \) -exec rm -rf {} +

pnpm tauri build --config="src-tauri/tauri.bundle.json" -- --profile bundle-release
