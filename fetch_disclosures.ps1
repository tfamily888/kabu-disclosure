# TDnet適時開示情報 取得スクリプト (PowerShell単体版)
# 使い方:
#   powershell -ExecutionPolicy Bypass -File fetch_disclosures.ps1
#   powershell -ExecutionPolicy Bypass -File fetch_disclosures.ps1 -Date 20260426
#
# 出力: data/disclosures.json

param(
    [string]$Date = ""
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

# Date handling: default to today, else use specified
if (-not $Date) {
    $Date = (Get-Date).ToString("yyyyMMdd")
}
$Date = $Date -replace "-", ""
$isoDate = "$($Date.Substring(0,4))-$($Date.Substring(4,2))-$($Date.Substring(6,2))"

Write-Host "============================================"
Write-Host "  TDnet開示情報取得 ($isoDate)"
Write-Host "============================================"

# Load config
$cfgPath = Join-Path $root "config.json"
$cfgJson = [System.IO.File]::ReadAllText($cfgPath, [System.Text.Encoding]::UTF8)
$cfg = ConvertFrom-Json $cfgJson

# Load analysis rules (if available)
$rulesPath = Join-Path $root "analysis_rules.json"
$rules = $null
if (Test-Path $rulesPath) {
    $rulesJson = [System.IO.File]::ReadAllText($rulesPath, [System.Text.Encoding]::UTF8)
    $rules = ConvertFrom-Json $rulesJson
}

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

# ==================== Analysis / Classification ====================
function Get-Analysis($title) {
    if (-not $rules) { return @{ sentiment = "neutral"; comment = "" } }
    foreach ($p in $rules.negative.patterns) {
        if ($title.Contains($p.match)) { return @{ sentiment = "negative"; comment = $p.comment } }
    }
    foreach ($p in $rules.positive.patterns) {
        if ($title.Contains($p.match)) { return @{ sentiment = "positive"; comment = $p.comment } }
    }
    foreach ($p in $rules.neutral.patterns) {
        if ($title.Contains($p.match)) { return @{ sentiment = "neutral"; comment = $p.comment } }
    }
    foreach ($kw in $rules.negative.keywords) {
        if ($title.Contains($kw)) { return @{ sentiment = "negative"; comment = "" } }
    }
    foreach ($kw in $rules.positive.keywords) {
        if ($title.Contains($kw)) { return @{ sentiment = "positive"; comment = "" } }
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

# ==================== Fetch all pages ====================
Write-Host "`n[1/3] TDnetから開示一覧を取得中..."
$allItems = @()
for ($page = 1; $page -le 10; $page++) {
    Write-Host "  ページ $page を取得中..."
    $html = Fetch-TDnetPage $Date $page
    if (-not $html -or $html.Length -lt 100) {
        Write-Host "    -> 取得不可（次のページなし）"
        break
    }
    $items = Parse-TDnetHtml $html
    if ($items.Count -eq 0) {
        Write-Host "    -> 0件（終了）"
        break
    }
    $allItems += $items
    Write-Host "    -> $($items.Count) 件"
}

Write-Host "`n   全開示件数: $($allItems.Count) 件"

if ($allItems.Count -eq 0) {
    Write-Host "`n  開示情報が見つかりませんでした。"
    Write-Host "  ※ 市場休業日 / 早朝（開示前）/ TDnet構造変更の可能性があります。"
    Write-Host "  既存ファイルは保持します（上書きしません）。"
    $logPath = Join-Path $root "fetch_log.txt"
    $logLine = "{0} | date={1} | raw=0 | filtered=0 | 既存ファイル保持" -f `
        (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $isoDate
    Add-Content -Path $logPath -Value $logLine -Encoding UTF8
    exit 0
}

# ==================== Filter / Classify ====================
Write-Host "`n[2/3] 重要開示を抽出中..."
$filtered = @()
$idx = 0
foreach ($item in $allItems) {
    if (Should-Exclude $item.title) { continue }

    $category = Get-CategoryName $item.title
    $impLevel = Get-ImportanceLevel $item.title
    $impStr = switch ($impLevel) { "h" { [char]0x9AD8 } "m" { [char]0x4E2D } default { [char]0x4F4E } }

    if ($impLevel -eq "l" -and -not $category) { continue }
    if (-not $category) { $category = [string]([char]0x305D) + [string]([char]0x306E) + [string]([char]0x4ED6) }

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

Write-Host "   重要開示: $($filtered.Count) 件"

# ==================== Save JSON ====================
Write-Host "`n[3/3] JSON出力中..."
$dataDir = Join-Path $root "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
}

$result = [ordered]@{
    lastUpdated = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
    date        = $isoDate
    totalRaw    = $allItems.Count
    disclosures = $filtered
}
$jsonStr = ConvertTo-Json $result -Depth 5

$outPath = Join-Path $dataDir "disclosures.json"
[System.IO.File]::WriteAllText($outPath, $jsonStr, [System.Text.UTF8Encoding]::new($true))

Write-Host "   保存完了: $outPath"

# Log file (append-only, useful for debugging scheduled runs)
$logPath = Join-Path $root "fetch_log.txt"
$logLine = "{0} | date={1} | raw={2} | filtered={3}" -f `
    (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $isoDate, $allItems.Count, $filtered.Count
Add-Content -Path $logPath -Value $logLine -Encoding UTF8

Write-Host "`n============================================"
Write-Host "  完了: 全$($allItems.Count)件中 $($filtered.Count)件を保存"
Write-Host "============================================"
