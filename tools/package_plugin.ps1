# Build a clean runtime-only Cubit plugin package for distribution.
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File tools\package_plugin.ps1
# Per-platform (separate Windows / Mac plugin zips):
#   powershell -ExecutionPolicy Bypass -File tools\package_plugin.ps1 -Platform win -Zip
#   powershell -ExecutionPolicy Bypass -File tools\package_plugin.ps1 -Platform mac -Zip
# -Platform all (default) bundles every platform's vendor in one zip.

param(
    [switch]$Zip,
    [ValidateSet("win", "mac", "all")]
    [string]$Platform = "all"
)

$ErrorActionPreference = "Stop"

$repoRoot      = Split-Path -Parent $PSScriptRoot
$pluginSource  = Join-Path $repoRoot "BrickGen"
$corePackage   = Join-Path $repoRoot "brick"
$distRoot      = Join-Path $repoRoot "dist"
# Per-platform builds get their own package dir + zip name so they don't clobber.
$packageName   = switch ($Platform) {
    "win" { "Cubit-Windows" }
    "mac" { "Cubit-macOS" }
    default { "Cubit" }
}
$packageRoot   = Join-Path $distRoot $packageName
$nativeGuiName = "bricklibrary.inline_gui"
$vendorSource  = Join-Path $repoRoot "vendor"

# Which vendor subdirs to include for each platform target.
$vendorSubdirs = switch ($Platform) {
    "win" { @("win_amd64") }
    "mac" { @("macos_arm64", "macos_x86_64") }
    default { @("win_amd64", "macos_arm64", "macos_x86_64") }
}

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

# Bundle only the requested platform(s)' vendored deps.
if (Test-Path $vendorSource) {
    $vendorDest = Join-Path $packageRoot "vendor"
    New-Item -ItemType Directory -Path $vendorDest -Force | Out-Null
    foreach ($sub in $vendorSubdirs) {
        $src = Join-Path $vendorSource $sub
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $vendorDest $sub) -Recurse -Force
            Write-Host "Bundled vendor/$sub"
        } elseif ($Platform -ne "all") {
            Write-Warning "vendor/$sub not found. Run the matching vendor script first (tools\vendor_$(if($Platform -eq 'mac'){'mac'}else{'c4d'})_deps.ps1)"
        }
    }
}

# The native GUI is a Windows-compiled C++ plugin (build-win64). It cannot run
# on macOS, so only bundle it for win/all targets. (The Python plugin degrades
# gracefully without it: the inline library panel just is not available.)
if ($Platform -ne "mac") {
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
    $zipPath = Join-Path $distRoot "$packageName.zip"
    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }
    Compress-Archive -Path $packageRoot -DestinationPath $zipPath -Force
    Write-Host "Wrote package zip: $zipPath"
}

Write-Host "Wrote runtime package: $packageRoot"
