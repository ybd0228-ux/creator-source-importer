# 运行依赖与再分发记录

本文件记录 0.7.0 Beta 的直接运行组件。Python 运行依赖的精确版本见根目录 `runtime-requirements.lock`，构建工具见 `build-requirements.lock`，Rust 间接依赖见 `desktop/src-tauri/Cargo.lock`。

| 组件 | 版本 | 来源 | 许可 | 构建/校验 |
|---|---:|---|---|---|
| Python Runtime | 3.12 | python.org/构建环境 | PSF | PyInstaller onedir |
| PyInstaller bootloader | 6.16.0 | PyPI | GPL-2.0-or-later + Bootloader Exception | 仅用于冻结运行组件 |
| yt-dlp | 2026.8.19 | PyPI | Unlicense | 固定版本 |
| yt-dlp-ejs | 0.8.0 | PyPI | Unlicense/MIT/ISC | 固定版本 |
| MLX | 0.32.2 | PyPI | MIT | arm64 |
| MLX Metal | 0.32.2 | PyPI | MIT | arm64 |
| mlx-whisper | 0.4.3 | PyPI | MIT | 模型按需下载 |
| Playwright Python | 1.62.0 | PyPI | Apache-2.0 | 不内置浏览器 |
| FFmpeg/ffprobe | 9.0.1 | ffmpeg.org source tar | LGPL-2.1-or-later | `--disable-autodetect --enable-securetransport --enable-shared --disable-static --disable-doc --disable-debug --disable-ffplay` |
| Deno | 2.9.6 arm64 | 官方 GitHub Release | MIT | SHA-256 校验 |
| Tauri | 2.x | crates.io/npm | Apache-2.0/MIT | Rust Cargo.lock 固定解析结果 |

FFmpeg 源码归档 SHA-256：

`cf38e0e28c7e5605942c4a77755349b0145804a397af37eb1fb4c77cb237f635`

Deno arm64 ZIP SHA-256：

`213a2f304f04d3c9cb5220669afad138f60a5aab1fe80962abdeb8f35807a472`

模型不是 DMG 的一部分。标准模型当前实测磁盘占用约 1.5 GB；下载界面在开始前显示估算并检查可用空间。

许可证结论：当前直接运行组件存在可再分发路径。FFmpeg 使用独立 LGPL 构建，未采用 Homebrew GPL 构建；GPL 许可的 mutagen 已从冻结 sidecar 排除。公开分发时仍需随 Release 提供本构建对应的 FFmpeg 源码归档、许可证文本和第三方通知。
