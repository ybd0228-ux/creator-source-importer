# 签名与 Apple 公证

0.7.1 的公开 DMG 已使用 Developer ID 签名、Hardened Runtime 和 Apple 公证。构建脚本支持重复执行这一流程，以生成后续版本的可公开分发安装包。

正式 Public Beta 前需要：

1. 在 Apple Developer 的 Certificates, Identifiers & Profiles 页面创建并下载 **Developer ID Application** 证书。不要选择 Apple Development、Apple Distribution 或 Mac App Distribution。
2. 双击下载的 `.cer` 文件，将证书和对应私钥安装到本机登录钥匙串。执行 `security find-identity -v -p codesigning` 时应能看到 `Developer ID Application: ...`。
3. 创建一个用于 Apple notary service 的 app-specific password，并用 `xcrun notarytool store-credentials "Creator Source Importer Notary" --apple-id "你的 Apple ID" --team-id "你的 Team ID"` 保存到钥匙串。命令会要求输入 app-specific password；不要把它写入项目文件或聊天记录。
4. 以如下方式构建：

   ```zsh
   CSI_SIGNING_IDENTITY='Developer ID Application: 你的名称 (TEAMID)' \
   CSI_NOTARY_PROFILE='Creator Source Importer Notary' \
   ./scripts/build_macos.sh
   ```

   脚本会先签名 App 内的每个 Mach-O 文件和主 App，再创建 DMG、提交公证、附加票据并验证票据。
5. 使用 `codesign --verify --deep --strict`、`spctl --assess --type execute` 和 `stapler validate` 验证最终产物。

构建脚本默认仍使用 ad-hoc 签名，供个人本地开发使用。只有明确提供 `CSI_SIGNING_IDENTITY` 时才使用正式身份；同时提供 `CSI_NOTARY_PROFILE` 才会提交 Apple 公证。

不要用关闭 Gatekeeper 或要求普通用户右键打开作为公开发布方案。
