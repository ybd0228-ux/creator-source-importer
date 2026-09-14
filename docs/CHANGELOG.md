# Changelog

## 0.7.0 Beta

- 增加 Tauri 桌面壳与冻结的 Python sidecar。
- 保留 Web UI 作为 Developer/Personal Mode；Web UI 与 Desktop 共用 Core、设置目录、任务历史和模型清单。
- 内置独立 Python 运行组件、自行构建的 LGPL FFmpeg/ffprobe 与 Deno。
- 增加首次配置、模型安装/校验/删除与磁盘空间检查。
- 正式支持油管、B站和本地媒体；小某书标为 Experimental。
- 增加持久化任务队列、失败隔离、重试、取消和重启恢复状态。
- 统一 SourceRecord 与 `(platform, source_id)` 去重，保留旧来源字段。
- 输出语义分段、段落时间范围与可选 Raw JSON，不生成 AI 总结。
- 增加旧配置复制迁移、迁移前备份及重新配置回退备份。
- 移除公共默认值中的个人路径，并隔离公共版运行状态。
