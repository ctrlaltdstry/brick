# Deploy the BrickGen plugin to Cinema 4D's user plugins folder.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File tools\deploy_plugin.ps1

$ErrorActionPreference = "Stop"

$repoRoot   = Split-Path -Parent $PSScriptRoot
$source     = Join-Path $repoRoot "BrickGen"
$c4dPlugins = "C:\Users\Mike\AppData\Roaming\Maxon\Maxon Cinema 4D 2026_1ABCDC12\plugins"
$backupRoot = "C:\Users\Mike\AppData\Roaming\Maxon\Maxon Cinema 4D 2026_1ABCDC12\plugin_backups"
$target     = Join-Path $c4dPlugins "BrickGen"

if (-not (Test-Path $source)) {
    throw "Source plugin folder not found: $source"
}
if (-not (Test-Path $c4dPlugins)) {
    throw "C4D plugins folder not found: $c4dPlugins"
}
if (-not (Test-Path $backupRoot)) {
    New-Item -ItemType Directory -Path $backupRoot | Out-Null
}

Write-Host "Source: $source"
Write-Host "Target: $target"

# C4D loads every folder under plugins/* — relocate any old BrickGen/BrickGenerator backups
# siblings out of the plugins root so they do not double-register the plugin.
Get-ChildItem -Path $c4dPlugins -Directory -Filter "BrickGen.bak_*" |
    ForEach-Object {
        $dest = Join-Path $backupRoot $_.Name
        Write-Host "Relocating stale backup $($_.FullName) -> $dest"
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        Move-Item $_.FullName $dest
    }
Get-ChildItem -Path $c4dPlugins -Directory -Filter "BrickGenerator.bak_*" |
    ForEach-Object {
        $dest = Join-Path $backupRoot $_.Name
        Write-Host "Relocating stale backup $($_.FullName) -> $dest"
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        Move-Item $_.FullName $dest
    }

if (Test-Path (Join-Path $c4dPlugins "BrickGenerator")) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $legacyBak = Join-Path $backupRoot "BrickGenerator.legacy_$stamp"
    Write-Host "Relocating legacy target -> $legacyBak"
    Move-Item (Join-Path $c4dPlugins "BrickGenerator") $legacyBak
}

if (Test-Path $target) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $bak = Join-Path $backupRoot "BrickGen.bak_$stamp"
    Write-Host "Backing up existing target -> $bak"
    Move-Item $target $bak
}

Copy-Item -Path $source -Destination $target -Recurse -Force

# Strip pycache to force a fresh import on next C4D launch
Get-ChildItem -Path $target -Recurse -Directory -Filter "__pycache__" |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

Write-Host "Deployed. Restart Cinema 4D to pick up changes."
