#!/usr/bin/env python3
"""Build the Windows Inno Setup installer from the PyInstaller bundle."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

from build_desktop import _version

ROOT = Path(__file__).resolve().parent.parent
INNO_SCRIPT = ROOT / "packaging" / "windows" / "VideoCaptioner.iss"
BUNDLE_DIR = ROOT / "dist" / "VideoCaptioner"
ARTIFACT_DIR = ROOT / "artifacts"


def _validated_version(value: str) -> str:
    version = value.strip().lstrip("v")
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._+-]*", version):
        raise ValueError(f"Unsupported installer version: {value!r}")
    return version


def _find_iscc(explicit: str | None = None) -> Path:
    candidates: list[str | None] = [
        explicit,
        os.environ.get("ISCC_PATH"),
        shutil.which("iscc"),
        str(Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe"),
        str(Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise RuntimeError(
        "Inno Setup 6 compiler (ISCC.exe) was not found. "
        "Install Inno Setup or pass --iscc/ISCC_PATH."
    )


def validate_source() -> None:
    if not INNO_SCRIPT.is_file():
        raise RuntimeError(f"Inno Setup source not found: {INNO_SCRIPT}")
    source = INNO_SCRIPT.read_text(encoding="utf-8")
    required = [
        "#error MyAppVersion",
        "AppVersion={#MyAppVersion}",
        "OutputBaseFilename=VideoCaptioner-{#MyAppVersion}-windows-x64-setup",
        "PrivilegesRequired=lowest",
        "ArchitecturesAllowed=x64compatible",
        "ArchitecturesInstallIn64BitMode=x64compatible",
        "UninstallDisplayIcon=",
        '[Files]',
        '[Icons]',
    ]
    required_exact_directives = ["UninstallDisplayName={#MyAppName}"]
    if re.search(
        r"^Architectures(?:Allowed|InstallIn64BitMode)=x64$",
        source,
        re.MULTILINE,
    ):
        raise RuntimeError("Installer source uses deprecated x64 architecture identifier")
    missing = [token for token in required if token not in source]
    source_lines = source.splitlines()
    missing.extend(
        directive for directive in required_exact_directives if directive not in source_lines
    )
    if missing:
        raise RuntimeError("Installer source is missing required directives: " + ", ".join(missing))
    if re.search(r'#define\s+MyAppVersion\s+"\d', source):
        raise RuntimeError("Installer version must be supplied dynamically, not hard-coded")


def validate_bundle() -> None:
    required = [
        BUNDLE_DIR / "VideoCaptioner.exe",
        ROOT / "LICENSE",
        ROOT / "NOTICE",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Installer inputs are missing:\n  - " + "\n  - ".join(missing))


def build_installer(version: str, iscc: Path) -> Path:
    validate_source()
    validate_bundle()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    version = _validated_version(version)
    command = [str(iscc), f"/DMyAppVersion={version}", str(INNO_SCRIPT)]
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)
    artifact = ARTIFACT_DIR / f"VideoCaptioner-{version}-windows-x64-setup.exe"
    if not artifact.is_file():
        raise RuntimeError(f"Inno Setup completed without producing {artifact}")
    print(f"Created {artifact.relative_to(ROOT)}")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Override the VCS-derived package version")
    parser.add_argument("--iscc", help="Path to ISCC.exe (or set ISCC_PATH)")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the maintained Inno source without requiring Windows or a bundle",
    )
    args = parser.parse_args()

    validate_source()
    if args.validate_only:
        print(f"Validated {INNO_SCRIPT.relative_to(ROOT)}")
        return 0

    version = _validated_version(args.version or _version())
    build_installer(version, _find_iscc(args.iscc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
