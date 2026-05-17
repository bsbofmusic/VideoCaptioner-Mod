import logging
import os
import sys
from pathlib import Path

try:
    from videocaptioner._version import __version__ as _raw_version
    # Strip dev suffix (e.g. "1.5.0.dev103+g38544177c" → "1.5.0")
    VERSION = _raw_version.split(".dev")[0]
except Exception:
    VERSION = "0.0.0-dev"
YEAR = 2026
APP_NAME = "VideoCaptioner-Mod"
AUTHOR = "Weifeng"

HELP_URL = "https://github.com/bsbofmusic/VideoCaptioner-Mod"
GITHUB_REPO_URL = "https://github.com/bsbofmusic/VideoCaptioner-Mod"
RELEASE_URL = "https://github.com/bsbofmusic/VideoCaptioner-Mod/releases/latest"
FEEDBACK_URL = "https://github.com/bsbofmusic/VideoCaptioner-Mod/issues"

# Detect whether running from source tree, pip-installed, or PyInstaller-frozen
_PACKAGE_DIR = Path(__file__).parent
_PROJECT_ROOT = _PACKAGE_DIR.parent

if getattr(sys, "frozen", False):
    # PyInstaller: resources are bundled next to the frozen package inside _MEIPASS.
    # Keep user-writable files outside the bundle so settings/models/cache persist.
    from platformdirs import user_data_dir

    ROOT_PATH = Path(getattr(sys, "_MEIPASS", _PROJECT_ROOT))
    RESOURCE_PATH = ROOT_PATH / "resource"
    APPDATA_PATH = Path(user_data_dir(APP_NAME))
    WORK_PATH = Path.home() / APP_NAME
elif (_PROJECT_ROOT / "resource").is_dir():
    ROOT_PATH = _PROJECT_ROOT
    RESOURCE_PATH = ROOT_PATH / "resource"
    APPDATA_PATH = ROOT_PATH / "AppData"
    WORK_PATH = ROOT_PATH / "work-dir"
else:
    # Installed via pip — use platform-appropriate directories
    from platformdirs import user_data_dir

    ROOT_PATH = Path(user_data_dir(APP_NAME))
    RESOURCE_PATH = ROOT_PATH / "resource"
    APPDATA_PATH = ROOT_PATH
    WORK_PATH = Path.home() / APP_NAME

BIN_PATH = RESOURCE_PATH / "bin"
ASSETS_PATH = RESOURCE_PATH / "assets"
SUBTITLE_STYLE_PATH = RESOURCE_PATH / "subtitle_style"
TRANSLATIONS_PATH = RESOURCE_PATH / "translations"
FONTS_PATH = RESOURCE_PATH / "fonts"

# Fallback: bundled fonts inside the package (for pip install)
_BUNDLED_FONTS = _PACKAGE_DIR / "resources" / "fonts"
if not FONTS_PATH.exists() and _BUNDLED_FONTS.exists():
    FONTS_PATH = _BUNDLED_FONTS

LOG_PATH = APPDATA_PATH / "logs"
LLM_LOG_FILE = LOG_PATH / "llm_requests.jsonl"
SETTINGS_PATH = APPDATA_PATH / "settings.json"
CACHE_PATH = APPDATA_PATH / "cache"
MODEL_PATH = APPDATA_PATH / "models"

FASTER_WHISPER_PATH = BIN_PATH / "Faster-Whisper-XXL"

# Logging
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Add bin paths to PATH (only if they exist)
if BIN_PATH.exists():
    os.environ["PATH"] = str(FASTER_WHISPER_PATH) + os.pathsep + os.environ["PATH"]
    os.environ["PATH"] = str(BIN_PATH) + os.pathsep + os.environ["PATH"]

if (BIN_PATH / "vlc").exists():
    os.environ["PYTHON_VLC_MODULE_PATH"] = str(BIN_PATH / "vlc")

# Create data directories
for p in [CACHE_PATH, LOG_PATH, WORK_PATH, MODEL_PATH]:
    p.mkdir(parents=True, exist_ok=True)
