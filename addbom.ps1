# Ensures key files have UTF-8 BOM so PowerShell reads Japanese correctly
$bom = New-Object System.Text.UTF8Encoding($true)
$files = @("server.ps1", "config.json", "analysis_rules.json", "scan_stocks.json", "fetch_disclosures.ps1")

foreach ($f in $files) {
    $p = Join-Path $PSScriptRoot $f
    if (Test-Path $p) {
        try {
            $c = [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)
            [System.IO.File]::WriteAllText($p, $c, $bom)
        } catch {
            Write-Host "Failed to add BOM to $f : $($_.Exception.Message)"
        }
    }
}

Write-Host "BOM added to critical files"
