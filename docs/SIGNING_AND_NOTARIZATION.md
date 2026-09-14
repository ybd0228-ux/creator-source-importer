# 签名与 Apple 公证

0.7.0 当前只能生成 unsigned/ad-hoc development build，因为构建机没有 Developer ID Application 身份与 notarization credential。它不能满足普通用户双击即开的发布目标。

正式 Public Beta 前需要：

1. 加入 Apple Developer Program，并在 Keychain 安装有效的 Developer ID Application 证书。
2. 为 Tauri 配置 hardened runtime、签名 identity 与必要 entitlement。
3. 对 App 内所有 Mach-O、主 App 和 DMG 按从内到外顺序签名。
4. 使用 `notarytool submit --wait` 提交 DMG。
5. 使用 `stapler staple` 附加票据。
6. 用 `codesign --verify --deep --strict`、`spctl --assess --type execute` 和 `stapler validate` 验证。

不要用关闭 Gatekeeper 或要求普通用户右键打开作为公开发布方案。

