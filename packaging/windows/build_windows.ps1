$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

python -m pip install --upgrade pyinstaller imageio-ffmpeg python-vlc pillow
python -m pip install --upgrade ".[gui]"

$IconPath = Join-Path $PSScriptRoot "logo.ico"
python -c "from PIL import Image; from pathlib import Path; p=Path(r'resource/assets/logo.png'); out=Path(r'packaging/windows/logo.ico'); img=Image.open(p).convert('RGBA'); img.save(out, sizes=[(16,16),(32,32),(48,48),(256,256)])"

$ffmpegExe = python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
$binDir = Join-Path $RepoRoot "resource\bin"
if (-not (Test-Path -LiteralPath $binDir)) {
    New-Item -ItemType Directory -Path $binDir | Out-Null
}
Copy-Item -LiteralPath $ffmpegExe -Destination (Join-Path $binDir "ffmpeg.exe") -Force

pyinstaller --noconfirm --clean "packaging\windows\VideoCaptioner-Mod.spec"

Write-Host "Built: $RepoRoot\dist\VideoCaptioner-Mod\VideoCaptioner-Mod.exe"
