# 0.7.0 Beta 测试报告

测试日期：2026-09-14
测试机：Apple Silicon，macOS 26.5.1，16 GB RAM

所有测试输出均写入 `/tmp` 或项目忽略的 `test-results/`，没有写入正式 Obsidian。

## 自动化回归

`python -m unittest`：51 项通过，0 失败。

覆盖旧配置复制迁移与备份、全新配置、普通/中文/空格/iCloud 风格路径、单链接、10 项批量中 1 项失败继续、四类来源适配、本地 MP3/MP4、内容哈希去重、旧 ID 兼容、网络/来源失败、模型缺失、磁盘不足、写入原子性、符号链接防护、取消、重启与异常任务恢复。

## 真实集成

| 场景 | 结果 | 证据 |
|---|---|---|
| 油管 | 通过 | 指定公开链接下载 15 MB 音频，转录 86.39 秒，生成日期标题 Markdown 与 Raw JSON |
| B站 | 通过 | 指定 BV 链接下载 16 MB 音频，转录 131.65 秒，生成 Markdown 与 Raw JSON |
| 小某书 Experimental | 通过 | 指定笔记使用用户已有登录 Profile，下载、30.40 秒转录并导出；Profile 未复制 |
| 本地 MP3 | 通过 | synthetic 音频在源码运行环境完成真实 MLX 转录 |
| 本地 MP4 | 通过 | synthetic 视频在源码运行环境完成真实 MLX 转录 |
| 打包 sidecar | 通过 | PyInstaller sidecar 对 synthetic 中文 WAV 完成真实 MLX 转录 |
| 完整 App | 通过 | `PATH=/usr/bin:/bin`、隔离状态目录下，由 Tauri 启动内置 sidecar，使用内置 FFmpeg，5.35 秒完成本地 WAV 转录并导出 |
| DMG | 通过（开发包） | 生成、SHA-256、只读挂载、App 结构和 ad-hoc codesign 校验通过；直接从挂载盘用内置 sidecar/FFmpeg 完成真实 MLX 转录 |
| Web UI / Desktop 共用 | 通过 | Web UI 以共享目录启动 0.7 Core；Desktop 检测并复用同版本回环 session，设置、历史和模型清单来自同一目录 |

实际输出抽查确认：Frontmatter 有 `platform/source_id` 和兼容旧 ID；标题有发布日期；正文有语义段落及段落时间范围；Raw JSON 可由相对链接访问；没有 AI 总结。

## 依赖与隔离

- App 内含冻结的 Python 3.12 sidecar、yt-dlp、MLX、FFmpeg/ffprobe 和 Deno。
- 完整 App 测试没有调用 Homebrew 或用户 Python。
- FFmpeg 9.0.1 由源码以 LGPL 配置构建，运行依赖已改成 App 相对路径；版本信息不含开发机用户路径。
- 公共资源扫描没有发现个人主目录、真实 token、Cookie 或 Profile 内容。
- 最终 DMG 为 289 MB，SHA-256 为 `27205e6f112beb4bb54466fcf02ce6e773fb1cff61395ca25e6d4a92185e0e5c`；App 约 703 MB。
- 个人版配置 SHA-256 与开发前快照一致；个人项目和已有 Obsidian 修改时间未因这些测试变化。

## 未完成的发布验收

- 没有第二台“无源码、Python、Homebrew”的干净 Apple Silicon Mac，因而干净机安装、首次模型下载和油管端到端仍待外部验收。
- 构建机没有 Developer ID Application 与 notarization credential。当前仅有 ad-hoc 签名；Gatekeeper 公共下载体验不合格。
- 高质量模型没有实际下载与转录。
- 小某书依赖平台页面和用户登录，当前成功不保证长期稳定。
- 第三方通知已有直接依赖与主要间接依赖清单；正式公开前还需归集每个随包文件的完整许可证文本并复核。
