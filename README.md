# VideoCaptioner-Mod

VideoCaptioner-Mod 是基于 [WEIFENG2333/VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner) 的非官方修改版。

- 当前版本：`0.0.4`
- 原项目：<https://github.com/WEIFENG2333/VideoCaptioner>
- 本修改版仓库：<https://github.com/bsbofmusic/VideoCaptioner-Mod>
- 许可证：GNU General Public License v3.0，见 [LICENSE](LICENSE)

本仓库不是原作者官方版本，也不代表原作者维护、认可或背书。原作者归属、修改版归属与非官方声明见 [NOTICE](NOTICE)。

## 更新说明

### 0.0.4

- 在“设置 → 翻译与优化”中新增“校对超时时间”滑条，范围 `90-600` 秒，默认 `90` 秒。
- 字幕校对阶段会将该超时时间用于每次 LLM 校对请求；推理较慢的模型可适当调高，以减少过早超时并改善校正质量。
- 字幕校对批次 watchdog 会随超时时间扩展，避免合法重试在较长超时配置下被提前终止。

### 0.0.3

- 在“设置 → 翻译与优化”中新增“校对并发数量”滑条，范围 `1-20`，默认 `10`。
- 在“设置 → 翻译与优化”中新增“校对批次大小”滑条，范围 `10-100`，默认 `50`。
- 字幕校对阶段现在独立读取上述两个参数；翻译服务的“线程数/批处理大小”仍只影响翻译流程。
- 发布 Windows x64 安装包，可在 GitHub Release 下载，包含应用图标、开始菜单快捷方式和卸载程序。

### 0.0.2

- 新增批量任务预检机制，在转录、字幕处理、全流程合成阶段启动前检查输入/输出路径。
- 自动清洗由文件名生成的输出路径，修复尾随空格、尾随点、Windows 非法字符和保留名。
- 自动创建输出目录并检查可写性，避免无人值守批处理第一步就因路径问题卡死或反复重试。
- 将确定性路径错误（如 `[WinError 3]`）标记为不可重试，直接给出失败原因。
- 字幕校正默认 batch size 从 `30` 行迁移到 `50` 行；已保存旧默认值的用户会一次性迁移。
- 加强字幕校正/翻译/断句阶段的无进度超时与停止逻辑。
- 字幕优化批次改为进程隔离执行，单批卡死可强制终止并回退原文，避免 GUI/批处理被不可杀线程拖死。

### 0.0.1

- 新增 `Codex` LLM 提供商，使用 OpenAI Responses API `/responses`。
- 新增 `Anthropic` LLM 提供商，使用 Anthropic Messages API `/messages`，默认模型配置为 `MiniMax-M2.7`。
- 保留原有 OpenAI 兼容提供商逻辑，非 Codex/Anthropic 提供商继续走原版 Chat Completions 路径。
- 增加字幕处理防卡死机制：LLM 请求超时、字幕优化批次无进度超时、批处理任务无进度超时。
- 任务失败时尽量给出具体原因；批处理中的非 LLM 问题自动重试最多 5 次。
- 增加 LLM 请求日志对 Responses API 的兼容处理。

## 安装与运行

Windows 用户可在 [GitHub Release](https://github.com/bsbofmusic/VideoCaptioner-Mod/releases/latest) 下载安装包。安装包会创建开始菜单项，并可通过系统“应用和功能”或开始菜单卸载项卸载。

源码运行：

```bash
git clone https://github.com/bsbofmusic/VideoCaptioner-Mod.git
cd VideoCaptioner-Mod
pip install -e .[gui]
videocaptioner
```

免费功能（B 接口、J 接口、必应/谷歌翻译）无需 API Key。LLM 字幕优化、LLM 翻译、Whisper API 等功能需要自行配置对应服务的 API Key。

## 隐私与配置提醒

- 不要公开 `AppData/`、`work-dir/`、日志、缓存或配置文件。
- `AppData/settings.json` 可能包含 API Key。
- `AppData/logs/llm_requests.jsonl` 可能包含字幕内容、请求内容和响应内容。
- 使用云端 ASR、LLM、翻译或 TTS 服务时，相关音频、字幕或文本可能会发送到第三方服务。

## 第三方组件

第三方组件、依赖和二进制文件说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。不同组件可能有各自许可证，请在再分发时一并遵守。

## 免责声明

本项目按“原样”提供，不提供任何明示或默示担保，包括但不限于适销性、特定用途适用性和非侵权担保。

使用者应自行承担使用本软件产生的风险，包括但不限于字幕内容错误、翻译错误、接口费用、第三方服务限制、账号风险、数据泄露和其他直接或间接后果。

在 GPL-3.0 允许的最大范围内，原作者和本修改版维护者均不对任何使用结果负责。详见 GPL-3.0 协议中的免责声明和责任限制条款。

## 源代码与 GPL-3.0 说明

本项目作为 GPL-3.0 项目的修改版，继续按 GNU General Public License v3.0 发布。完整对应源代码已在本仓库公开，GitHub Release 也会附带源码包。

在遵守 GPL-3.0 的前提下，你可以：

- 运行本软件；
- 复制和分发本软件；
- 修改本软件；
- 分发你的修改版；
- 将本软件用于学习、研究、个人、组织或商业场景。

如果你再分发本软件或其修改版，你需要遵守 GPL-3.0，包括但不限于：

- 保留版权声明、许可证文本和修改说明；
- 以 GPL-3.0 兼容方式提供完整对应源代码；
- 不得向下游接收者施加额外限制；
- 如果分发二进制/打包版本，应同时提供源码或符合 GPL-3.0 的源码获取方式。

本 README 中的免责声明、用途提醒或风险提示不限制 GPL-3.0 授予你的任何权利。
