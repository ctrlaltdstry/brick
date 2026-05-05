# Deploy the Brick plugin to Cinema 4D's user plugins folder.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File tools\deploy_plugin.ps1

$ErrorActionPreference = "Stop"

$repoRoot      = Split-Path -Parent $PSScriptRoot
$source        = Join-Path $repoRoot "BrickGen"
$corePackage   = Join-Path $repoRoot "brick"
$vendorSource  = Join-Path $repoRoot "vendor"

# Discover the C4D 2026 instance folder dynamically. Each install gets its
# own per-machine hash (e.g. `Maxon Cinema 4D 2026_1ABCDC12` on this box,
# different on a friend's 2026.1.0 install). Honor BRICK_C4D_ROOT to override
# for unusual setups; otherwise pick the most recently modified 2026 instance.
if ($env:BRICK_C4D_ROOT -and (Test-Path $env:BRICK_C4D_ROOT)) {
    $c4dRoot = $env:BRICK_C4D_ROOT
} else {
    $maxonRoot = Join-Path $env:APPDATA "Maxon"
    $c4dInstances = @()
    if (Test-Path $maxonRoot) {
        $c4dInstances = Get-ChildItem -Path $maxonRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "Maxon Cinema 4D 2026*" } |
            Sort-Object LastWriteTime -Descending
    }
    if ($c4dInstances.Count -eq 0) {
        throw "No 'Maxon Cinema 4D 2026*' instance folder found under $maxonRoot. Set BRICK_C4D_ROOT to override."
    }
    $c4dRoot = $c4dInstances[0].FullName
    if ($c4dInstances.Count -gt 1) {
        Write-Host "Multiple C4D 2026 instances detected; using most recent: $($c4dInstances[0].Name)"
        Write-Host "  (others: $((($c4dInstances | Select-Object -Skip 1).Name) -join ', '))"
        Write-Host "  Set BRICK_C4D_ROOT to override."
    }
}
$c4dPlugins    = Join-Path $c4dRoot "plugins"
$backupRoot    = Join-Path $c4dRoot "plugin_backups"
$target        = Join-Path $c4dPlugins "Brick"
$targetCore    = Join-Path $target "brick"
$targetVendor  = Join-Path $target "vendor"
$nativeGuiName = "bricklibrary.inline_gui"
$targetNative  = Join-Path $target $nativeGuiName
$rootNative    = Join-Path $c4dPlugins $nativeGuiName

if (-not (Test-Path $source)) {
    throw "Source plugin folder not found: $source"
}
if (-not (Test-Path (Join-Path $corePackage "__init__.py"))) {
    throw "Core brick package not found: $corePackage"
}
if (-not (Test-Path $c4dPlugins)) {
    throw "C4D plugins folder not found: $c4dPlugins"
}
if (-not (Test-Path $backupRoot)) {
    New-Item -ItemType Directory -Path $backupRoot | Out-Null
}

Write-Host "Source: $source"
Write-Host "Target: $target"

function Move-PluginFolderToBackup {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if (-not (Test-Path $Path)) {
        return
    }

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $dest = Join-Path $backupRoot "$Label.bak_$stamp"
    Write-Host "Relocating $Path -> $dest"
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Move-Item $Path $dest
}

$nativeGuiSource = $null
$nativeGuiCandidates = @()
if ($env:BRICK_NATIVE_GUI_SOURCE) {
    $nativeGuiCandidates += $env:BRICK_NATIVE_GUI_SOURCE
}
$nativeGuiCandidates += "C:\Dev\c4d_sdk_2026\build-win64\bin\Release\plugins\$nativeGuiName"
$nativeGuiCandidates += $rootNative

foreach ($candidate in $nativeGuiCandidates) {
    if ($candidate -and (Test-Path $candidate)) {
        $nativeGuiSource = $candidate
        break
    }
}
if ($nativeGuiSource) {
    Write-Host "Native GUI source: $nativeGuiSource"
} else {
    Write-Host "Native GUI source not found; deploying Python plugin only."
}

# C4D loads every folder under plugins/*, so move stale siblings out of the
# plugins root before deploying to avoid duplicate plugin registration.
Get-ChildItem -Path $c4dPlugins -Directory |
    Where-Object {
        $_.Name -like "Brick.bak_*" -or
        $_.Name -like "BrickGen.bak_*" -or
        $_.Name -like "BrickGenerator.bak_*" -or
        $_.Name -like "$nativeGuiName.bak_*"
    } |
    ForEach-Object {
        $dest = Join-Path $backupRoot $_.Name
        Write-Host "Relocating stale backup $($_.FullName) -> $dest"
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        Move-Item $_.FullName $dest
    }

Move-PluginFolderToBackup -Path $target -Label "Brick"
Move-PluginFolderToBackup -Path (Join-Path $c4dPlugins "BrickGen") -Label "BrickGen"
Move-PluginFolderToBackup -Path (Join-Path $c4dPlugins "BrickGenerator") -Label "BrickGenerator"

Copy-Item -Path $source -Destination $target -Recurse -Force
Copy-Item -Path $corePackage -Destination $targetCore -Recurse -Force
if (Test-Path $vendorSource) {
    Copy-Item -Path $vendorSource -Destination $targetVendor -Recurse -Force
    Write-Host "Bundled vendor deps: $targetVendor"
}

# Bundle the user manual HTML alongside the plugin so the BrickGen / BrickIt
# "Open User Manual" button can serve it offline without a network round-trip.
$userManual = Join-Path $repoRoot "USER_MANUAL.html"
if (Test-Path $userManual) {
    Copy-Item -Path $userManual -Destination (Join-Path $target "USER_MANUAL.html") -Force
    Write-Host "Bundled user manual: $(Join-Path $target 'USER_MANUAL.html')"
}

# Strip pycache to force a fresh import on next C4D launch
Get-ChildItem -Path $target -Recurse -Directory -Filter "__pycache__" |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

if ($nativeGuiSource) {
    if (Test-Path $targetNative) {
        Remove-Item $targetNative -Recurse -Force
    }
    Copy-Item -Path $nativeGuiSource -Destination $targetNative -Recurse -Force
    Write-Host "Nested native GUI: $targetNative"
}

Move-PluginFolderToBackup -Path $rootNative -Label $nativeGuiName

Write-Host ""
Write-Host "Plugin root layout:"
Get-ChildItem -Path $c4dPlugins -Directory |
    Where-Object {
        $_.Name -eq "Brick" -or
        $_.Name -eq "BrickGen" -or
        $_.Name -eq "BrickGenerator" -or
        $_.Name -eq $nativeGuiName
    } |
    Select-Object -ExpandProperty FullName |
    ForEach-Object { Write-Host "  $_" }

Write-Host "Deployed. Restart Cinema 4D to pick up changes."
