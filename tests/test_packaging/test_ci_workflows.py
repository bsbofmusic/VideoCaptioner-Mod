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


def test_windows_installer_smoke_checks_all_matching_uninstall_registry_views() -> None:
    workflow = DESKTOP_WORKFLOW.read_text(encoding="utf-8")
    smoke = _step(workflow, "Smoke test silent install and uninstall")
    roots_match = re.search(
        r"(?ms)^          \$uninstallRoots = @\(\n"
        r"(?P<body>.*?)"
        r"^          \)\n",
        smoke,
    )

    assert roots_match, "uninstall registry roots not found"
    assert re.findall(r'(?m)^            "([^"]+)"$', roots_match.group("body")) == [
        r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKCU:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]

    finder_match = re.search(
        r"(?ms)^          function Get-MatchingUninstallEntries \{\n"
        r"(?P<body>.*?)"
        r"^          \}\n\n"
        r"^          \$installerArguments =",
        smoke,
    )
    assert finder_match, "uninstall registry matching helper not found"
    finder = finder_match.group("body")
    assert "Test-Path -LiteralPath $root" in finder
    assert "Get-ChildItem -LiteralPath $root" in finder
    assert '$entry.DisplayName -eq "VideoCaptioner-Mod"' in finder
    assert "IsNullOrWhiteSpace([string]$entry.InstallLocation)" in finder
    assert "[System.IO.Path]::GetFullPath($InstallDir)" in finder
    assert re.search(
        r"\[System\.IO\.Path\]::GetFullPath\(\s*"
        r"\[string\]\$entry\.InstallLocation\s*\)",
        finder,
    )
    assert finder.count(".TrimEnd($pathSeparators)") == 2
    assert "[System.StringComparer]::OrdinalIgnoreCase.Equals(" in finder
    assert "RegistryPath = $key.PSPath" in finder

    registry_call = (
        "@(Get-MatchingUninstallEntries -Roots $uninstallRoots -InstallDir $installDir)"
    )
    assert smoke.count(registry_call) == 2
    assert re.search(
        r"(?ms)\$uninstallEntries = "
        + re.escape(registry_call)
        + r"\n"
        r"          if \(\$uninstallEntries\.Count -ne 1\) \{\n"
        r"            throw \"Expected exactly one matching uninstall entry, found "
        r"\$\(\$uninstallEntries\.Count\)\"\n"
        r"          \}\n"
        r"          Write-Host \"Matched uninstall registry entry: "
        r"\$\(\$uninstallEntries\[0\]\.RegistryPath\)\"",
        smoke,
    )

    cleanup_check = (
        'if (Test-Path $installDir) { throw "Install directory remains after uninstall: '
        '$installDir" }'
    )
    remaining_call = "$remainingEntries = " + registry_call
    assert smoke.index(cleanup_check) < smoke.index(remaining_call)
    assert re.search(
        r"(?ms)\$remainingEntries = "
        + re.escape(registry_call)
        + r"\n"
        r"          if \(\$remainingEntries\.Count -ne 0\) \{\n"
        r"            throw \"Expected zero matching uninstall entries after uninstall, found "
        r"\$\(\$remainingEntries\.Count\)\"\n"
        r"          \}",
        smoke,
    )
