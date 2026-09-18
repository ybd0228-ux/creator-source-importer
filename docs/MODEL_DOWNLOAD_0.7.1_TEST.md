# 0.7.1 Beta 模型下载验证

2026-09-17。此版本针对大陆无 VPN 首次下载超时：共享 Python Core 优先从魔搭下载标准或高质量 MLX Whisper 模型；魔搭不可用时使用 Hugging Face 备用源。两种来源的模型文件都按固定大小与 SHA-256 校验；魔搭中断的 `.part` 文件可在再次点击下载时续传。模型仍保存在应用数据目录，Web UI 与 Desktop App 使用同一份清单。

## 模型一致性

魔搭的 `mlx-community/whisper-large-v3-turbo` 与 Hugging Face 同名仓库：`config.json` SHA-256 为 `b34fc29e4e11e0a25e812775dd67f4dd16fc2c8eb43d28ae25ff7d660ecb6379`，`weights.safetensors` 为 `951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6`，大小 1,613,977,612 字节。

魔搭的 `mlx-community/whisper-large-v3-mlx` 与 Hugging Face 同名仓库：`config.json` SHA-256 为 `34982ce6ae286095000f82ae9583b3431639e8b092bf60c961f203745e6500e3`，`weights.npz` 为 `05ff791ce3630fae47e7c51004e9666204d786246ec07cac6110af768099b40d`，大小 3,083,520,416 字节。文件列表与哈希来自两个平台的仓库 API，并对小配置文件做了实际 SHA-256 比对。

这里验证的是文件逐字节一致性，不代表已经核实魔搭仓库的维护者身份或对模型再分发作出了法律结论；当前 App 不内置模型文件。

## 实测

- 无 VPN 的干净 macOS 虚拟机：魔搭两个模式的模型权重均成功获取 1 MiB 分段；标准权重随后完成全文件网络传输，终端显示 100%（约 1,539 MiB、2 分 51 秒）。这次虚拟机下载流向 `/dev/null`，因此验证了完整网络传输，但没有在虚拟机内计算文件哈希或安装新版 App。
- 开发机：新版 `ModelManager.install("standard")` 从魔搭下载完整标准模型，用固定大小和 SHA-256 校验并登记，约 144 秒。
- 开发机：使用安装在魔搭目录内的标准模型、并把 Hugging Face 缓存指向空目录，`transcribe_worker.py` 成功加载模型并处理 1 秒测试 WAV。
- 挂载 DMG 的冻结 sidecar：使用仅缺末尾 1 MiB 的本地测试数据发起安装，成功续传、校验完整文件，并在 API 中报告模型已安装。这个测试的网络来自开发机。
- 最终 0.7.1 DMG 已复制到无 VPN 虚拟机；虚拟机与开发机的 SHA-256 同为 `1992878f79e9bf0cca665ecd439ef04854bfac8e5814e1d67b11cea1cbbcefed`，镜像通过挂载校验。尚未在该虚拟机内运行新版 App。
- 自动测试：53 项通过，涵盖本地 HTTP 模拟的续传、备用源哈希失败拒绝登记以及既有导入功能。

## 尚未验证

- 新版 DMG 尚未在这台无 VPN 虚拟机里点击“开始下载”并完成 App 内安装。已有测试分别覆盖了虚拟机的完整网络传输和 DMG 内的下载实现，但不能把两项相加冒充一次虚拟机 App 端到端成功。
- 高质量模型在虚拟机仅验证 1 MiB 分段，尚未完成 3.08 GB 全文件下载和转录。
- 当前 DMG 仍为 ad-hoc 签名、未公证的本地测试构建，不是公开发布包。

来源：[魔搭标准模型](https://modelscope.cn/models/mlx-community/whisper-large-v3-turbo)、[魔搭高质量模型](https://modelscope.cn/models/mlx-community/whisper-large-v3-mlx)、[Hugging Face 标准模型](https://huggingface.co/mlx-community/whisper-large-v3-turbo)、[Hugging Face 高质量模型](https://huggingface.co/mlx-community/whisper-large-v3-mlx)。
