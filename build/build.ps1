# 在 GitHub 的 Windows 机器上把所有零件装进 dist\pkg，再出 app.zip（热更新用）。PLAN v1.4 第 4 步。
# 每一步都写死版本号：客户电脑上的东西和我们测过的一模一样。
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'          # Invoke-WebRequest 的进度条会让下载慢很多
Set-Location (Split-Path $PSScriptRoot -Parent)   # 仓库根目录
$V   = (Get-Content VERSION -Raw).Trim()
$PKG = Join-Path $PWD 'dist\pkg'
$TMP = Join-Path $PWD 'dist\tmp'
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $PKG, $TMP | Out-Null
function Get($url, $out) { Write-Host "download $url"; Invoke-WebRequest $url -OutFile $out }

# 1. 便携 Python 3.11.9（python.org 官方 embeddable 包，解压即用，不写注册表）
Get 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' "$TMP\py.zip"
Expand-Archive "$TMP\py.zip" "$PKG\python"
# embeddable 版默认关掉 site-packages，打开它 pip 装的库才找得到
(Get-Content "$PKG\python\python311._pth") -replace '^#\s*import site', 'import site' | Set-Content "$PKG\python\python311._pth"
Get 'https://bootstrap.pypa.io/get-pip.py' "$TMP\get-pip.py"
& "$PKG\python\python.exe" "$TMP\get-pip.py" --no-warn-script-location
if ($LASTEXITCODE) { throw 'get-pip failed' }

# 2. Python 库（版本锁死，见 requirements.lock）
& "$PKG\python\python.exe" -m pip install --no-warn-script-location -r requirements.lock
if ($LASTEXITCODE) { throw 'pip install failed' }

# 3. 浏览器：用 playwright 装它自己要的那个 Chromium 版本，放进包里的 browsers\
$env:PLAYWRIGHT_BROWSERS_PATH = "$PKG\browsers"
& "$PKG\python\python.exe" -m playwright install chromium-headless-shell   # 查官网只用无界面版；完整版 432 MB 不装
if ($LASTEXITCODE) { throw 'playwright install failed' }

# 4. 便携 Node v24.22.0（nodejs.org 官方 zip）+ Baileys（npm ci 按 package-lock.json 装，版本和 Mac 上一样）
Get 'https://nodejs.org/dist/v24.22.0/node-v24.22.0-win-x64.zip' "$TMP\node.zip"
Expand-Archive "$TMP\node.zip" $TMP
Move-Item "$TMP\node-v24.22.0-win-x64" "$PKG\node"
Push-Location wa_check
& "$PKG\node\npm.cmd" ci --omit=dev
if ($LASTEXITCODE) { Pop-Location; throw 'npm ci failed' }
Pop-Location
Move-Item wa_check\node_modules "$PKG\node_modules"

# 5. gosom（谷歌地图）官方 Windows 版 v1.18.1
New-Item -ItemType Directory -Force "$PKG\gosom" | Out-Null
Get 'https://github.com/gosom/google-maps-scraper/releases/download/v1.18.1/google_maps_scraper-1.18.1-windows-amd64.exe' "$PKG\gosom\google_maps_scraper-1.18.1-windows-amd64.exe"

# 6. 出厂代码 + 启动器
$CODE = 'VERSION', 'app', 'maps', 'web', 'wa_check'
New-Item -ItemType Directory -Force "$PKG\app_builtin" | Out-Null
foreach ($c in $CODE) { Copy-Item -Recurse $c "$PKG\app_builtin\" }
# run_maps.py imports this sibling at process start. Keep the dependency explicit
# and fail before the expensive installer compression if packaging ever drops it.
New-Item -ItemType Directory -Force "$PKG\app_builtin\maps" | Out-Null
Copy-Item -Force "maps\playwright_maps.py" "$PKG\app_builtin\maps\playwright_maps.py"
if (-not (Test-Path "$PKG\app_builtin\maps\playwright_maps.py")) { throw 'playwright_maps.py missing from package' }
Remove-Item -Recurse -Force "$PKG\app_builtin\wa_check\node_modules" -ErrorAction SilentlyContinue
Copy-Item launcher.py "$PKG\"

# 7. app.zip（热更新包：只有代码，几百 KB）。用 Python 打 zip：旧版 PowerShell 的 Compress-Archive 会写成 \ 分隔，
#    启动器按 app/server.py 这种名字检查，所以统一用 /
& "$PKG\python\python.exe" -c "import os,sys,zipfile;r=sys.argv[1];z=zipfile.ZipFile(sys.argv[2],'w',zipfile.ZIP_DEFLATED);[z.write(os.path.join(d,f),os.path.relpath(os.path.join(d,f),r).replace(os.sep,'/')) for d,_,fs in os.walk(r) for f in fs if '__pycache__' not in d];z.close()" "$PKG\app_builtin" "$PWD\dist\app.zip"
if ($LASTEXITCODE) { throw 'app.zip failed' }

$size = (Get-ChildItem $PKG -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("pkg ready: v{0}, {1:N0} MB" -f $V, $size)
# 每个零件多大（找安装包太大的原因）
Get-ChildItem $PKG -Directory | ForEach-Object { '{0,8:N0} MB  {1}' -f ((Get-ChildItem $_.FullName -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), $_.Name }
Get-ChildItem "$PKG\python\Lib\site-packages" -Directory | ForEach-Object { [pscustomobject]@{MB=[math]::Round((Get-ChildItem $_.FullName -Recurse -File | Measure-Object Length -Sum).Sum / 1MB); Name=$_.Name} } | Sort-Object MB -Descending | Select-Object -First 15 | Format-Table -AutoSize | Out-String | Write-Host
Get-ChildItem "$PKG\browsers" -Directory | ForEach-Object { '{0,8:N0} MB  browsers\{1}' -f ((Get-ChildItem $_.FullName -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), $_.Name }
