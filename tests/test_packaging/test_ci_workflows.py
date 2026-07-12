"""Static contracts for release-critical GitHub Actions workflow structure."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DESKTOP_WORKFLOW = ROOT / ".github" / "workflows" / "build-desktop.yml"


def _job(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        source,
    )
    assert match, f"workflow job not found: {name}"
    return match.group("body")


def _step(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n(?P<body>.*?)(?=^      - name: |\Z)",
        source,
    )
    assert match, f"workflow step not found: {name}"
    return match.group("body")


def test_ci_keeps_full_quality_on_312_and_adds_exact_core_python_matrix() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    quality = _job(workflow, "python")
    compatibility = _job(workflow, "core-compatibility")

    assert re.search(r"(?m)^permissions:\n  contents: read$", workflow)
    assert 'python-version: "3.12"' in quality
    assert "uv sync --frozen --all-extras" in quality
    assert 'python-version: ["3.10", "3.11", "3.12"]' in compatibility
    assert 'python-version: "${{ matrix.python-version }}"' in compatibility
    assert "uv build --wheel" in compatibility
    assert "videocaptioner --help" in compatibility
    assert "videocaptioner transcribe --help" in compatibility
    assert "videocaptioner gui" in compatibility
    assert "videocaptioner-gui" in compatibility
    assert "pip install 'videocaptioner[gui]'" in compatibility
    assert "Traceback" in compatibility
    assert "--all-extras" not in compatibility


def test_desktop_release_write_permission_is_tag_only_and_separate_from_builds() -> None:
    workflow = DESKTOP_WORKFLOW.read_text(encoding="utf-8")
    desktop = _job(workflow, "desktop")
    release = _job(workflow, "release")

    assert re.search(r"(?m)^permissions:\n  contents: read$", workflow)
    assert "contents: write" not in desktop
    assert "gh release" not in desktop
    assert "actions/upload-artifact@" in desktop

    assert "needs: desktop" in release
    assert "if: github.event_name == 'push'" in release
    assert "startsWith(github.ref, 'refs/tags/v')" in release
    assert "permissions:\n      contents: write" in release
    assert "actions/download-artifact@" in release
    assert "pattern: desktop-*" in release
    assert "merge-multiple: true" in release
    assert "gh release create" in release
    assert "gh release upload" in release
    assert "--clobber" in release


def test_windows_installer_smoke_waits_for_checked_gui_processes() -> None:
    workflow = DESKTOP_WORKFLOW.read_text(encoding="utf-8")
    smoke = _step(workflow, "Smoke test silent install and uninstall")
    helper_match = re.search(
        r"(?ms)^          function Invoke-CheckedProcess \{\n"
        r"(?P<body>.*?)"
        r"^          \}\n\n"
        r"^          \$installer =",
        smoke,
    )

    assert helper_match, "checked-process helper not found"
    helper = helper_match.group("body")
    assert "[string]$Executable" in helper
    assert "[string[]]$ArgumentList" in helper
    assert "[string]$Description" in helper
    assert "Start-Process" in helper
    assert "-FilePath $Executable" in helper
    assert "-ArgumentList $ArgumentList" in helper
    assert "-Wait" in helper
    assert "-PassThru" in helper
    assert re.search(r"\$process\.ExitCode -ne 0", helper)
    assert "$($process.ExitCode)" in helper

    setup_calls = re.findall(
        r'(?m)^          Invoke-CheckedProcess -Executable \$installer\.FullName '
        r'-ArgumentList \$installerArguments -Description "[^"]+"$',
        smoke,
    )
    uninstall_calls = re.findall(
        r'(?m)^          Invoke-CheckedProcess -Executable \$uninstaller '
        r'-ArgumentList \$uninstallerArguments -Description "[^"]+"$',
        smoke,
    )
    assert len(setup_calls) == 2
    assert len(uninstall_calls) == 1
    assert "& $installer.FullName" not in smoke
    assert "& $uninstaller" not in smoke
    assert re.search(
        r'\$installerArguments = @\("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", '
        r'"/SP-", "/DIR=\$installDir"\)',
        smoke,
    )
    assert (
        '$uninstallerArguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")'
        in smoke
    )
