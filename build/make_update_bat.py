"""Make a double-click update file (no internet needed) from a release's app.zip.
For clients whose network can't reach GitHub: the launcher's hot update fails silently there, so we hand them the same
app.zip inside a .bat. It does what launcher.update() does: check the files, check VERSION, unpack to
%LOCALAPPDATA%\\WhatsApp客户提取\\app\\<ver>, then write current.txt last.
Usage: python3 build/make_update_bat.py <app.zip> <out.bat>"""
import base64, sys, zipfile

zp, out = sys.argv[1:3]
with zipfile.ZipFile(zp) as z:
    ver = z.read("VERSION").decode().strip()
b64 = base64.b64encode(open(zp, "rb").read()).decode()
lines = "\n".join(b64[i:i + 76] for i in range(0, len(b64), 76))

PS = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$ver = '@VER@'
$home_ = Join-Path $env:LOCALAPPDATA 'WhatsApp客户提取'
$apps = Join-Path $home_ 'app'
function Done($ok, $msg) { Write-Host ''; Write-Host $msg; Write-Host ''; Read-Host '按回车键关闭这个窗口'; exit $(if ($ok) { 0 } else { 1 }) }
try {
  Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*WhatsAppLeadTool*' } | Stop-Process -Force -ErrorAction SilentlyContinue
  $t = Get-Content -Raw -Encoding UTF8 $env:WAT_BAT
  $a = $t.IndexOf('#PAYLOAD' + '-BEGIN') + 14; $b = $t.IndexOf('#PAYLOAD' + '-END')
  $bytes = [Convert]::FromBase64String(($t.Substring($a, $b - $a) -replace '\s', ''))
  $tmp = Join-Path $env:TEMP ('wat_upd_' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory $tmp | Out-Null
  $zip = Join-Path $tmp 'app.zip'; [IO.File]::WriteAllBytes($zip, $bytes)
  $stage = Join-Path $tmp 'x'; [IO.Compression.ZipFile]::ExtractToDirectory($zip, $stage)
  foreach ($m in 'app\server.py','app\window.html','app\main.py','app\pipeline.py','wa_check\check.js','VERSION') {
    if (-not (Test-Path (Join-Path $stage $m))) { throw "更新包缺少 $m" } }
  if ((Get-Content (Join-Path $stage 'VERSION') -Raw).Trim() -ne $ver) { throw '版本号对不上' }
  New-Item -ItemType Directory -Force $apps | Out-Null
  $dest = Join-Path $apps $ver
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  Move-Item $stage $dest
  [IO.File]::WriteAllText((Join-Path $apps 'current.txt'), $ver, (New-Object Text.UTF8Encoding $false))
  Remove-Item -Recurse -Force $tmp
  Done $true "更新完成：已更新到 $ver。`n现在从桌面重新打开「WhatsApp客户提取」，窗口右下角会显示 $ver。"
} catch {
  Done $false "更新没成功：$($_.Exception.Message)`n请把这个窗口截图发给我们。"
}
'''.replace("@VER@", ver)

bat = ('@echo off\r\n'
       'set "WAT_BAT=%~f0"\r\n'
       'powershell -NoProfile -ExecutionPolicy Bypass -Command "$t=Get-Content -Raw -Encoding UTF8 $env:WAT_BAT; '
       '$i=$t.IndexOf([string][char]35+\'PS-BEGIN\')+9; $j=$t.IndexOf([string][char]35+\'PS-END\'); '
       'Invoke-Expression $t.Substring($i,$j-$i)"\r\n'
       'exit /b\r\n'
       '#PS-BEGIN\r\n' + PS.replace("\n", "\r\n") + '#PS-END\r\n'
       '#PAYLOAD-BEGIN\r\n' + lines.replace("\n", "\r\n") + '\r\n#PAYLOAD-END\r\n')
open(out, "w", encoding="utf-8", newline="").write(bat)
print(f"wrote {out} for {ver}, {len(bat)} bytes")
