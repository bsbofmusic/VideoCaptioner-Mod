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
    assert source.splitlines().count("UninstallDisplayName={#MyAppName}") == 1
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


@pytest.mark.parametrize(
    "replacement",
    ["", "UninstallDisplayName={#MyAppName} {#MyAppVersion}"],
    ids=["removed", "changed"],
)
def test_installer_validator_requires_exact_uninstall_display_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import build_windows_installer

    required_directive = "UninstallDisplayName={#MyAppName}"
    source = INNO_SOURCE.read_text(encoding="utf-8")
    assert required_directive in source

    regressed_source = tmp_path / "VideoCaptioner.iss"
    regressed_text = source.replace(required_directive, replacement, 1)
    assert required_directive not in regressed_text.splitlines()
    regressed_source.write_text(regressed_text, encoding="utf-8")
    monkeypatch.setattr(build_windows_installer, "INNO_SCRIPT", regressed_source)

    with pytest.raises(RuntimeError, match="missing required directives") as exc_info:
        build_windows_installer.validate_source()
    assert required_directive in str(exc_info.value)


def test_uninstall_display_name_matches_workflow_registry_contract() -> None:
    source = INNO_SOURCE.read_text(encoding="utf-8")
    workflow = DESKTOP_WORKFLOW.read_text(encoding="utf-8")

    app_name = re.search(
        r'^#define\s+(?P<symbol>MyAppName)\s+"(?P<value>[^"\r\n]+)"$',
        source,
        re.MULTILINE,
    )
    uninstall_display_name = re.search(
        r"^UninstallDisplayName=\{#(?P<symbol>[A-Za-z_][A-Za-z0-9_]*)\}$",
        source,
        re.MULTILINE,
    )
    workflow_display_name = re.search(
        r'^\s*\$displayNameMatches\s*=\s*\$entry\.DisplayName\s+-eq\s+"'
        r'(?P<value>[^"\r\n]+)"\s*$',
        workflow,
        re.MULTILINE,
    )

    assert app_name is not None
    assert uninstall_display_name is not None
    assert workflow_display_name is not None
    assert uninstall_display_name.group("symbol") == app_name.group("symbol")

    resolved_installer_product_name = app_name.group("value")
    assert workflow_display_name.group("value") == resolved_installer_product_name


def test_windows_workflow_smokes_installed_render_and_uninstall_cleanup() -> None:
    workflow = DESKTOP_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("Invoke-CheckedProcess -Executable $installer.FullName") == 2
    assert "scripts/smoke_desktop.py $installDir" in workflow
    assert 'DisplayName -eq "VideoCaptioner-Mod"' in workflow
    assert "Install directory remains after uninstall" in workflow
