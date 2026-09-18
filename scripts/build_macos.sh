#!/bin/zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
identity="${CSI_SIGNING_IDENTITY:--}"
notary_profile="${CSI_NOTARY_PROFILE:-}"
entitlements="$root/desktop/src-tauri/entitlements.plist"

if [[ "$identity" != "-" ]] && ! security find-identity -v -p codesigning | grep -Fq -- "$identity"; then
  echo "找不到代码签名身份：$identity" >&2
  echo "请先在钥匙串安装 Developer ID Application 证书。" >&2
  exit 1
fi

sign_bundle() {
  local target="$1"
  local -a arguments=(--force --sign "$identity")
  if [[ "$identity" != "-" ]]; then
    arguments+=(--options runtime --timestamp --entitlements "$entitlements")
  fi
  while IFS= read -r -d '' binary; do
    if file -b "$binary" | grep -q 'Mach-O'; then
      codesign "${arguments[@]}" "$binary"
    fi
  done < <(find "$target/Contents" -type f -print0)
  codesign "${arguments[@]}" "$target"
}

"$root/scripts/build_sidecar.sh"
"$root/scripts/assemble_runtime.sh"
cd "$root/desktop"
PATH="$HOME/.cargo/bin:$PATH" npm ci
PATH="$HOME/.cargo/bin:$PATH" npm run tauri -- build --bundles app
app="$root/desktop/src-tauri/target/release/bundle/macos/Creator Source Importer Beta.app"
dmg="$root/desktop/src-tauri/target/release/bundle/dmg/Creator-Source-Importer-v0.7.1-arm64.dmg"
mkdir -p "${dmg:h}"
"$root/scripts/fix_tauri_sidecar_links.py" "$app"
sign_bundle "$app"
"$root/scripts/verify_bundle.sh" "$app"
hdiutil create -ov -volname "Creator Source Importer Beta" -srcfolder "$app" -format UDZO "$dmg"
if [[ -n "$notary_profile" ]]; then
  xcrun notarytool submit "$dmg" --keychain-profile "$notary_profile" --wait
  xcrun stapler staple "$dmg"
  xcrun stapler validate "$dmg"
  spctl --assess --type execute --verbose=4 "$app"
elif [[ "$identity" != "-" ]]; then
  echo "已使用 Developer ID 签名，但尚未公证。设置 CSI_NOTARY_PROFILE 后会自动提交并附加公证票据。" >&2
fi
(cd "${dmg:h}" && shasum -a 256 "${dmg:t}") > "$dmg.sha256"
