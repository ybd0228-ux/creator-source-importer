# 产品化交付状态

1. **当前版本号**：0.7.0 Beta。
2. **已完成**：个人路径移除、设置迁移、统一数据结构和边界、四类来源、Local Media、任务队列、模型管理、Tauri、独立 sidecar、LGPL FFmpeg、Deno、App 与 DMG。
3. **未完成**：Developer ID 签名、公证、干净机外部验收、高质量模型实测、公开 GitHub Release。
4. **项目目录**：公共开发副本 `Creator_Source_Importer_Public`，与个人版分离。
5. **新 App**：日常 Web UI 启动器仍为本机 `Creator Source Importer.app`；公开测试入口为 `desktop/src-tauri/target/release/bundle/macos/Creator Source Importer Beta.app`。
6. **启动**：本人默认双击 Web UI 启动器；开发 DMG App 用于独立环境测试。当前 DMG 未公证。
7. **旧配置迁移**：已实际执行复制迁移；迁移前备份存在，旧配置未删除，个人资料根目录继续沿用。
8. **现有 Obsidian**：没有批量修改、移动或删除；本轮集成只写临时目录。
9. **油管**：指定真实链接完整通过。
10. **B站**：指定真实链接完整通过。
11. **小某书 Experimental**：指定真实链接完整通过；仍依赖 Chrome、用户登录及平台页面稳定性。
12. **Local Media**：MP3、MP4 和打包 App 内 WAV 的真实 MLX 转录通过；扩展名验证覆盖 M4A/WAV/MOV。
13. **DMG**：已生成开发 DMG，并完成哈希、挂载与 App 校验。
14. **完全独立性**：运行组件已内置；本机隔离 PATH 实测通过。干净 Mac 尚未验收，因此不能宣称发布级完全独立。
15. **用户依赖**：设计上不要求安装 Python、Homebrew、Node、FFmpeg、yt-dlp、MLX 或 Deno；首次需要下载模型。
16. **安装包体积**：DMG 289 MB，App 文件系统占用约 703 MB。
17. **模型大小**：标准模型当前实测占用约 1.5 GB，界面估算 1.7 GB；高质量界面估算 3.2 GB，未实测。
18. **第三方许可**：FFmpeg 使用 LGPL 构建；直接依赖许可已记录；mutagen 已排除。正式发布前仍需完整文本归集和复核。
19. **当前 blockers**：Apple 签名/公证凭据、干净 Apple Silicon Mac 验收、完整许可证归集。
20. **GitHub Release 尚缺**：签名公证后的最终 DMG、干净机结果、最终许可证包、仓库页面与所有者发布确认。
21. **Apple Developer 尚缺**：有效 Developer ID Application、notarytool 凭据、hardened runtime 签名与 notarization/staple 验证。
22. **回滚**：继续运行原个人版 App 即可；公共版使用独立状态目录。需要撤销迁移时可删除公共版设置或从公共状态目录的迁移备份恢复，个人版和旧配置不受影响。

## 实际架构与原建议的差异

核心功能集中在既有 `importer.py`，本轮通过 Protocol 和统一 record 建立模块边界，没有为产品化重写稳定适配器。Phase C 中任务队列、错误详情、重试、取消、模型管理等必要项目已提前纳入 0.7，因为它们直接影响桌面 App 可用性。

Tauri 自带的 DMG 美化脚本在本机构建 700 MB 级 App 时失败，改用 macOS `hdiutil` 生成可挂载的标准 UDZO DMG；安装内容相同，缺少定制背景和 Applications 拖放快捷方式。正式发布可以在签名阶段再补安装盘外观。

Web UI 是本人的默认 Developer/Personal Mode，Desktop 是同一 Core 的冻结发行物。两者共享 `~/Library/Application Support/Creator Source Importer`，不分叉业务逻辑。个人版快照继续保留作回滚证据。
