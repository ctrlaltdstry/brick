# Stop Cinema 4D, switch to Desktop 1, and reopen the test scene there.
$ErrorActionPreference = "SilentlyContinue"

$kbSrc = @'
using System;
using System.Runtime.InteropServices;
public static class Kb {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
}
'@
Add-Type -TypeDefinition $kbSrc -ErrorAction SilentlyContinue

$VK_LCONTROL = 0xA2
$VK_LWIN     = 0x5B
$VK_LEFT     = 0x25
$KEYUP       = 0x0002

function Send-CtrlWinLeft {
    [Kb]::keybd_event($VK_LCONTROL, 0, 0, [UIntPtr]::Zero)
    [Kb]::keybd_event($VK_LWIN,     0, 0, [UIntPtr]::Zero)
    [Kb]::keybd_event($VK_LEFT,     0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 60
    [Kb]::keybd_event($VK_LEFT,     0, $KEYUP, [UIntPtr]::Zero)
    [Kb]::keybd_event($VK_LWIN,     0, $KEYUP, [UIntPtr]::Zero)
    [Kb]::keybd_event($VK_LCONTROL, 0, $KEYUP, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 250
}

# Kill C4D
$procs = Get-Process -Name 'Cinema 4D*' -ErrorAction SilentlyContinue
if ($procs) { $procs | Stop-Process -Force }
Start-Sleep -Milliseconds 700

# Hop to Desktop 1 (send the shortcut a few times to ensure we're at the leftmost desktop).
Send-CtrlWinLeft
Send-CtrlWinLeft
Send-CtrlWinLeft

# Re-open test scene (Windows will launch C4D on the currently active desktop).
Start-Process -FilePath 'Z:\02_MKE\2026\BRICK\TEST FILE.c4d'
