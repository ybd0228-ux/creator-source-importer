# 隐私说明

Creator Source Importer 0.7.0 Beta 采用本地优先设计：

- 音视频转码和语音转录在本机执行。
- 转录、目标目录和任务历史不上传到本项目的服务器。
- 不包含遥测、analytics、用户账号或云端同步。
- 安装包不包含开发者 Cookie、浏览器 Profile、个人配置、真实媒体或真实转录。

使用链接来源时，App 会连接用户提交的网站以读取元数据和媒体。首次安装模型时会连接模型托管服务。小某书 Experimental 会调用用户系统中的 Chrome Profile；它引用用户自己的登录状态，不复制或打包该 Profile。

数据保存在用户选择的输出目录及 macOS Application Support 中。卸载 App 不会主动删除输出 Markdown。删除模型只删除由公共版管理的模型；从旧环境识别到的外部模型只会解除登记。

