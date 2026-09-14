#!/bin/zsh
set -euo pipefail

app="$1"
resources="$app/Contents/Resources/resources"
test -x "$resources/sidecar/creator-source-importer-sidecar"
test -x "$resources/runtime/bin/ffmpeg"
test -x "$resources/runtime/bin/ffprobe"
test -x "$resources/runtime/bin/deno"
"$resources/runtime/bin/ffmpeg" -version >/dev/null
"$resources/runtime/bin/ffprobe" -version >/dev/null
"$resources/runtime/bin/deno" --version >/dev/null
if find "$app" -type f -print0 | xargs -0 strings 2>/dev/null | grep -qE '/Users/[^/]+|Cookie|xsec_token='; then
  echo "Bundle privacy scan found a forbidden string." >&2
  exit 1
fi
codesign --verify --deep --strict "$app"
echo "Bundle structure and bundled executables verified."

