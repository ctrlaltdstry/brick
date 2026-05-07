# Build a clean runtime-only Brick plugin package for distribution.
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File tools\package_plugin.ps1
# Optional zip:
#   powershell -ExecutionPolicy Bypass -File tools\package_plugin.ps1 -Zip

param(
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

$repoRoot      = Split-Path -Parent $PSScriptRoot
$pluginSource  = Join-Path $repoRoot "BrickGen"
$corePackage   = Join-Path $repoRoot "brick"
$distRoot      = Join-Path $repoRoot "dist"
$packageRoot   = Join-Path $distRoot "Brick"
$nativeGuiName = "bricklibrary.inline_gui"
$vendorSource  = Join-Path $repoRoot "vendor"

if (-not (Test-Path (Join-Path $pluginSource "c4d_brick_generator.pyp"))) {
    throw "Plugin source not found: $pluginSource"
}
if (-not (Test-Path (Join-Path $corePackage "__init__.py"))) {
    throw "Core brick package not found: $corePackage"
}

if (Test-Path $packageRoot) {
    Remove-Item $packageRoot -Recurse -Force
}
if (-not (Test-Path $distRoot)) {
    New-Item -ItemType Directory -Path $distRoot | Out-Null
}

Copy-Item -Path $pluginSource -Destination $packageRoot -Recurse -Force
Copy-Item -Path $corePackage -Destination (Join-Path $packageRoot "brick") -Recurse -Force

if (Test-Path $vendorSource) {
    Copy-Item -Path $vendorSource -Destination (Join-Path $packageRoot "vendor") -Recurse -Force
}

$nativeGuiCandidates = @()
if ($env:BRICK_NATIVE_GUI_SOURCE) {
    $nativeGuiCandidates += $env:BRICK_NATIVE_GUI_SOURCE
}
$nativeGuiCandidates += "C:\Dev\c4d_sdk_2026\build-win64\bin\Release\plugins\$nativeGuiName"

foreach ($candidate in $nativeGuiCandidates) {
    if ($candidate -and (Test-Path $candidate)) {
        Copy-Item -Path $candidate -Destination (Join-Path $packageRoot $nativeGuiName) -Recurse -Force
        Write-Host "Included native GUI: $candidate"
        break
    }
}

$readme = Join-Path $repoRoot "README_INSTALL.md"
if (Test-Path $readme) {
    Copy-Item -Path $readme -Destination (Join-Path $packageRoot "README_INSTALL.md") -Force
}

# Bundle the user manual so the in-AM "Open User Manual" button can serve
# it offline. The Python button handler looks for USER_MANUAL.html next to
# the plugin first and falls back to the canonical GitHub URL otherwise.
$userManual = Join-Path $repoRoot "USER_MANUAL.html"
if (Test-Path $userManual) {
    Copy-Item -Path $userManual -Destination (Join-Path $packageRoot "USER_MANUAL.html") -Force
}

# Strip development/generated content from the runtime package.
$directoryFilters = @(
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".cursor",
    ".claude",
    "tools",
    "tests",
    "backup",
    "demo",
    "docs",
    "output",
    "output_alt",
    "output_greedy",
    "output_uniform"
)

foreach ($filter in $directoryFilters) {
    Get-ChildItem -Path $packageRoot -Recurse -Directory -Force -Filter $filter -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
}

$fileFilters = @("*.pyc", "*.pyo", "*.log", "*.tmp", "*.bak", "*.pdb")
foreach ($filter in $fileFilters) {
    Get-ChildItem -Path $packageRoot -Recurse -File -Force -Filter $filter -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Force }
}

if ($Zip) {
    $zipPath = Join-Path $distRoot "Brick.zip"
    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }
    Compress-Archive -Path $packageRoot -DestinationPath $zipPath -Force
    Write-Host "Wrote package zip: $zipPath"
}

Write-Host "Wrote runtime package: $packageRoot"
