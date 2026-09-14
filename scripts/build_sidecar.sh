#!/bin/zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
venv="${CSI_BUILD_VENV:-$root/build/runtime-venv}"
out="$root/build/sidecar-dist"
cd "$root"

"$venv/bin/pyinstaller" --clean --noconfirm --onedir \
  --name creator-source-importer-sidecar \
  --distpath "$out" --workpath "$root/build/pyinstaller-work" \
  --specpath "$root/build" \
  --add-data "$root/index.html:." \
  --hidden-import transcribe_worker \
  --hidden-import xhs_login \
  --hidden-import yt_dlp \
  --hidden-import playwright.sync_api \
  --hidden-import mlx_whisper \
  --collect-data yt_dlp_ejs \
  --collect-data playwright \
  --collect-data mlx_whisper \
  --copy-metadata yt-dlp \
  --copy-metadata yt-dlp-ejs \
  --copy-metadata mlx-whisper \
  --copy-metadata mlx-metal \
  --collect-submodules yt_dlp \
  --collect-submodules scipy._external.array_api_compat.numpy \
  --collect-submodules scipy._external.array_api_compat.common \
  --collect-all mlx \
  --exclude-module mutagen \
  app.py
