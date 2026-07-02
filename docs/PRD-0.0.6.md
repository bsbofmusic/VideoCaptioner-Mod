# VideoCaptioner-Mod 0.0.6 PRD

## Objective

Rebuild VideoCaptioner-Mod 0.0.6 from the latest upstream `WEIFENG2333/VideoCaptioner` master source, then re-apply only the maintained Mod changes. The release remains a source/CLI release, not a Windows exe installer release.

## Upstream Base

- Repository: `https://github.com/WEIFENG2333/VideoCaptioner`
- Branch: `master`
- Target commit: `95842ecb5618c0b6a548a336bdfb0eb859bdb501`

## Product Requirements

### LLM Providers

- Add `Codex` as an LLM provider.
- Codex must call OpenAI Responses API `/responses` only and must not fall back to Chat Completions.
- Add `Anthropic` as an LLM provider.
- Anthropic must call Anthropic Messages API `/messages` and keep MiniMax-compatible defaults:
  - model: `MiniMax-M2.7`
  - base URL: `https://api.minimaxi.com/anthropic/v1`
- Non-Codex/non-Anthropic providers must keep upstream OpenAI-compatible Chat Completions behavior.
- LLM request logs and log UI must tolerate Responses API records and nullable usage fields.

### Proofreading Stability And Controls

- Keep subtitle proofreading process isolation so a stuck batch can be terminated without freezing the GUI or batch queue.
- Failed or timed-out proofreading batches must fall back to original text and still report progress.
- Child proofreading processes must inherit the parent cache-enabled state.
- Preserve detailed validation logs:
  - missing keys
  - extra keys
  - similarity
  - Original
  - Optimized
  - alignment failures
- Keep proofreading controls independent from translation controls:
  - concurrency: `1-20`, default `10`
  - batch size: `10-100`, default `50`
  - timeout seconds: `90-600`, default `90`
  - retry count: `3-50`, default `3`
- Proofreading timeout must be passed into each LLM call.
- Proofreading watchdogs must scale with `timeout_seconds * retry_count + 30`, with the existing minimum stage timeout preserved.

### GUI Drag And Drop

- GUI launched from the CLI must support dragging local media files into the task creation flow.
- Dragging onto the search box, home page, or main stacked container must import supported audio/video files.
- Unsupported files must not switch pages or start a task.

### Batch And Path Reliability

- Preserve batch preflight validation before queued jobs start.
- Preserve output path sanitization for derived filenames.
- Deterministic path errors must not enter automatic retry loops.
- Output directories must be created and checked for writability before work starts.

### ASR And Cache Behavior

- Preserve public B/J ASR models and do not remove or rename them.
- Preserve friendly ASR error messages.
- Preserve narrow rate-limit cache refresh behavior for ASR rate-limit state only.
- Do not advertise ASR limit reset behavior in README or CHANGELOG.

### CLI And Packaging

- Keep the package installable with `pip install -e .[gui]`.
- `videocaptioner` with no arguments should launch the GUI when GUI dependencies are installed.
- CLI subtitle processing must read `subtitle.retry_count` from config and pass it to proofreading.
- The 0.0.6 release must be a GitHub source/CLI release. No exe installer artifact is required.

### Branding, Paths, And Compliance

- Use `APP_NAME = "VideoCaptioner-Mod"`.
- Project URLs must point to `https://github.com/bsbofmusic/VideoCaptioner-Mod`.
- Keep GPL-3.0 license notices, `NOTICE`, and third-party notices.
- Do not commit user settings, logs, cache, subtitles, audio/video, API keys, GitHub tokens, or `AppData/settings.json`.

## Acceptance Criteria

- `python -m compileall` passes for modified Python files.
- `videocaptioner --version` reports `0.0.6` after local editable reinstall from a clean tagged tree.
- Codex and Anthropic code paths are present and provider selection wires through GUI config and task creation.
- Proofreading retry/timeout/concurrency/batch settings are present in GUI config and wired into `SubtitleOptimizer`.
- A mocked proofreading retry test proves configured retry count changes actual LLM call count.
- Drag-drop handler imports supported media paths and rejects unsupported paths without switching flow.
- Secret scan over staged changes finds no API keys or tokens.
- Reviewer subagent audit finds no blocking issues before release.
