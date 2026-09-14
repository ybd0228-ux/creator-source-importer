#!/bin/zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
resources="$root/desktop/src-tauri/resources"
mkdir -p "$resources/sidecar" "$resources/runtime/bin" "$resources/runtime/lib" "$resources/runtime/licenses"
rsync -a --delete "$root/build/sidecar-dist/creator-source-importer-sidecar/" "$resources/sidecar/"
cp "$root/build/ffmpeg-runtime/bin/ffmpeg" "$root/build/ffmpeg-runtime/bin/ffprobe" "$resources/runtime/bin/"
cp -a "$root"/build/ffmpeg-runtime/lib/*.dylib "$resources/runtime/lib/"
cp "$root/build/deno-runtime/bin/deno" "$resources/runtime/bin/"
cp "$root"/build/runtime-licenses/* "$resources/runtime/licenses/"
cp "$root/index.html" "$root/desktop/frontend/index.html"
chmod +x "$resources/sidecar/creator-source-importer-sidecar" "$resources/runtime/bin/"*
