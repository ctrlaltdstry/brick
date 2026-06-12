# Vendor Windows Cinema 4D 2026 Python dependencies into ./vendor/win_amd64.
#
# Cinema 4D 2026 uses Python 3.11 on Windows, so this downloads CPython 3.11
# win_amd64 wheels and unpacks them into a plugin-local, per-platform vendor
# dir (siblings: vendor/macos_arm64 from tools/vendor_mac_deps.ps1). Versions
# are pinned so both platforms ship identical numpy/scipy.
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File tools\vendor_c4d_deps.ps1

$ErrorActionPreference = "Stop"

$repoRoot   = Split-Path -Parent $PSScriptRoot
# Per-platform layout: only clear THIS platform's dir, never the whole
# vendor/ root (which holds sibling platforms).
$vendorRoot = Join-Path $repoRoot "vendor\win_amd64"
$wheelhouse = Join-Path $repoRoot ".vendor_wheels"

$numpyVersion = "2.4.4"
$scipyVersion = "1.17.1"

if (Test-Path $vendorRoot) {
    Remove-Item $vendorRoot -Recurse -Force
}
if (Test-Path $wheelhouse) {
    Remove-Item $wheelhouse -Recurse -Force
}
New-Item -ItemType Directory -Path $vendorRoot -Force | Out-Null
New-Item -ItemType Directory -Path $wheelhouse | Out-Null

python -m pip download `
    --only-binary=:all: `
    --platform win_amd64 `
    --python-version 3.11 `
    --implementation cp `
    --abi cp311 `
    --dest $wheelhouse `
    "numpy==$numpyVersion" "scipy==$scipyVersion"

Get-ChildItem -Path $wheelhouse -Filter "*.whl" |
    ForEach-Object {
        Write-Host "Unpacking $($_.Name)"
        python -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" $_.FullName $vendorRoot
    }

# Keep the vendored tree focused on runtime imports.
Get-ChildItem -Path $vendorRoot -Recurse -Directory -Force -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
Get-ChildItem -Path $vendorRoot -Recurse -Directory -Force -Filter "tests" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

Remove-Item $wheelhouse -Recurse -Force

Write-Host "Vendored dependencies into: $vendorRoot"
