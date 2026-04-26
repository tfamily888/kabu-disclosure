[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Try multiple ports for reliability across PC restarts
$portCandidates = if ($env:PORT) { @($env:PORT) } else { @("7777", "7778", "7779", "7780", "5500", "8800") }
$listener = $null
$port = $null

foreach ($p in $portCandidates) {
    try {
        $l = New-Object System.Net.HttpListener
        $l.Prefixes.Add("http://localhost:${p}/")
        $l.Start()
        $listener = $l
        $port = $p
        break
    } catch {
        Write-Host "Port ${p} unavailable, trying next..."
        if ($l) { try { $l.Close() } catch {} }
    }
}

if (-not $listener) {
    Write-Host ""
    Write-Host "ERROR: Could not start server on any available port."
    Write-Host "Please restart your PC or run as Administrator."
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "============================================"
Write-Host "  Server running at http://localhost:${port}/"
Write-Host "  Browser: http://localhost:${port}/"
Write-Host "============================================"
Write-Host ""

# Save current port so browser shortcut / frontend can find it (no BOM)
try {
    $portFile = Join-Path $PSScriptRoot "current_port.txt"
    [System.IO.File]::WriteAllText($portFile, $port, (New-Object System.Text.ASCIIEncoding))
} catch {}

$mime = @{
    ".html" = "text/html; charset=utf-8"
    ".css"  = "text/css; charset=utf-8"
    ".js"   = "application/javascript; charset=utf-8"
    ".json" = "application/json; charset=utf-8"
    ".png"  = "image/png"
    ".jpg"  = "image/jpeg"
    ".svg"  = "image/svg+xml"
    ".ico"  = "image/x-icon"
}

$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

# Load configs
$cfgPath = Join-Path $root "config.json"
$cfgJson = [System.IO.File]::ReadAllText($cfgPath, [System.Text.Encoding]::UTF8)
$cfg = ConvertFrom-Json $cfgJson

$rulesPath = Join-Path $root "analysis_rules.json"
$rulesJson = [System.IO.File]::ReadAllText($rulesPath, [System.Text.Encoding]::UTF8)
$rules = ConvertFrom-Json $rulesJson

# Major stock list for 75MA scanner (Nikkei 225 subset + popular)
$scanStocksPath = Join-Path $root "scan_stocks.json"
$scanStocksJson = [System.IO.File]::ReadAllText($scanStocksPath, [System.Text.Encoding]::UTF8)
$scanStocks = ConvertFrom-Json $scanStocksJson

# ==================== TDnet Fetch ====================
function Fetch-TDnetPage($dateStr, $page) {
    $url = "https://www.release.tdnet.info/inbs/I_list_{0:D3}_$dateStr.html" -f $page
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        $req = [System.Net.HttpWebRequest]::Create($url)
        $req.UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        $req.Referer = "https://www.release.tdnet.info/inbs/I_main_00.html"
        $req.Timeout = 15000
        $resp = $req.GetResponse()
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8)
        $html = $reader.ReadToEnd()
        $reader.Close()
        $resp.Close()
        return $html
    } catch {
        return ""
    }
}

function Parse-TDnetHtml($html) {
    $results = @()
    $lines = $html -split "`n"
    $time = ""; $code = ""; $company = ""; $title = ""; $pdfUrl = ""; $market = ""

    foreach ($line in $lines) {
        if ($line -match 'kjTime"[^>]*>(\d{1,2}:\d{2})<') {
            $time = $Matches[1]
        }
        elseif ($line -match 'kjCode"[^>]*>(\d+)<') {
            $code = $Matches[1].Trim()
            if ($code.Length -eq 5) { $code = $code.Substring(0, 4) }
        }
        elseif ($line -match 'kjName"[^>]*>([^<]+)<') {
            $company = $Matches[1].Trim()
        }
        elseif ($line -match 'kjTitle"[^>]*><a href="([^"]+)"[^>]*>([^<]+)</a>') {
            $pdfUrl = "https://www.release.tdnet.info/inbs/" + $Matches[1]
            $title = $Matches[2].Trim()
        }
        elseif ($line -match 'kjTitle"[^>]*>([^<]+)<') {
            $pdfUrl = ""
            $title = $Matches[1].Trim()
        }
        elseif ($line -match 'kjPlace"[^>]*>([^<]*)<') {
            $market = $Matches[1].Trim()
            if ($time -and $code -and $company -and $title) {
                $results += @{
                    time    = $time
                    code    = $code
                    company = $company
                    title   = $title
                    pdfUrl  = $pdfUrl
                    market  = $market
                }
            }
            $time = ""; $code = ""; $company = ""; $title = ""; $pdfUrl = ""; $market = ""
        }
    }
    return $results
}

# ==================== Analysis ====================
function Get-Analysis($title) {
    # Check negative first (risk-first)
    foreach ($p in $rules.negative.patterns) {
        if ($title.Contains($p.match)) {
            return @{ sentiment = "negative"; comment = $p.comment }
        }
    }
    # Check positive
    foreach ($p in $rules.positive.patterns) {
        if ($title.Contains($p.match)) {
            return @{ sentiment = "positive"; comment = $p.comment }
        }
    }
    # Check neutral
    foreach ($p in $rules.neutral.patterns) {
        if ($title.Contains($p.match)) {
            return @{ sentiment = "neutral"; comment = $p.comment }
        }
    }
    # Fallback keyword check
    foreach ($kw in $rules.negative.keywords) {
        if ($title.Contains($kw)) {
            return @{ sentiment = "negative"; comment = "" }
        }
    }
    foreach ($kw in $rules.positive.keywords) {
        if ($title.Contains($kw)) {
            return @{ sentiment = "positive"; comment = "" }
        }
    }
    return @{ sentiment = "neutral"; comment = "" }
}

function Get-CategoryName($title) {
    foreach ($prop in $cfg.categories.PSObject.Properties) {
        foreach ($kw in $prop.Value) {
            if ($title.Contains($kw)) { return $prop.Name }
        }
    }
    return $null
}

function Get-ImportanceLevel($title) {
    foreach ($kw in $cfg.highImportance) {
        if ($title.Contains($kw)) { return "h" }
    }
    foreach ($kw in $cfg.mediumImportance) {
        if ($title.Contains($kw)) { return "m" }
    }
    return "l"
}

function Should-Exclude($title) {
    foreach ($kw in $cfg.excludes) {
        if ($title.Contains($kw)) { return $true }
    }
    return $false
}

# ==================== TDnet API Handler ====================
function Handle-TDnetApi($dateStr) {
    $allItems = @()
    for ($page = 1; $page -le 10; $page++) {
        Write-Host "  Fetching page $page..."
        $html = Fetch-TDnetPage $dateStr $page
        if (-not $html -or $html.Length -lt 100) { break }
        $items = Parse-TDnetHtml $html
        if ($items.Count -eq 0) { break }
        $allItems += $items
        Write-Host "    -> $($items.Count) items"
    }

    $filtered = @()
    $idx = 0
    foreach ($item in $allItems) {
        if (Should-Exclude $item.title) { continue }

        $category = Get-CategoryName $item.title
        $impLevel = Get-ImportanceLevel $item.title
        $impStr = switch ($impLevel) { "h" { [char]0x9AD8 } "m" { [char]0x4E2D } default { [char]0x4F4E } }

        if ($impLevel -eq "l" -and -not $category) { continue }
        if (-not $category) { $category = [string]([char]0x305D) + [string]([char]0x306E) + [string]([char]0x4ED6) }

        # Get analysis
        $analysis = Get-Analysis $item.title

        $idx++
        $filtered += [ordered]@{
            id         = "d$($idx.ToString('D4'))"
            time       = $item.time
            code       = $item.code
            company    = $item.company
            title      = $item.title
            pdfUrl     = $item.pdfUrl
            market     = $item.market
            category   = $category
            importance = [string]$impStr
            summary    = "$($item.company) - $($item.title)"
            earnings   = $null
            sentiment  = $analysis.sentiment
            analysis   = $analysis.comment
        }
    }

    $isoDate = "$($dateStr.Substring(0,4))-$($dateStr.Substring(4,2))-$($dateStr.Substring(6,2))"
    $result = [ordered]@{
        lastUpdated = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
        date        = $isoDate
        totalRaw    = $allItems.Count
        disclosures = $filtered
    }
    return (ConvertTo-Json $result -Depth 5 -Compress)
}

# ==================== Yahoo Finance Fetch ====================
function Fetch-YahooChart($symbol) {
    $url = "https://query1.finance.yahoo.com/v8/finance/chart/${symbol}.T?range=6mo&interval=1d"
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        $req = [System.Net.HttpWebRequest]::Create($url)
        $req.UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        $req.Timeout = 10000
        $resp = $req.GetResponse()
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8)
        $json = $reader.ReadToEnd()
        $reader.Close()
        $resp.Close()
        return $json
    } catch {
        Write-Host "    Yahoo fetch error for ${symbol}: $($_.Exception.Message)"
        return ""
    }
}

# ==================== 75MA Scanner API (parallel + cache) ====================
$script:scanCache = $null
$script:scanCacheDate = ""

function Handle-ScanApi {
    # Check cache (valid for current trading day)
    $today = (Get-Date).ToString("yyyyMMdd")
    if ($script:scanCache -and $script:scanCacheDate -eq $today) {
        Write-Host "Returning cached scan result."
        return $script:scanCache
    }

    Write-Host "Starting 75MA breakout scan (parallel)..."
    $startTime = Get-Date

    # Parallel fetch using RunspacePool (10 concurrent)
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

    foreach ($stock in $scanStocks.stocks) {
        $ps = [System.Management.Automation.PowerShell]::Create()
        $ps.RunspacePool = $pool
        [void]$ps.AddScript($fetchScript).AddArgument($stock.code).AddArgument($stock.name)
        $jobs += @{ ps = $ps; handle = $ps.BeginInvoke() }
    }

    # Collect results
    $fetchResults = @()
    foreach ($j in $jobs) {
        $r = $j.ps.EndInvoke($j.handle)
        $j.ps.Dispose()
        $fetchResults += $r
    }
    $pool.Close(); $pool.Dispose()

    $fetchTime = ((Get-Date) - $startTime).TotalSeconds
    Write-Host "  Fetched $($fetchResults.Count) stocks in $([Math]::Round($fetchTime,1))s"

    # Analyze in parallel too
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

            # ---- 新高値/新安値 (1-year) ----
            # Use close prices for robustness (filter out null/0/unreasonable values)
            $histHighs = @()
            $histLows = @()
            for ($i = 0; $i -lt $len - 1; $i++) {
                $h = $highs[$i]; $l = $lows[$i]; $c = $closes[$i]
                if ($h -ne $null -and [double]$h -gt 0) { $histHighs += [double]$h }
                if ($l -ne $null -and [double]$l -gt 0) { $histLows += [double]$l }
            }
            $prevHighMax = if ($histHighs.Count -gt 0) { ($histHighs | Measure-Object -Maximum).Maximum } else { 0 }
            $prevLowMin = if ($histLows.Count -gt 0) { ($histLows | Measure-Object -Minimum).Minimum } else { 0 }

            $changeRatePct = [Math]::Round(($todayClose - $yesterdayClose) / $yesterdayClose * 100, 2)
            $rangeDays = $histHighs.Count

            # Require valid today values and enough history (>=200 days ~ 10 months)
            $validData = ($todayHigh -gt 0) -and ($todayLow -gt 0) -and ($rangeDays -ge 200)

            if ($validData -and $prevHighMax -gt 0 -and $todayHigh -gt $prevHighMax) {
                Write-Host "    NEW HIGH! $code $name (${todayHigh} > ${prevHighMax})"
                $newHighs += [ordered]@{
                    code       = $code
                    name       = $name
                    close      = $todayClose
                    high       = $todayHigh
                    prevHigh   = [Math]::Round($prevHighMax, 1)
                    changeRate = $changeRatePct
                    rangeDays  = $rangeDays
                }
            }
            if ($validData -and $prevLowMin -gt 0 -and $todayLow -lt $prevLowMin) {
                Write-Host "    NEW LOW! $code $name (${todayLow} < ${prevLowMin})"
                $newLows += [ordered]@{
                    code       = $code
                    name       = $name
                    close      = $todayClose
                    low        = $todayLow
                    prevLow    = [Math]::Round($prevLowMin, 1)
                    changeRate = $changeRatePct
                    rangeDays  = $rangeDays
                }
            }

            # ---- 75MA breakout ----
            $sum75 = 0.0
            for ($i = $len - 75; $i -lt $len; $i++) { $sum75 += [double]$closes[$i] }
            $ma75Today = $sum75 / 75.0

            $sum75prev = 0.0
            for ($i = $len - 76; $i -lt $len - 1; $i++) { $sum75prev += [double]$closes[$i] }
            $ma75Yesterday = $sum75prev / 75.0

            $breakoutDay = -1
            if ($yesterdayClose -le $ma75Yesterday -and $todayClose -gt $ma75Today) {
                $breakoutDay = 0
            }

            if ($breakoutDay -eq 0) {
                Write-Host "    BREAKOUT today! $code $name"

                # Build chart data (last 90 days or available)
                $chartLen = [Math]::Min(90, $len)
                $startIdx = $len - $chartLen

                $chartDates = @()
                $chartCloses = @()
                $chartOpens = @()
                $chartHighs = @()
                $chartLows = @()
                $chartVolumes = @()
                $chartMa75 = @()

                $epoch = New-Object DateTime(1970,1,1,0,0,0,[System.DateTimeKind]::Utc)
                for ($i = $startIdx; $i -lt $len; $i++) {
                    $dt = $epoch.AddSeconds([long]$timestamps[$i]).AddHours(9)
                    $chartDates += $dt.ToString("MM/dd")
                    $chartCloses += [double]$closes[$i]
                    $chartOpens += [double]$opens[$i]
                    $chartHighs += [double]$highs[$i]
                    $chartLows += [double]$lows[$i]
                    $chartVolumes += [long]$volumes[$i]

                    # Calculate MA75 at this point
                    if ($i -ge 74) {
                        $maSum = 0.0
                        for ($j = $i - 74; $j -le $i; $j++) {
                            $maSum += [double]$closes[$j]
                        }
                        $chartMa75 += [Math]::Round($maSum / 75.0, 1)
                    } else {
                        $chartMa75 += $null
                    }
                }

                # Calculate 25MA too
                $chartMa25 = @()
                for ($i = $startIdx; $i -lt $len; $i++) {
                    if ($i -ge 24) {
                        $maSum = 0.0
                        for ($j = $i - 24; $j -le $i; $j++) {
                            $maSum += [double]$closes[$j]
                        }
                        $chartMa25 += [Math]::Round($maSum / 25.0, 1)
                    } else {
                        $chartMa25 += $null
                    }
                }

                $changeRate = [Math]::Round(($todayClose - $yesterdayClose) / $yesterdayClose * 100, 2)
                $aboveMaRate = [Math]::Round(($todayClose - $ma75Today) / $ma75Today * 100, 2)

                $breakouts += [ordered]@{
                    code        = $code
                    name        = $name
                    close       = $todayClose
                    prevClose   = $yesterdayClose
                    ma75        = [Math]::Round($ma75Today, 1)
                    changeRate  = $changeRate
                    aboveMaRate = $aboveMaRate
                    volume      = [long]$volumes[$len - 1]
                    breakoutDay = $breakoutDay
                    chart       = [ordered]@{
                        dates   = $chartDates
                        closes  = $chartCloses
                        ma75    = $chartMa75
                        ma25    = $chartMa25
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

    $result = [ordered]@{
        lastUpdated  = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
        count        = $breakouts.Count
        highCount    = $newHighs.Count
        lowCount     = $newLows.Count
        elapsedSec   = [Math]::Round($totalTime, 1)
        breakouts    = $breakouts
        newHighs     = $newHighs
        newLows      = $newLows
    }
    $jsonResult = (ConvertTo-Json $result -Depth 6 -Compress)

    # Cache for today
    $script:scanCache = $jsonResult
    $script:scanCacheDate = (Get-Date).ToString("yyyyMMdd")

    return $jsonResult
}

# Helper: write response with no-cache headers
function Write-Response {
    param($ctx, $bytes, $contentType, [int]$status = 200)
    $ctx.Response.ContentType = $contentType
    $ctx.Response.Headers.Add("Cache-Control", "no-cache, no-store, must-revalidate")
    $ctx.Response.Headers.Add("Pragma", "no-cache")
    $ctx.Response.Headers.Add("Expires", "0")
    $ctx.Response.Headers.Add("Access-Control-Allow-Origin", "*")
    $ctx.Response.StatusCode = $status
    $ctx.Response.ContentLength64 = $bytes.Length
    $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $ctx.Response.Close()
}

# ==================== Main Request Loop ====================
while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $reqPath = $ctx.Request.Url.LocalPath
    $query = $ctx.Request.Url.Query

    # API: TDnet disclosures (always fresh)
    if ($reqPath -eq "/api/tdnet") {
        $dateParam = ""
        if ($query -match "date=(\d{8})") { $dateParam = $Matches[1] }
        if (-not $dateParam) { $dateParam = (Get-Date).ToString("yyyyMMdd") }

        Write-Host "API request: TDnet data for $dateParam"
        $jsonStr = Handle-TDnetApi $dateParam
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonStr)
        Write-Response $ctx $bytes "application/json; charset=utf-8"
        continue
    }

    # API: 75MA breakout scan (supports force=1 to bypass cache)
    if ($reqPath -eq "/api/scan75ma") {
        if ($query -match "force=1") {
            Write-Host "API request: 75MA scan (force refresh - clearing cache)"
            $script:scanCache = $null
            $script:scanCacheDate = ""
        } else {
            Write-Host "API request: 75MA breakout scan"
        }
        $jsonStr = Handle-ScanApi
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonStr)
        Write-Response $ctx $bytes "application/json; charset=utf-8"
        continue
    }

    # Static files (with no-cache so updates show immediately)
    if ($reqPath -eq "/") { $reqPath = "/index.html" }
    $reqPath = $reqPath -replace "\?.*$", ""
    $filePath = Join-Path $root $reqPath.TrimStart("/").Replace("/", "\")

    if (Test-Path $filePath -PathType Leaf) {
        $ext = [System.IO.Path]::GetExtension($filePath)
        $contentType = if ($mime.ContainsKey($ext)) { $mime[$ext] } else { "application/octet-stream" }
        $bytes = [System.IO.File]::ReadAllBytes($filePath)
        Write-Response $ctx $bytes $contentType
    } else {
        $notFoundBytes = [System.Text.Encoding]::UTF8.GetBytes("Not Found")
        Write-Response $ctx $notFoundBytes "text/plain" 404
    }
}
