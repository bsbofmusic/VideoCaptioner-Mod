# Changelog

## 0.0.3

- Added proofreading concurrency slider under Settings → 翻译与优化.
- Added proofreading batch-size slider under Settings → 翻译与优化.
- Wired proofreading settings into subtitle optimization independently from translation concurrency and translation batch size.
- Raised the subtitle optimizer in-flight cap to 20 so the new concurrency slider is effective.

## 0.0.2

- Added batch preflight checks before starting queued jobs.
- Auto-sanitized derived output paths and created writable parent directories.
- Prevented deterministic path errors like trailing-space stems from entering retry loops.
- Migrated existing subtitle correction batch size defaults from 30 to 50.
- Added a process-isolated subtitle optimizer watchdog so stuck batches can be killed and safely fall back to original text.

## 0.0.1

- Added Codex provider based on OpenAI Responses API `/responses`.
- Added Anthropic provider based on Anthropic Messages API `/messages`.
- Preserved original OpenAI-compatible Chat Completions behavior for non-Codex/non-Anthropic providers.
- Changed subtitle correction batch size default to 30 lines.
- Added watchdogs/timeouts for LLM calls, subtitle optimization, and batch processing.
- Added non-LLM automatic retry for batch tasks, up to 5 attempts.
- Improved user-facing failure messages for known ASR and processing failures.
- Improved LLM log compatibility with Responses API records.
