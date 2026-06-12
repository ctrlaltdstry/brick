# Vendor macOS Cinema 4D 2026 Python dependencies into ./vendor/macos_<arch>.
#
# Cinema 4D 2026 uses CPython 3.11 on macOS too, so this downloads cp311
# macOS wheels and unpacks them into plugin-local, per-arch vendor dirs.
# Cross-downloading Mac binary wheels FROM WINDOWS works fine (pip just
# resolves by tag); no Mac is needed to fetch them. A real Mac IS needed to
# verify they actually load inside C4D's embedded Python.
#
# Versions are pinned to match the Windows tree (tools/vendor_c4d_deps.ps1)
# so both platforms ship identical numpy/scipy.
#
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File tools\vendor_mac_deps.ps1
# By default it fetches Apple Silicon (arm64). Add -Intel to also fetch x86_64.

param(
    [switch]$Intel
)

$ErrorActionPreference = "Stop"

$repoRoot   = Split-Path -Parent $PSScriptRoot
$vendorRoot = Join-Path $repoRoot "vendor"

$numpyVersion = "2.4.4"
$scipyVersion = "1.17.1"

if (-not (Test-Path $vendorRoot)) {
    New-Item -ItemType Directory -Path $vendorRoot | Out-Null
}

function Get-MacWheels {
    param(
        [string]$Arch,        # arm64 | x86_64
        [string]$SubdirName   # macos_arm64 | macos_x86_64
    )

    $target = Join-Path $vendorRoot $SubdirName
    $wheelhouse = Join-Path $repoRoot ".vendor_wheels_$SubdirName"

    # Only clear THIS arch's dirs — never the whole vendor/ root (which holds
    # sibling platforms).
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    if (Test-Path $wheelhouse) { Remove-Item $wheelhouse -Recurse -Force }
    New-Item -ItemType Directory -Path $target | Out-Null
    New-Item -ItemType Directory -Path $wheelhouse | Out-Null

    # --only-binary=:all: is mandatory when --platform/--abi are set.
    # macosx_12_0 satisfies both numpy (floor 11.0) and scipy (floor 12.0)
    # for cp311; pip matches any wheel whose min macOS <= the requested tag.
    Write-Host "Downloading macOS $Arch wheels (numpy==$numpyVersion, scipy==$scipyVersion)..."
    python -m pip download `
        --only-binary=:all: `
        --platform "macosx_12_0_$Arch" `
        --python-version 3.11 `
        --implementation cp `
        --abi cp311 `
        --dest $wheelhouse `
        "numpy==$numpyVersion" "scipy==$scipyVersion"

    Get-ChildItem -Path $wheelhouse -Filter "*.whl" |
        ForEach-Object {
            Write-Host "  Unpacking $($_.Name)"
            python -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" $_.FullName $target
        }

    # Trim to runtime imports only.
    Get-ChildItem -Path $target -Recurse -Directory -Force -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
    Get-ChildItem -Path $target -Recurse -Directory -Force -Filter "tests" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

    Remove-Item $wheelhouse -Recurse -Force
    Write-Host "Vendored macOS $Arch into: $target"
}

# Apple Silicon is the primary target.
Get-MacWheels -Arch "arm64" -SubdirName "macos_arm64"

if ($Intel) {
    Get-MacWheels -Arch "x86_64" -SubdirName "macos_x86_64"
}

Write-Host "Done. Mac vendor dirs are under: $vendorRoot"
