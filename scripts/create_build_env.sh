#!/bin/zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
command -v uv >/dev/null || {
  echo "Developer dependency missing: uv" >&2
  exit 1
}
uv venv --python 3.12 "$root/build/runtime-venv"
uv pip install --python "$root/build/runtime-venv/bin/python" -r "$root/build-requirements.lock"

