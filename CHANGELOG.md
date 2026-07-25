# Changelog

## 0.0.8

- Unified Bcut upload, task creation, and result polling on model `8`.
- Made Bcut result polling recover from HTTP `412`, rate limits, temporary server failures,
  timeouts, and transport interruptions while preserving the existing ten-minute deadline and
  task ID.
- Sanitized Bcut HTTP and transport failures so task IDs, request URLs, and low-level connection
  details are not exposed in errors or retry logs.
- Prevented GUI startup events received during base-window construction from accessing
  `stackedWidget` before it is initialized.

## 0.0.7

- Fixed packaged `doctor` detection so bundled `ffmpeg` and `ffprobe` are recognized without relying on the host `PATH`.
- Split the lightweight CLI core from optional runtime features:
  - `gui`: PyQt5, PyQt-Fluent-Widgets, ModelScope, psutil, and GPUtil.
  - `dubbing`: Edge TTS.
  - `all`: complete GUI and dubbing installation.
  - Declared `httpx` explicitly for direct ASR/TTS HTTP clients.
- Made CLI parser and preset imports independent of GUI and Edge TTS packages; both GUI entry
  paths now return actionable extra-install hints instead of import tracebacks.
- Added explicit connect/read/write/pool timeouts to every Bcut request plus a ten-minute
  monotonic polling deadline that also caps the final result request and pending-state sleeps.
- Preserved persisted subtitle style names `毕导科普风`, `番剧可爱风`, and `竖屏` as aliases of
  the canonical `default`, `anime`, and `vertical` presets. Unified presets use the bundled
  `Noto Sans SC`, so line wrapping and glyph metrics can differ slightly from older fonts.
- Added a dynamically versioned Windows Inno Setup installer while retaining Windows portable
  zip and macOS desktop artifacts; CI verifies silent install/upgrade, `--version`, doctor,
  rendering, uninstall registration, and cleanup.
- Replaced automatic PyPI publishing with idempotent GitHub Release uploads for wheel/sdist and
  expanded release gates to lockfile, lint, type, unit, build, and fresh-install checks.
- Retained the v0.0.6 Mod behavior: default Bijian ASR, Codex Responses, Anthropic Messages,
  proofreading concurrency/retry/hard-timeout controls, drag/drop fallback, path preflight,
  doctor, dubbing, unified styles, and cross-platform desktop builds.

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
