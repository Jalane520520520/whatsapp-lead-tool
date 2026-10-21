$ErrorActionPreference = 'Stop'

$root = (Get-Location).Path
$out = Join-Path $root 'gosom_windows_fix/results'
New-Item -ItemType Directory -Force $out | Out-Null

git clone --quiet --depth 1 --branch v1.18.1 https://github.com/gosom/google-maps-scraper.git gosom-diag
git clone --quiet --depth 1 --branch v1.4.0 https://github.com/gosom/scrapemate.git scrapemate-diag
git clone --quiet --depth 1 --branch v1.18.1 https://github.com/gosom/google-maps-scraper.git gosom-fixed
git clone --quiet --depth 1 --branch v1.4.0 https://github.com/gosom/scrapemate.git scrapemate-fixed

git -C scrapemate-diag apply "$root/gosom_windows_fix/patches/diagnostic.patch"
git -C scrapemate-fixed apply "$root/gosom_windows_fix/patches/diagnostic.patch"
git -C scrapemate-fixed apply "$root/gosom_windows_fix/patches/isclosed.patch"

Push-Location gosom-diag
go mod edit "-replace=github.com/gosom/scrapemate=../scrapemate-diag"
go mod tidy
go build -o "$out/gosom-diag.exe" .
Pop-Location

Push-Location gosom-fixed
go mod edit "-replace=github.com/gosom/scrapemate=../scrapemate-fixed"
go mod tidy
go build -o "$out/gosom-fixed.exe" .
Pop-Location

Set-Content -Encoding utf8 "$out/query.txt" 'chinese supermarket'

function Run-Case {
    param([string]$Name, [string]$Exe, [int]$PagesPerBrowser)
    $csv = "$out/$Name.csv"
    $log = "$out/$Name.log"
    Remove-Item -Force -ErrorAction SilentlyContinue $csv
    $args = @(
        '-input', "$out/query.txt",
        '-results', $csv,
        '-grid-bbox', '51.49952,-0.12574,51.50853,-0.11127',
        '-grid-cell', '1',
        '-zoom', '17',
        '-depth', '2',
        '-c', '1',
        '-pages-per-browser', "$PagesPerBrowser",
        '-exit-on-inactivity', '2m'
    )
    & $Exe @args *>&1 | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
    $rows = @()
    if (Test-Path $csv) { $rows = @(Import-Csv $csv) }
    $clipped = @($rows | Where-Object {
        $lat = 0.0; $lon = 0.0
        [double]::TryParse($_.latitude, [ref]$lat) -and
        [double]::TryParse($_.longitude, [ref]$lon) -and
        $lat -ge 51.49952 -and $lat -le 51.50853 -and
        $lon -ge -0.12574 -and $lon -le -0.11127
    })
    $unexpected = ([regex]::Matches((Get-Content $log -Raw), 'unexpected page type')).Count
    $targetClosed = ([regex]::Matches((Get-Content $log -Raw), 'target closed')).Count
    $summary = [ordered]@{
        name = $Name
        pages_per_browser = $PagesPerBrowser
        exit_code = $exitCode
        raw_rows = $rows.Count
        clipped_rows = $clipped.Count
        unexpected_page_type = $unexpected
        target_closed = $targetClosed
    }
    $summary | ConvertTo-Json -Compress | Tee-Object -FilePath "$out/$Name.json"
}

Run-Case -Name 'diag-default' -Exe "$out/gosom-diag.exe" -PagesPerBrowser 1
Run-Case -Name 'diag-pages2' -Exe "$out/gosom-diag.exe" -PagesPerBrowser 2
Run-Case -Name 'fixed-default' -Exe "$out/gosom-fixed.exe" -PagesPerBrowser 1

Get-Content "$out/*.json" | Set-Content -Encoding utf8 "$out/summary.jsonl"
Get-Content "$out/summary.jsonl"
