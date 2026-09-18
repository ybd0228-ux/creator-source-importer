# GitHub Release Draft — 0.7.1 Beta

状态：已完成 Developer ID 签名、Apple 公证和票据附加；待创建首个 GitHub Pre-release。

## 变化

Creator Source Importer 可从桌面 App 完成链接或本地媒体导入、本地 MLX 转录与 Markdown 导出。正式支持油管、B站和本地媒体，小某书作为 Experimental。模型下载优先使用魔搭，失败时回退至 Hugging Face；标准与高质量模型均有固定文件大小和 SHA-256，并支持中断续传。

## 系统要求

- Apple Silicon Mac
- macOS 13.5+
- 模型与来源下载需要网络
- 小某书 Experimental 需要系统 Chrome 及用户自己的有效登录

## 附件清单

- `Creator-Source-Importer-v0.7.1-arm64.dmg`
- `Creator-Source-Importer-v0.7.1-arm64.dmg.sha256`
- `FFmpeg-9.0.1-source.tar.xz`
- README、CHANGELOG、PRIVACY、THIRD_PARTY_NOTICES

## 发布门槛

- Developer ID 签名、公证、票据附加和系统信任校验均已通过。
- 首次公开发布前，需在独立 Apple Silicon 环境完成安装与导入验收。
- Release 随附 FFmpeg 对应源码归档、校验值和第三方声明。
