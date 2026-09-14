# Creator Source Importer 0.7.0 Beta

Creator Source Importer 把用户主动提交的公开视频或本地媒体在 Mac 上转成可读的 Markdown。媒体转录在本机完成，输出可以保存到 Obsidian 的任意目录或普通文件夹。

本机保留两种入口：

- **Web UI（Developer/Personal Mode）**：个人日常默认入口，由 `launch.py` 启动。
- **Desktop App**：用于 DMG 公开分发和独立环境测试。

两个入口都调用同一套 Python Core，并共用 `~/Library/Application Support/Creator Source Importer` 下的设置、任务历史和模型清单。来源、转录和导出逻辑只维护一份。

## 当前能力

- 正式支持：油管、B站、本地 MP3/M4A/WAV/MP4/MOV。
- 实验支持：小某书 Experimental，需要系统已安装 Chrome，并使用用户自己的登录状态。
- 批量队列中单条失败不会中断后续任务，可查看详情、重试和取消。
- 按“平台/创作者”建目录，以 `(platform, source_id)` 去重。
- Markdown 包含通用 Frontmatter、语义分段转录、段落时间范围和可选原始 JSON。
- 不自动总结，也不修改或移动已有 Markdown。

## 安装与首次使用

本地开发构建位于 `desktop/src-tauri/target/release/bundle/`。当前 DMG 没有 Developer ID 签名或 Apple 公证，只用于本机开发验证，暂不适合作为普通用户公开下载。

首次启动：

1. 选择资料保存目录。Obsidian 目录与普通文件夹采用相同方式处理。
2. 选择“标准（推荐）”或“高质量”。
3. 下载并校验本地语音识别模型。

之后粘贴链接或添加本地文件，再开始任务。App 自带 Python 运行时、FFmpeg、ffprobe、Deno、yt-dlp 和 MLX 相关组件；模型在首次使用时单独下载。

开发机日常启动 Web UI：

```zsh
build/runtime-venv/bin/python launch.py
```

本机的 “Creator Source Importer.app” 无窗口启动器执行的就是这条 Web UI 路径。

## 使用边界

仅处理用户有权访问并主动提交的内容。不要用它绕过付费、DRM、地区、年龄、验证码或其他访问控制。小某书接口可能随平台页面变化失效。

## 数据与隐私

默认没有遥测或统计。音视频、转录、目标目录和任务历史不会上传到本项目的服务器；读取公开来源和下载模型时会按功能需要访问相应网站。详见 [PRIVACY.md](docs/PRIVACY.md)。

## 从源码构建

构建面向 Apple Silicon macOS 13.5+，需要开发机安装 Rust、Node 和 Python 构建环境：

```zsh
./scripts/build_macos.sh
```

这些是开发构建依赖；最终用户不需要安装它们。FFmpeg 必须使用本项目记录的 LGPL 配置自行构建，不可复制 Homebrew 的 GPL 构建。完整清单见 [DEPENDENCIES.md](docs/DEPENDENCIES.md)。
