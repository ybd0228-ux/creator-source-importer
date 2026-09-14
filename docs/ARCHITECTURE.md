# 架构

Web UI 与 Tauri Desktop App 是同一 Core 的两个入口。Web UI 用开发运行环境执行 `app.py`；Desktop App 从资源目录运行同一 `app.py` 构建出的冻结 sidecar，并把 FFmpeg、ffprobe、Deno 路径显式传入。两者都使用 `~/Library/Application Support/Creator Source Importer`。

sidecar 只监听回环地址，生成随机会话 token；WebView 的每个写请求都需要该 token。Desktop 启动时会验证共享目录中的活动 session；若同版本 Web UI 已运行，Desktop 复用该本地服务，避免维护两份运行状态。

处理路径：

```text
Desktop UI
  -> TaskManager（串行、持久化、失败隔离）
  -> SourceAdapter（油管 / B站 / 小某书 Experimental / 本地媒体）
  -> 本地媒体临时文件
  -> MLX Whisper Transcriber
  -> SourceRecord
  -> Markdown Exporter + 可选 Raw JSON
```

来源最终统一为 `SourceRecord`。去重键是 `(platform, source_id)`；旧字段 `video_id`、`bvid`、`note_id`继续写入对应来源，保证旧资料可识别。本地文件用内容 SHA-256 作为 source_id。

设置、任务历史和模型清单保存在同一个 Application Support 目录。输出根目录完全由用户选择。模型独立于 App 与输出目录管理，因此升级 App 不会把模型写入 Obsidian。

小某书适配器与其他来源隔离。Chrome 缺失、登录失效或页面变化只会使该任务失败。
