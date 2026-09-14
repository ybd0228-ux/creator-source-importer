# Creator Source Importer v0.7.0 Beta 开发报告

> 用途：交给 Chat 模式评审当前产品状态，并帮助决定下一阶段工作。  
> 报告日期：2026-09-14  
> 当前状态：本地开发与独立安装包验证完成，尚未公开发布。

## 一、项目目标

Creator Source Importer 是一个本地优先的创作者素材导入工具。用户主动提交公开视频链接或本地音视频后，工具完成：

~~~text
读取来源
→ 获取媒体
→ 本地 MLX Whisper 转录
→ 生成 Markdown 与可选 Raw JSON
→ 保存到用户选择的 Obsidian 目录或普通文件夹
~~~

当前面向 Apple Silicon Mac 和 macOS 13.5+。正式支持油管、B站和本地媒体；小某书作为 Experimental。当前不包含云端转录、AI 自动总结、账号系统、付费系统、Windows、Intel Mac 或移动端。

## 二、本轮开发结果

项目已从绑定个人电脑路径和开发环境的个人工具，改造成 0.7.0 Beta：

- 删除公共默认配置中的个人路径。
- 增加首次设置、保存目录选择、标准/高质量模式和模型管理。
- 统一 SourceAdapter、Transcriber、Exporter、TaskManager 和 Settings 边界。
- 建立统一 SourceRecord，用 (platform, source_id) 去重。
- 保留旧笔记中的 video_id、bvid、note_id 等兼容字段。
- 增加本地 MP3、M4A、WAV、MP4、MOV。
- 增加持久化串行任务队列、单条失败隔离、取消、重试和重启恢复。
- 输出带日期的文件名、语义段落、段落时间范围、原始 transcript 和 Raw JSON。
- 不自动生成 AI 总结，不批量修改已有 Markdown。
- 增加 Tauri Desktop App、冻结的 Python sidecar、独立 FFmpeg/ffprobe 和 Deno。
- 生成 Apple Silicon DMG 和本地 GitHub Release 草稿。

## 三、两个入口与唯一 Core

当前保留两个入口：

1. **Web UI（Developer/Personal Mode）**：作为本人日常默认入口，通过本地启动器运行项目中的 app.py。
2. **Tauri Desktop App**：作为公开 DMG 分发和独立环境测试入口，运行由同一份 app.py 冻结出来的 sidecar。

两者共用同一套来源、转录、导出和任务逻辑，也共用同一个用户设置目录：

~~~text
~/Library/Application Support/Creator Source Importer
~~~

设置、任务历史和模型清单都在该目录。两种入口也使用同一个回环 HTTP 协议和 token 安全边界。

如果 Web UI 已运行，Desktop 会验证并复用同版本 session，不会额外启动第二套 Core。关闭 Desktop 后，原 Web UI 服务仍继续运行。

后续核心功能必须先修改公共 Python Core，再同时由 Web UI 和 Desktop 使用；不分别维护两套业务实现。

## 四、输出与数据设计

新用户选择一个资料根目录后，工具自动使用：

~~~text
资料根目录/
├── 油管/
├── B站/
├── 小某书/
└── 本地媒体/
~~~

网络来源继续按创作者建立子目录。Markdown 使用通用 Frontmatter，并保留来源兼容字段。Raw JSON 默认放在笔记旁的 _raw 目录，通过相对链接引用。

临时媒体默认在转录并成功导出后删除；本地原始文件始终保留。下载、转录或写入失败时保留工作目录，以便排查和恢复。

个人旧配置通过“复制、备份、可回退”的方式迁移。旧个人项目、旧配置、已有笔记和完整快照均未删除。

## 五、当前界面能力

首次启动流程为：

1. 选择资料保存文件夹，或沿用检测到的旧配置。
2. 选择“标准（推荐）”或“高质量”转录模式。
3. 下载并校验本地模型。

主界面支持：

- 一条或多条链接。
- 添加本地媒体。
- 查看等待、读取、下载、转录、保存、完成和失败状态。
- 取消任务、重试失败任务、查看技术详情。
- 查看模型安装状态和删除由公共版管理的模型。
- 打开小某书登录窗口。
- 打开输出目录。

普通错误提示不直接显示 Python traceback；技术详情中保留可诊断信息。

## 六、隐私与安全

- 默认没有遥测、analytics 或远程任务历史。
- 媒体转码和转录在本机执行。
- 安装包不包含个人 Cookie、Chrome Profile、真实转录、测试媒体或个人默认路径。
- Web 服务只监听 127.0.0.1，写请求需要随机 session token。
- 目标目录禁止使用符号链接越界写入。
- Markdown 与 Raw JSON 使用临时文件写入后原子替换。
- 小某书 Experimental 只引用用户自己的 Chrome Profile，不复制或打包登录状态。
- 不绕过付费、DRM、地区、年龄、验证码或其他访问控制。

## 七、测试结果

### 自动化测试

51 项通过，0 失败。

覆盖旧配置迁移、全新设置、中文/空格/iCloud 风格路径、单条任务、10 条批量任务、单条失败继续、四类来源、本地媒体、重复检测、模型缺失、磁盘不足、取消、重启恢复、原子写入和符号链接防护。

### 真实来源测试

| 来源 | 结果 | 说明 |
|---|---|---|
| 油管 | 通过 | 真实链接完成音频下载、86.39 秒转录、Markdown 和 Raw JSON |
| B站 | 通过 | 指定 BV 链接完成下载、131.65 秒转录和导出 |
| 小某书 Experimental | 通过 | 指定链接使用用户已有登录状态完成下载、30.40 秒转录和导出 |
| 本地媒体 | 通过 | MP3、MP4、WAV 完成真实 MLX 转录；M4A、MOV 完成格式覆盖 |

所有产品化测试写入临时目录，没有写入正式 Obsidian。

### 独立运行测试

- 在仅保留 /usr/bin:/bin 的 PATH 下，由 Tauri 启动内置 sidecar 和 FFmpeg，完成本地转录与 Markdown 导出。
- DMG 可以创建、校验、只读挂载。
- 直接从挂载后的 DMG 内运行 sidecar，完成真实 MLX 转录。
- App 内运行时没有依赖 Homebrew 或用户 Python。
- Web UI 与 Desktop 复用同一 session 的测试通过。

## 八、构建与依赖

| 组件 | 当前版本/状态 |
|---|---|
| Creator Source Importer | 0.7.0 Beta |
| Python Runtime | 3.12，PyInstaller onedir |
| yt-dlp | 2026.8.19 |
| MLX | 0.32.2 |
| mlx-whisper | 0.4.3 |
| FFmpeg/ffprobe | 9.0.1，自行构建的 LGPL 配置 |
| Deno | 2.9.6 arm64 |
| Tauri CLI | 2.11.4 |

Homebrew FFmpeg 没有进入安装包。FFmpeg 使用通用安装前缀构建，并把动态库引用改为 App 相对路径。许可证为 GPL 的可选 mutagen 已从冻结 sidecar 排除。

最终产物：

- App 文件系统占用约 703 MB。
- DMG 约 289 MB。
- 标准模型不在 DMG 内，当前实测约 1.5 GB。
- DMG SHA-256：27205e6f112beb4bb54466fcf02ce6e773fb1cff61395ca25e6d4a92185e0e5c

## 九、版本与发布状态

- 本地 Git 分支：productization-v07。
- 当前开发基线提交：4250bd9。
- 没有配置 Git 远程仓库。
- 没有上传源码、DMG 或真实资料。
- 没有创建 GitHub Release。
- 没有给项目源码自动添加 MIT、Apache 等开源许可证。
- 已准备本地 Release Draft、README、隐私说明、Changelog、依赖清单和签名流程。

## 十、当前未完成与风险

### P0：阻止公开发布

1. **没有 Developer ID Application 和公证凭据**  
   当前 App 只有 ad-hoc 签名。codesign 本地结构验证通过，但 spctl 拒绝。普通用户从网络下载后不能获得预期的双击打开体验。

2. **没有干净 Apple Silicon Mac 验收**  
   当前已进行隔离 PATH 和挂载 DMG 测试，但测试机仍是开发机。尚未在没有源码、Python、Homebrew 和旧模型缓存的 Mac 上完成“安装 → 首次下载模型 → 油管导入 → 转录 → Markdown”。

3. **许可证归集尚未完全结束**  
   直接依赖和主要间接依赖已审计，FFmpeg 路线已确认；正式公开前仍需把每个随包组件要求的完整许可证文本归集到 Release，并进行最终复核。

### P1：Private Beta 前建议解决

1. 高质量模型尚未真实下载和转录。
2. 首次模型下载的断网、重试和进度准确度需要真实新用户测试。
3. DMG 当前是标准可挂载镜像，缺少定制背景和 Applications 拖放快捷方式。
4. 错误日志只有本地技术详情，尚未设计用户主动导出诊断包。
5. 缺少不同 macOS 13/14/15 设备的兼容性结果。

### 长期限制

- 小某书依赖 Chrome、用户登录状态和页面结构，当前成功不代表长期稳定。
- 平台策略或页面变化可能导致网络来源失效，需要持续维护适配器。
- 首次模型下载体积较大，弱网络用户体验可能较差。
- 目前只支持 Apple Silicon Mac。

## 十一、建议的下一阶段路线

### 路线 A：进入签名与小范围 Private Beta（推荐）

适合尽快让 5～20 名真实用户安装和反馈：

1. 确认是否加入 Apple Developer Program。
2. 完成 Developer ID、hardened runtime、notarization 和 staple。
3. 找一台干净 Apple Silicon Mac 做完整首次使用验收。
4. 完成第三方许可证文本归集。
5. 建立只承载介绍、下载、隐私、Issue 和 Release 的公开发布仓库。
6. 发布签名后的 Private Beta，收集安装、模型下载、来源成功率和输出可读性问题。
7. 根据反馈决定 0.8 UX 范围，而不是立即商业化。

### 路线 B：继续个人使用，先加强稳定性

适合暂不承担签名和用户支持成本。优先完善模型下载恢复、诊断包导出、macOS 多版本测试、平台适配回归测试、任务暂停和失败临时文件清理界面。

### 路线 C：直接发布 unsigned DMG

不建议。它会让普通用户遇到 Gatekeeper 阻挡，降低信任，也无法验证“下载后直接安装使用”的产品目标。

## 十二、请 Chat 模式重点判断

请基于本报告回答：

1. 当前最合理的下一阶段是继续稳定性开发，还是先完成签名并进入小范围 Private Beta？为什么？
2. 在进入 Private Beta 前，哪些项目是真正的 P0，哪些可以延后？
3. 是否值得现在加入 Apple Developer Program？请结合测试目标、维护成本和未来商业化判断。
4. 私有源码仓库与公开 Release 仓库分离是否合适？公开仓库第一版至少应包含哪些页面和 Issue 模板？
5. 5～20 人 Private Beta 应如何设计测试任务、反馈问卷和成功指标？
6. 小某书 Experimental 应继续保留在主界面，还是放入实验设置？
7. 标准模型约 1.5 GB、DMG 约 289 MB，这个体积是否合理？Beta 前是否需要继续压缩？
8. 在不加入遥测的前提下，如何设计用户主动提交的诊断信息？
9. 商业化讨论应该在哪个验证节点开始？在此之前最需要证明的用户价值是什么？
10. 请给出按先后顺序排列的 0.7.1／0.8 执行清单，并标出每项验收标准。

## 十三、评审边界

本轮只做产品和工程路线评审。未经项目所有者确认，不执行：

- 公开 GitHub Release。
- 开源完整源码或添加源码许可证。
- 购买 Apple Developer 会员。
- 引入遥测、账号、支付或云端转录。
- 删除个人版、旧配置、旧任务历史或现有 Obsidian 内容。
