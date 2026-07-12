"""Static validation for the maintained Windows installer source."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INNO_SOURCE = ROOT / "packaging" / "windows" / "VideoCaptioner.iss"
DESKTOP_WORKFLOW = ROOT / ".github" / "workflows" / "build-desktop.yml"


def test_inno_source_uses_dynamic_version_and_supports_uninstall() -> None:
    source = INNO_SOURCE.read_text(encoding="utf-8")

    assert "#error MyAppVersion" in source
    assert "AppVersion={#MyAppVersion}" in source
    assert "OutputBaseFilename=VideoCaptioner-{#MyAppVersion}-windows-x64-setup" in source
    assert "ArchitecturesAllowed=x64compatible" in source
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in source
    assert not re.search(r"^Architectures(?:Allowed|InstallIn64BitMode)=x64$", source, re.MULTILINE)
    assert "UninstallDisplayIcon=" in source
    assert "unins000" not in source
    assert not re.search(r'#define\s+MyAppVersion\s+"\d', source)


def test_installer_build_helper_validates_source_on_any_platform() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_windows_installer.py", "--validate-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Validated packaging/windows/VideoCaptioner.iss" in result.stdout


def test_installer_validator_rejects_deprecated_x64_identifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import build_windows_installer

    regressed_source = tmp_path / "VideoCaptioner.iss"
    source = INNO_SOURCE.read_text(encoding="utf-8")
    regressed_source.write_text(source.replace("x64compatible", "x64"), encoding="utf-8")
    monkeypatch.setattr(build_windows_installer, "INNO_SCRIPT", regressed_source)

    with pytest.raises(RuntimeError, match="deprecated x64 architecture identifier"):
        build_windows_installer.validate_source()


def test_windows_workflow_smokes_installed_render_and_uninstall_cleanup() -> None:
    workflow = DESKTOP_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("& $installer.FullName /VERYSILENT") == 2
    assert "scripts/smoke_desktop.py $installDir" in workflow
    assert 'DisplayName -eq "VideoCaptioner-Mod"' in workflow
    assert "Install directory remains after uninstall" in workflow
