# Changelog

## 0.0.6

- Rebuilt the working tree from upstream `WEIFENG2333/VideoCaptioner` master commit `95842ec`.
- Re-applied VideoCaptioner-Mod features on the new base:
  - Codex provider via OpenAI Responses API `/responses` only.
  - Anthropic/MiniMax provider via Anthropic Messages API `/messages`.
  - Independent proofreading concurrency, batch size, timeout, and retry controls.
  - Process-isolated subtitle proofreading batches with hard timeout fallback.
  - GUI media drag-and-drop forwarding for CLI-launched GUI sessions.
  - Batch path preflight and Windows-safe output path sanitization.
  - Mod-specific app name, GitHub links, and release metadata.
- This release is source/CLI oriented. No new Windows exe installer artifact is provided.
