# 75MAブレイクアウト + 新高値/新安値スキャナ (PowerShell単体版)
# 使い方:
#   pwsh -File scan_75ma.ps1
#
# 入力: scan_stocks.json (銘柄リスト)
# 出力: data/scan75ma.json

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

Write-Host "============================================"
Write-Host "  75MA Breakout / New High-Low Scanner"
Write-Host "============================================"

$scanStocksPath = Join-Path $root "scan_stocks.json"
if (-not (Test-Path $scanStocksPath)) {
    Write-Host "ERROR: scan_stocks.json not found"
    exit 1
}
$scanStocksJson = [System.IO.File]::ReadAllText($scanStocksPath, [System.Text.Encoding]::UTF8)
$scanStocks = ConvertFrom-Json $scanStocksJson

$startTime = Get-Date

# ---- Parallel fetch using RunspacePool ----
$fetchScript = {
    param($code, $name)
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        $url = "https://query1.finance.yahoo.com/v8/finance/chart/${code}.T?range=1y&interval=1d"
        $req = [System.Net.HttpWebRequest]::Create($url)
        $req.UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        $req.Timeout = 15000
        $resp = $req.GetResponse()
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8)
        $json = $reader.ReadToEnd()
        $reader.Close()
        $resp.Close()
        return @{ code = $code; name = $name; json = $json }
    } catch {
        return @{ code = $code; name = $name; json = "" }
    }
}

$pool = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspacePool(1, 30)
$pool.Open()
$jobs = @()

Write-Host "Submitting $($scanStocks.stocks.Count) fetch jobs (30 parallel)..."
foreach ($stock in $scanStocks.stocks) {
    $ps = [System.Management.Automation.PowerShell]::Create()
    $ps.RunspacePool = $pool
    [void]$ps.AddScript($fetchScript).AddArgument($stock.code).AddArgument($stock.name)
    $jobs += @{ ps = $ps; handle = $ps.BeginInvoke() }
}

$fetchResults = @()
foreach ($j in $jobs) {
    $r = $j.ps.EndInvoke($j.handle)
    $j.ps.Dispose()
    $fetchResults += $r
}
$pool.Close(); $pool.Dispose()

$fetchTime = ((Get-Date) - $startTime).TotalSeconds
Write-Host "  Fetched $($fetchResults.Count) stocks in $([Math]::Round($fetchTime,1))s"

# ---- Analyze ----
$breakouts = @()
$newHighs = @()
$newLows = @()

foreach ($r in $fetchResults) {
    $code = $r.code
    $name = $r.name
    $json = $r.json
    if (-not $json) { continue }

    try {
        $data = ConvertFrom-Json $json
        $result = $data.chart.result[0]
        $timestamps = $result.timestamp
        $closes = $result.indicators.quote[0].close
        $opens = $result.indicators.quote[0].open
        $highs = $result.indicators.quote[0].high
        $lows = $result.indicators.quote[0].low
        $volumes = $result.indicators.quote[0].volume

        if ($closes.Count -lt 76) { continue }

        $len = $closes.Count
        $todayClose = [double]$closes[$len - 1]
        $yesterdayClose = [double]$closes[$len - 2]
        $todayHigh = [double]$highs[$len - 1]
        $todayLow = [double]$lows[$len - 1]

        # New high / new low (1-year)
        $histHighs = @()
        $histLows = @()
        for ($i = 0; $i -lt $len - 1; $i++) {
            $h = $highs[$i]; $l = $lows[$i]
            if ($h -ne $null -and [double]$h -gt 0) { $histHighs += [double]$h }
            if ($l -ne $null -and [double]$l -gt 0) { $histLows += [double]$l }
        }
        $prevHighMax = if ($histHighs.Count -gt 0) { ($histHighs | Measure-Object -Maximum).Maximum } else { 0 }
        $prevLowMin = if ($histLows.Count -gt 0) { ($histLows | Measure-Object -Minimum).Minimum } else { 0 }
        $changeRatePct = [Math]::Round(($todayClose - $yesterdayClose) / $yesterdayClose * 100, 2)
        $rangeDays = $histHighs.Count
        $validData = ($todayHigh -gt 0) -and ($todayLow -gt 0) -and ($rangeDays -ge 200)

        if ($validData -and $prevHighMax -gt 0 -and $todayHigh -gt $prevHighMax) {
            $newHighs += [ordered]@{
                code       = $code; name = $name; close = $todayClose
                high       = $todayHigh; prevHigh = [Math]::Round($prevHighMax, 1)
                changeRate = $changeRatePct; rangeDays = $rangeDays
            }
        }
        if ($validData -and $prevLowMin -gt 0 -and $todayLow -lt $prevLowMin) {
            $newLows += [ordered]@{
                code       = $code; name = $name; close = $todayClose
                low        = $todayLow; prevLow = [Math]::Round($prevLowMin, 1)
                changeRate = $changeRatePct; rangeDays = $rangeDays
            }
        }

        # 75MA breakout
        $sum75 = 0.0
        for ($i = $len - 75; $i -lt $len; $i++) { $sum75 += [double]$closes[$i] }
        $ma75Today = $sum75 / 75.0

        $sum75prev = 0.0
        for ($i = $len - 76; $i -lt $len - 1; $i++) { $sum75prev += [double]$closes[$i] }
        $ma75Yesterday = $sum75prev / 75.0

        if ($yesterdayClose -le $ma75Yesterday -and $todayClose -gt $ma75Today) {
            $chartLen = [Math]::Min(90, $len)
            $startIdx = $len - $chartLen
            $chartDates = @(); $chartCloses = @(); $chartOpens = @()
            $chartHighs = @(); $chartLows = @(); $chartVolumes = @()
            $chartMa75 = @(); $chartMa25 = @()
            $epoch = New-Object DateTime(1970,1,1,0,0,0,[System.DateTimeKind]::Utc)

            for ($i = $startIdx; $i -lt $len; $i++) {
                $dt = $epoch.AddSeconds([long]$timestamps[$i]).AddHours(9)
                $chartDates += $dt.ToString("MM/dd")
                $chartCloses += [double]$closes[$i]
                $chartOpens += [double]$opens[$i]
                $chartHighs += [double]$highs[$i]
                $chartLows += [double]$lows[$i]
                $chartVolumes += [long]$volumes[$i]

                if ($i -ge 74) {
                    $maSum = 0.0
                    for ($j = $i - 74; $j -le $i; $j++) { $maSum += [double]$closes[$j] }
                    $chartMa75 += [Math]::Round($maSum / 75.0, 1)
                } else { $chartMa75 += $null }

                if ($i -ge 24) {
                    $maSum2 = 0.0
                    for ($j = $i - 24; $j -le $i; $j++) { $maSum2 += [double]$closes[$j] }
                    $chartMa25 += [Math]::Round($maSum2 / 25.0, 1)
                } else { $chartMa25 += $null }
            }

            $aboveMaRate = [Math]::Round(($todayClose - $ma75Today) / $ma75Today * 100, 2)

            $breakouts += [ordered]@{
                code        = $code; name = $name; close = $todayClose
                prevClose   = $yesterdayClose; ma75 = [Math]::Round($ma75Today, 1)
                changeRate  = $changeRatePct; aboveMaRate = $aboveMaRate
                volume      = [long]$volumes[$len - 1]; breakoutDay = 0
                chart       = [ordered]@{
                    dates   = $chartDates; closes = $chartCloses
                    ma75    = $chartMa75; ma25 = $chartMa25
                    volumes = $chartVolumes
                }
            }
        }
    } catch {
        Write-Host "    Parse error for ${code}: $($_.Exception.Message)"
    }
}

$totalTime = ((Get-Date) - $startTime).TotalSeconds
Write-Host "Scan complete in $([Math]::Round($totalTime,1))s. Breakouts=$($breakouts.Count), NewHighs=$($newHighs.Count), NewLows=$($newLows.Count)"

$resultObj = [ordered]@{
    lastUpdated = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
    count       = $breakouts.Count
    highCount   = $newHighs.Count
    lowCount    = $newLows.Count
    elapsedSec  = [Math]::Round($totalTime, 1)
    breakouts   = $breakouts
    newHighs    = $newHighs
    newLows     = $newLows
}

$dataDir = Join-Path $root "data"
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }

$outPath = Join-Path $dataDir "scan75ma.json"
$jsonStr = ConvertTo-Json $resultObj -Depth 6 -Compress
[System.IO.File]::WriteAllText($outPath, $jsonStr, [System.Text.UTF8Encoding]::new($true))

Write-Host "Saved: $outPath"
