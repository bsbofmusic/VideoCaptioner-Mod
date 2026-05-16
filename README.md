# VideoCaptioner-Mod

VideoCaptioner-Mod 是基于 [WEIFENG2333/VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner) 的非官方修改版。

本仓库不是原作者官方版本，原项目版权与许可证声明见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。

## 修改内容

版本：`0.0.1`

相对原版主要修改：

- 新增 `Codex` LLM 提供商，使用 OpenAI Responses API `/responses`，适配 `https://ms.ll9e.cn/v1` 等 Responses API 网关。
- 新增 `Anthropic` LLM 提供商，使用 Anthropic Messages API `/messages`，默认模型配置为 `MiniMax-M2.7`。
- 保留原有 OpenAI 兼容提供商逻辑，非 Codex/Anthropic 提供商继续走原版 Chat Completions 路径。
- ASR 公共接口本地限额自动刷新，仅清理本地 `rate_limit:*` 记录，不删除 ASR 结果缓存和用户配置。
- 字幕校正默认批处理大小调整为 `30` 行，并行数保持原版配置不变。
- 增加字幕处理防卡死机制：LLM 请求超时、字幕优化批次无进度超时、批处理任务无进度超时。
- 任务失败时尽量给出具体原因；批处理中的非 LLM 问题自动重试最多 5 次。
- 增加 LLM 请求日志对 Responses API 的兼容处理。

## 安装与运行

```bash
git clone https://github.com/<your-name>/VideoCaptioner-Mod.git
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

## 许可证

本修改版基于 GPL-3.0 发布，详见 [LICENSE](LICENSE)。

第三方组件和依赖说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 免责声明

本项目仅供学习与研究使用，按“原样”提供，不提供任何明示或默示担保。

使用者应自行承担使用本软件产生的全部风险，包括但不限于字幕内容错误、翻译错误、接口费用、第三方服务限制、账号风险、数据泄露和其他直接或间接后果。

本修改版维护者不对任何使用结果负责。详见 GPL-3.0 协议中的免责声明和责任限制条款。
