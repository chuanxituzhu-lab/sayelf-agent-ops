$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$tauri = Join-Path $repo 'desktop/tauri'
if ((py -3.12 -c 'import sys; print(sys.version_info[:2] == (3, 12))') -ne 'True') { throw 'Install Python 3.12 x64 on this builder.' }
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { throw 'Install Rust MSVC x64 on this builder.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Install Node.js/npm on this builder.' }
Push-Location $repo
try {
    py -3.12 -m venv desktop/runtime/.venv
    & desktop/runtime/.venv/Scripts/python.exe -m pip install --disable-pip-version-check -r desktop/runtime/requirements-build.txt
    & desktop/runtime/.venv/Scripts/python.exe desktop/runtime/build_sidecar.py
    Push-Location $tauri
    try {
        if (-not (Test-Path package-lock.json)) { npm install --package-lock-only }
        npm ci
        npm run tauri -- build --bundles nsis
    } finally { Pop-Location }
    $bundle = Join-Path $tauri 'src-tauri/target/release/bundle/nsis'
    $installer = Get-ChildItem -LiteralPath $bundle -Filter '*-setup.exe' -Recurse | Select-Object -First 1
    if (-not $installer) { throw 'Tauri did not produce an NSIS Setup.exe.' }
    $dist = Join-Path $PSScriptRoot 'dist'
    New-Item -ItemType Directory -Force -Path $dist | Out-Null
    Copy-Item -LiteralPath $installer.FullName -Destination (Join-Path $dist 'Sayelf-Agent-Ops-Setup-x64.exe') -Force
    Get-FileHash (Join-Path $dist 'Sayelf-Agent-Ops-Setup-x64.exe') -Algorithm SHA256
} finally { Pop-Location }
