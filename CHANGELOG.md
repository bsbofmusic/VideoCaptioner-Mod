# Changelog

## 0.0.11

- Adds a deterministic mechanical subtitle-reflow path that groups real word/character timestamps by pauses, punctuation, and bounded display length without calling an LLM or fabricating timing.
- Enables mechanical reflow by default for MiniMax ASR with conservative defaults of 18 CJK characters / 12 space-separated words and a 500 ms pause boundary; Bcut/JianYing keep their provider segmentation by default and expose an explicit opt-in switch.
- Changes `ChunkedASR`'s global default concurrency from 3 to 1 so newly added providers are stable-by-default unless they explicitly opt into parallel chunk requests.
- Removes LLM subtitle splitting from the normal GUI/CLI pipeline defaults while retaining compatibility configuration/code for existing callers; subtitle optimization and translation remain independent LLM features.
- Adds CLI `--mechanical-split` / `--no-mechanical-split`, GUI switches, provider-policy tests, and deterministic reflow regressions covering text preservation, punctuation boundaries, pauses, English spacing, and fail-safe rejection of sentence-only timestamps.
- Validates the 18/500 defaults on a real 120-second excerpt from the Windows course library: MiniMax returned 566 real word timestamps; reflow preserved the full text, produced zero punctuation-leading cues, and held P95/max CJK cue length at 18 characters.

## 0.0.10

- Serializes Bcut/必剪 and JianYing long-audio chunks instead of sending three public-ASR chunks concurrently, reducing self-inflicted 412/429 bursts while keeping real upstream throttling visible.
- Fixes Windows ASS hard-subtitle synthesis when FFmpeg stderr contains bytes that the active Windows code page cannot decode; video-resolution detection now parses FFmpeg stderr as raw bytes.
- Makes batch-processing failures actionable in the table by showing a compact real error reason while preserving the full exception text in the tooltip.
- Adds regressions for public-ASR concurrency policy, Windows FFmpeg stderr decoding, and batch error presentation.
- Adds MiniMax ASR as a first-class `minimax` provider for CLI and GUI, using the official `asr-1.0` `/v1/speech_to_text` multipart API, SRT output, language hints/auto detection, word timestamps, masked configuration, connection testing, and actionable HTTP errors.
- Keeps MiniMax inside its official file limits by serializing long audio into 480-second chunks; Bcut/JianYing long-audio chunks remain serialized as well.
- Fixes a Qt test-thread teardown race that could abort the GitHub release test job with `QThread: Destroyed while thread is still running` even after the behavioral assertion passed.
- Validates the release candidate on Windows with a real 63-minute Chinese lecture video: MiniMax, Bcut, and JianYing all completed on the same real-audio sample, and all three completed a multi-chunk long-audio probe before release.

## 0.0.9

- Rebuilt the Mod from the exact upstream `WEIFENG2333/VideoCaptioner` v1.4.2 tag (`d753521d57cf2311df96bfee96fe39c6306a8e09`) instead of carrying forward the old proofreading/provider fork surface.
- Reworked the local ASR quota patch: before each quota check, only that ASR service's local `rate_limit:*` usage history is normalized to a fresh/full state. ASR result caches, settings, and other services are left untouched. This does not hide or bypass real upstream HTTP 429 responses.
- Bcut/必剪 reliability hardening:
  - Locks the upstream protocol to model sequence `8/8/8/7` and rejects the v0.0.8 result-query drift to model 8.
  - Adds bounded connect/read/write/pool timeouts and a 600-second healthy-task deadline.
  - Uses short bounded retries for 412/429, bounded retries for 5xx/timeout/transport failures, capped `Retry-After`, and sanitized errors.
- JianYing now keeps the same fresh local quota behavior while treating its remote signing service as an explicit external dependency. Persistent 429/5xx/transport failures use short bounded retries and return an actionable Bcut fallback instead of hanging or leaking endpoint details.
- The retired Bing Edge free-auth endpoint now fails with a clear Google/LLM fallback message instead of a raw 404 traceback, and the built-in/default onboarding translator is now Google rather than the retired Bing path.
- Keeps the lightweight CLI-first packaging from v0.0.7: GUI dependencies remain behind the `gui` extra, package resources are read-only, and user data stays in writable platform directories.
- Preserves small v0.0.7 compatibility wins: bundled `ffmpeg`/`ffprobe` doctor discovery and legacy subtitle style aliases (`毕导科普风`, `番剧可爱风`, `竖屏`).
- Intentionally drops the old Mod-only Codex/Anthropic proofreading providers, proofreading worker/process isolation, and other subtitle-proofreading fork complexity. Upstream v1.4.2 is the source of truth for those general features.
- Fixes small upstream defects found during rebuild: an invalid LLM translator return contract/unreachable statement, stale `ChunkedASR` tests, process-global test-cache leakage, missing deterministic LLM test fixture, and one Ruff violation.
- Release validation includes real Bcut transcription, explicit JianYing remote-throttle verification, core-only and GUI test matrices, clean artifact installs, counterexample stress tests, and two independent mechanical audits.

## 0.0.8

- Hardened Bcut polling and GUI startup, but also changed Bcut result-query `model_id` from upstream 7 to 8. v0.0.9 intentionally restores the upstream protocol while retaining the useful reliability ideas in a bounded form.

## 0.0.7

- Split lightweight CLI core from optional GUI/dubbing dependencies.
- Added Bcut request timeouts and a hard polling deadline.
- Added bundled media-tool doctor detection and legacy subtitle style aliases.
- Included broader Mod-only proofreading/provider and desktop packaging work that is intentionally not carried into v0.0.9 unless still justified by the v1.4.2 base.
