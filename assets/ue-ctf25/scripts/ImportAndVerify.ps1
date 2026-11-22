param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$Bridge = ''
)
# 导入事件包 -> 立即回读 -> 比对 CF_CNCV25_EVENTS 的 Base64。
# 通过只表示剪贴板内容与文件一致；Fusion 是否接受仍需粘贴验证。
$ErrorActionPreference = 'Stop'
if (-not $Bridge) { $Bridge = Join-Path $PSScriptRoot 'ClipboardBridge.ps1' }

function Load-EventBase64([string]$file) {
    $doc = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    $entry = @($doc.Formats | Where-Object { $_.Name -ceq 'CF_CNCV25_EVENTS' -and $_.Storage -eq 'HGLOBAL' })
    if ($entry.Count -ne 1) { throw "expected one CF_CNCV25_EVENTS in $file" }
    $bytes = [Convert]::FromBase64String($entry[0].Base64)
    if ($bytes.Length -eq 0 -or $bytes.Length -ne $entry[0].Length) {
        throw "invalid payload length in $file"
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($hash -ne $entry[0].SHA256) { throw "SHA256 mismatch in $file" }
    return [Convert]::ToBase64String($bytes)
}

$source = Load-EventBase64 (Resolve-Path -LiteralPath $Path)
& powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File $Bridge -Mode Import -Path (Resolve-Path -LiteralPath $Path) -FormatName CF_CNCV25_EVENTS
if ($LASTEXITCODE -ne 0) { throw "import failed ($LASTEXITCODE)" }

$dir = Split-Path -Parent (Resolve-Path -LiteralPath $Bridge)
$before = @(Get-ChildItem -LiteralPath $dir -Filter 'ctf-clipboard-*.json' -ErrorAction SilentlyContinue | ForEach-Object FullName)
& powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File $Bridge | Out-Null
if ($LASTEXITCODE -ne 0) { throw "export failed ($LASTEXITCODE)" }
$newFiles = @(Get-ChildItem -LiteralPath $dir -Filter 'ctf-clipboard-*.json' |
    Where-Object { $before -notcontains $_.FullName })
if ($newFiles.Count -ne 1) { throw "expected exactly one new export, found $($newFiles.Count)" }
$new = $newFiles[0]

$readback = Load-EventBase64 $new.FullName
if ($readback -ne $source) { throw "clipboard payload differs from $Path" }
Write-Host "PASS: clipboard matches $Path ($($new.Name))"
