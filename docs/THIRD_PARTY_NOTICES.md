# Third-Party Notices

Creator Source Importer 本身暂未声明开源许可证。安装包包含或链接以下第三方组件，其权利归各自作者：

- FFmpeg 9.0.1：GNU Lesser General Public License 2.1 或以后版本。本构建禁用自动探测及 GPL 编码组件。完整 LGPL 文本随 App 提供；对应源码归档应与 Release 同时提供。
- Python 3.12：Python Software Foundation License。
- Deno 2.9.6：MIT License。
- Tauri 2.x 及 Rust crates：主要为 Apache-2.0、MIT、BSD 等许可，精确版本由 Cargo.lock 固定。
- yt-dlp 2026.8.19：Unlicense。
- yt-dlp-ejs 0.8.0：Unlicense、MIT、ISC。
- MLX、MLX Metal、mlx-whisper：MIT。
- Playwright Python：Apache-2.0。
- NumPy、SciPy、Numba、llvmlite 及 Python 网络/工具依赖：BSD、MIT、Apache-2.0、MPL-2.0、PSF 及其声明的兼容许可。
- PyInstaller bootloader：GPL-2.0-or-later，带允许分发非自由程序的 bootloader exception。

完整许可文本应从冻结环境中各 distribution 的 `licenses/` 或 `LICENSE*` 文件归集到最终 Release 附件。0.7.0 当前是开发构建，公开 Release 前必须完成该归集与独立法律复核。

