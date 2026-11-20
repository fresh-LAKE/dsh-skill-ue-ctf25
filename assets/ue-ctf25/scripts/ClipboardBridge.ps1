param(
    [ValidateSet('Export','Import')][string]$Mode = 'Export',
    [string]$Path = "$PSScriptRoot\ctf-clipboard.json",
    [string[]]$FormatName
)
$ErrorActionPreference = 'Stop'
if ($Mode -eq 'Export') {
    $timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss-fff'
    $Path = Join-Path $PSScriptRoot "ctf-clipboard-$timestamp.json"
}
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class ClipNative {
 [DllImport("user32.dll", SetLastError=true)] public static extern bool OpenClipboard(IntPtr owner);
 [DllImport("user32.dll")] public static extern bool CloseClipboard();
 [DllImport("user32.dll", SetLastError=true)] public static extern uint EnumClipboardFormats(uint format);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClipboardFormatName(uint format, StringBuilder name, int count);
 [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr GetClipboardData(uint format);
 [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr SetClipboardData(uint format, IntPtr data);
 [DllImport("user32.dll", SetLastError=true)] public static extern bool EmptyClipboard();
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern uint RegisterClipboardFormat(string name);
 [DllImport("user32.dll", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr CreateWindowEx(uint ex, string cls, string name, uint style, int x, int y, int w, int h, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr param);
 [DllImport("user32.dll")] public static extern bool DestroyWindow(IntPtr window);
 [DllImport("kernel32.dll", SetLastError=true)] public static extern UIntPtr GlobalSize(IntPtr data);
 [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr GlobalLock(IntPtr data);
 [DllImport("kernel32.dll")] public static extern bool GlobalUnlock(IntPtr data);
 [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr GlobalAlloc(uint flags, UIntPtr size);
 [DllImport("kernel32.dll")] public static extern IntPtr GlobalFree(IntPtr data);
}
'@
function Open-Clip([IntPtr]$Owner) {
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if ([ClipNative]::OpenClipboard($Owner)) { return }
        Start-Sleep -Milliseconds 100
    }
    throw "OpenClipboard failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
}
if ($Mode -eq 'Export') {
    $rows = [Collections.Generic.List[object]]::new()
    Open-Clip ([IntPtr]::Zero)
    try {
        $ids = [Collections.Generic.List[uint32]]::new()
        [uint32]$id = 0
        while (($id = [ClipNative]::EnumClipboardFormats($id)) -ne 0) { $ids.Add($id) }
        foreach ($id in $ids) {
            $name = [Text.StringBuilder]::new(512)
            [void][ClipNative]::GetClipboardFormatName($id,$name,$name.Capacity)
            $row = [ordered]@{ Id=$id; Name=$name.ToString(); Storage=''; Length=0; SHA256=$null; Base64=$null }
            # Bitmap, palette, metafile and private/GDI handles are not raw HGLOBAL payloads.
            if (($id -ge 0xC000) -or ($id -in @(1,4,6,7,8,13,15,16,17))) {
                $handle = [ClipNative]::GetClipboardData($id)
                $size = [ClipNative]::GlobalSize($handle).ToUInt64()
                if ($handle -eq [IntPtr]::Zero -or $size -eq 0) {
                    $row.Storage = 'UnavailableOrNonHGlobal'
                } elseif ($size -gt 134217728) {
                    $row.Storage = 'SkippedOver128MiB'
                    $row.Length = $size
                } else {
                    $ptr = [ClipNative]::GlobalLock($handle)
                    if ($ptr -eq [IntPtr]::Zero) { $row.Storage = 'LockFailed' }
                    else {
                        try {
                            $bytes = New-Object byte[] ([int]$size)
                            [Runtime.InteropServices.Marshal]::Copy($ptr,$bytes,0,$bytes.Length)
                            $row.Storage = 'HGLOBAL'
                            $row.Length = $bytes.Length
                            $row.Base64 = [Convert]::ToBase64String($bytes)
                            $sha = [Security.Cryptography.SHA256]::Create()
                            try { $row.SHA256 = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
                            finally { $sha.Dispose() }
                        } finally { [void][ClipNative]::GlobalUnlock($handle) }
                    }
                }
            } else { $row.Storage = 'SkippedHandleFormat' }
            $rows.Add([pscustomobject]$row)
        }
    } finally { [void][ClipNative]::CloseClipboard() }
    $json = [ordered]@{ Version=1; CapturedAt=[DateTimeOffset]::Now.ToString('o'); Formats=@($rows.ToArray()) } |
        ConvertTo-Json -Depth 6
    $json | Out-File -LiteralPath $Path -Encoding UTF8 -NoClobber
    $rows | Select-Object Id,Name,Storage,Length | Format-Table -AutoSize
    Write-Host "Exported to: $Path"
} else {
    if (-not $FormatName) { throw 'Import requires -FormatName with the exact custom format name(s) to restore.' }
    $doc = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    $payloads = @()
    foreach ($requested in $FormatName) {
        $matches = @($doc.Formats | Where-Object { $_.Name -ceq $requested -and $_.Storage -eq 'HGLOBAL' -and $_.Id -ge 0xC000 })
        if ($matches.Count -ne 1) { throw "Missing or ambiguous HGLOBAL custom format: $requested" }
        $entry = $matches[0]
        $bytes = [Convert]::FromBase64String($entry.Base64)
        if ($bytes.Length -ne $entry.Length -or $bytes.Length -eq 0) { throw "Invalid payload size: $requested" }
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
        finally { $sha.Dispose() }
        if ($hash -ne $entry.SHA256) { throw "SHA256 mismatch: $requested" }
        $id = [ClipNative]::RegisterClipboardFormat($entry.Name)
        if ($id -eq 0) { throw 'RegisterClipboardFormat failed' }
        $payloads += [pscustomobject]@{ Id=$id; Bytes=$bytes; Name=$entry.Name }
    }
    $window = [ClipNative]::CreateWindowEx(0,'STATIC','ClipboardBridge',0,0,0,0,0,[IntPtr]::Zero,[IntPtr]::Zero,[IntPtr]::Zero,[IntPtr]::Zero)
    if ($window -eq [IntPtr]::Zero) { throw 'Unable to create clipboard owner window' }
    try {
        Open-Clip $window
        try {
            if (-not [ClipNative]::EmptyClipboard()) { throw 'EmptyClipboard failed' }
            foreach ($payload in $payloads) {
                $handle = [ClipNative]::GlobalAlloc(0x42,[UIntPtr]::new([uint64]$payload.Bytes.Length))
                if ($handle -eq [IntPtr]::Zero) { throw 'GlobalAlloc failed; clipboard may be partially restored' }
                try {
                    $ptr = [ClipNative]::GlobalLock($handle)
                    if ($ptr -eq [IntPtr]::Zero) { throw 'GlobalLock failed' }
                    try { [Runtime.InteropServices.Marshal]::Copy($payload.Bytes,0,$ptr,$payload.Bytes.Length) }
                    finally { [void][ClipNative]::GlobalUnlock($handle) }
                    if ([ClipNative]::SetClipboardData($payload.Id,$handle) -eq [IntPtr]::Zero) { throw 'SetClipboardData failed' }
                    $handle = [IntPtr]::Zero
                    Write-Host "Restored: $($payload.Name)"
                } finally { if ($handle -ne [IntPtr]::Zero) { [void][ClipNative]::GlobalFree($handle) } }
            }
        } finally { [void][ClipNative]::CloseClipboard() }
    } finally { [void][ClipNative]::DestroyWindow($window) }
}
