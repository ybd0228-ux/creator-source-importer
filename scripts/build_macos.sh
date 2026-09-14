#!/bin/zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/build_sidecar.sh"
"$root/scripts/assemble_runtime.sh"
cd "$root/desktop"
PATH="$HOME/.cargo/bin:$PATH" npm ci
PATH="$HOME/.cargo/bin:$PATH" npm run tauri -- build --bundles app
app="$root/desktop/src-tauri/target/release/bundle/macos/Creator Source Importer Beta.app"
dmg="$root/desktop/src-tauri/target/release/bundle/dmg/Creator-Source-Importer-v0.7.0-arm64.dmg"
mkdir -p "${dmg:h}"
"$root/scripts/fix_tauri_sidecar_links.py" "$app"
codesign --force --deep --sign - "$app"
"$root/scripts/verify_bundle.sh" "$app"
hdiutil create -ov -volname "Creator Source Importer Beta" -srcfolder "$app" -format UDZO "$dmg"
(cd "${dmg:h}" && shasum -a 256 "${dmg:t}") > "$dmg.sha256"
