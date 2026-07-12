# Desktop release build

VideoCaptioner publishes desktop bundles for Windows and macOS from GitHub Actions.
Users can download the zip files from a GitHub Release, extract them, and run the
bundled `VideoCaptioner` executable without installing Python or FFmpeg.

## Local build

```bash
uv sync --frozen --all-extras
uv run --with pyinstaller --with static-ffmpeg python scripts/build_desktop.py --clean
uv run python scripts/smoke_desktop.py dist/VideoCaptioner
```

The build script downloads static `ffmpeg` and `ffprobe` for the current platform
and bundles them under `resource/bin` inside the PyInstaller app. Runtime user data
is kept in the system user-data directory, so app upgrades do not overwrite
settings, logs, cache, models, or custom subtitle styles.

On Windows, install Inno Setup 6 after building the bundle, then create the maintained
installer with the VCS-derived package version:

```powershell
choco install innosetup --no-progress -y
uv run python scripts/build_windows_installer.py
```

The Inno source can be checked on any platform without a Windows bundle or compiler:

```bash
uv run python scripts/build_windows_installer.py --validate-only
```

## Release verification

Run the same repository gates used before a tagged release (with `ffmpeg` and `ffprobe`
available on `PATH`):

```bash
uv lock --check
uv sync --frozen
uv run ruff check videocaptioner/ tests/ scripts/
uv run pyright \
  videocaptioner/cli/ videocaptioner/core/asr/bcut.py \
  videocaptioner/core/dubbing/ videocaptioner/core/speech/providers.py \
  videocaptioner/core/subtitle/style_manager.py videocaptioner/ui/task_factory.py
QT_QPA_PLATFORM=offscreen uv run pytest \
  tests/test_cli tests/test_dubbing tests/test_asr tests/test_style \
  -m "not integration and not slow and not llm" -q
rm -rf dist && uv build
WHEEL_PATH="$(python -c 'from pathlib import Path; print(next(Path("dist").glob("*.whl")).resolve())')"
VIDEOCAPTIONER_TEST_WHEEL="$WHEEL_PATH" uv run pytest tests/test_packaging -q
uv run python scripts/build_windows_installer.py --validate-only
```

## CI and releases

`.github/workflows/build-desktop.yml` builds on:

- `windows-latest`
- `macos-15-intel`

Each job runs a real packaged-app smoke test:

- starts the packaged executable with `--version`
- lists bundled subtitle styles
- runs `doctor --json`
- generates a short video with bundled FFmpeg
- creates both soft-subtitle and hard-subtitle videos
- validates output duration with bundled ffprobe

The Windows job additionally compiles the Inno installer, performs a silent install and
in-place upgrade/reinstall, checks the uninstall registration, runs the installed executable
through `--version`, doctor, style, soft-subtitle, and hard-subtitle render smokes, then verifies
silent uninstall cleanup.

On `v*` tags, the workflow uploads portable desktop zip files and the Windows setup
executable to the GitHub Release. `.github/workflows/release-python.yml` runs the
Python quality gates, builds wheel/sdist, performs fresh core and all-extra install
smokes, then uploads those package files to the same release. PyPI is not published
automatically.
