# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

block_cipher = None
project_root = Path.cwd()
packaging_root = project_root / "packaging" / "windows"

_datas = [
    (str(project_root / "resource"), "resource"),
    (str(project_root / "videocaptioner" / "core" / "prompts"), "videocaptioner/core/prompts"),
    (str(project_root / "videocaptioner" / "resources" / "fonts"), "resource/fonts"),
    (str(project_root / "LICENSE"), "."),
    (str(project_root / "NOTICE"), "."),
    (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project_root / "README.md"), "."),
    (str(project_root / "CHANGELOG.md"), "."),
]

datas = [(src, dest) for src, dest in _datas if Path(src).exists()]

for package in [
    "qfluentwidgets",
    "qframelesswindow",
    "modelscope",
    "langdetect",
    "certifi",
    "yt_dlp",
]:
    try:
        datas += collect_data_files(package)
    except Exception:
        pass

for package in [
    "videocaptioner",
    "modelscope",
    "yt-dlp",
    "PyQt-Fluent-Widgets",
    "qframelesswindow",
]:
    try:
        datas += copy_metadata(package)
    except Exception:
        pass

binaries = []
ffmpeg_path = project_root / "resource" / "bin" / "ffmpeg.exe"
if ffmpeg_path.exists():
    binaries.append((str(ffmpeg_path), "resource/bin"))

hiddenimports = [
    "PyQt5.QtSvg",
    "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets",
    "vlc",
]

for package in [
    "qfluentwidgets",
    "qframelesswindow",
    "yt_dlp.extractor",
    "yt_dlp.postprocessor",
    "yt_dlp.downloader",
    "modelscope.hub",
]:
    try:
        hiddenimports += collect_submodules(package)
    except Exception:
        pass

icon_path = packaging_root / "logo.ico"

a = Analysis(
    [str(project_root / "videocaptioner" / "__main__.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "tensorflow",
        "matplotlib",
        "notebook",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoCaptioner-Mod",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VideoCaptioner-Mod",
)
