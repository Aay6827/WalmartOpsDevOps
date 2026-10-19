param([int]$MaxWaitSeconds = 360)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$prom = 'http://localhost:30001'
$log = New-Object System.Collections.Generic.List[string]

function Note($msg, $color = 'Gray') {
    $line = "[{0}] {1}" -f (Get-Date).ToString('HH:mm:ss'), $msg
    $log.Add($line)
    Write-Host $line -ForegroundColor $color
}
function Fmt($v) { if ($null -eq $v) { 'n/a' } else { '{0:N3}' -f $v } }
function PromValue($q) {
    try {
        $r = Invoke-RestMethod ("{0}/api/v1/query?query={1}" -f $prom, [uri]::EscapeDataString($q))
        if ($r.data.result.Count -gt 0) { return [double]$r.data.result[0].value[1] }
    } catch { }
    return $null
}
function AlertStates {
    try {
        $r = Invoke-RestMethod "$prom/api/v1/alerts"
        $pairs = @($r.data.alerts | ForEach-Object { "{0}={1}" -f $_.labels.alertname, $_.state })
        if ($pairs.Count -eq 0) { return 'none' }
        return ($pairs -join ', ')
    } catch { return 'unreachable' }
}
$ratioQuery = '(sum(rate(http_requests_total{status=~"5.."}[5m])) or vector(0)) / sum(rate(http_requests_total[5m]))'

Note 'DRILL: PostgreSQL outage under live traffic' 'Cyan'
$base = Invoke-RestMethod http://localhost:30000/health/ready
Note ("Baseline API readiness: " + $base.status)
Note ("Baseline alerts: " + (AlertStates))

$trafficScript = Join-Path $root 'scripts\traffic.ps1'
$job = Start-Job -ScriptBlock { param($s, $n) & $s -Mode normal -Seconds $n } -ArgumentList $trafficScript, ($MaxWaitSeconds + 240)
Note 'Background traffic started; letting baseline settle for 30s'
Start-Sleep -Seconds 30
Note ("Baseline: db_up={0}  5xx_ratio={1}" -f (Fmt (PromValue 'db_up')), (Fmt (PromValue $ratioQuery)))

$t0 = Get-Date
Note 'FAULT INJECTED: docker compose stop postgres' 'Red'
docker compose stop postgres *> $null

$seen = @{}
$deadline = $t0.AddSeconds($MaxWaitSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 15
    $elapsed = [int]((Get-Date) - $t0).TotalSeconds
    $states = AlertStates
    Note ("T+{0,3}s  db_up={1}  5xx_ratio={2}  alerts: {3}" -f $elapsed, (Fmt (PromValue 'db_up')), (Fmt (PromValue $ratioQuery)), $states)
    foreach ($name in 'DatabaseDown', 'HighErrorRate') {
        if (-not $seen.ContainsKey($name) -and $states -match "$name=firing") {
            $seen[$name] = $elapsed
            Note ("ALERT FIRING: {0} at T+{1}s" -f $name, $elapsed) 'Yellow'
        }
    }
    if ($seen.ContainsKey('DatabaseDown') -and $seen.ContainsKey('HighErrorRate')) { break }
}

try {
    $am = Invoke-RestMethod http://localhost:30003/api/v2/alerts
    $names = (@($am) | ForEach-Object { $_.labels.alertname }) -join ', '
    Note ("Alertmanager holds {0} active alert(s): {1}" -f @($am).Count, $names) 'Yellow'
} catch { Note 'Alertmanager query failed' 'Yellow' }

$outageSec = [int]((Get-Date) - $t0).TotalSeconds
$t1 = Get-Date
Note ("RECOVERY: docker compose start postgres (outage lasted {0}s)" -f $outageSec) 'Green'
docker compose start postgres *> $null

$ready = $false
for ($i = 0; $i -lt 40 -and -not $ready; $i++) {
    Start-Sleep -Seconds 3
    try {
        $r = Invoke-RestMethod http://localhost:30000/health/ready
        if ($r.status -eq 'ready') { $ready = $true }
    } catch { }
}
$recSec = [int]((Get-Date) - $t1).TotalSeconds
if ($ready) {
    Note ("API readiness restored {0}s after Postgres start, with no API restart" -f $recSec) 'Green'
} else {
    Note 'API did not recover within 120s: run docker compose restart api' 'Red'
}

try {
    $o = Invoke-RestMethod -Method Post -Uri http://localhost:30000/orders -ContentType 'application/json' -Body '{"customer_id":"C-DRILL","channel":"online","lines":[{"sku":"WMT-1001","quantity":1,"unit_price":6.5}]}'
    Note ("Post-recovery order accepted: id {0}" -f $o.id) 'Green'
} catch { Note 'Post-recovery order FAILED' 'Red' }

Start-Sleep -Seconds 45
Note ("db_up={0}  alerts 45s after recovery: {1}" -f (Fmt (PromValue 'db_up')), (AlertStates))
Stop-Job $job -ErrorAction SilentlyContinue
Remove-Job $job -Force -ErrorAction SilentlyContinue

Note '--- SUMMARY ---' 'Cyan'
foreach ($name in 'DatabaseDown', 'HighErrorRate') {
    if ($seen.ContainsKey($name)) { Note ("{0}: fired {1}s after fault" -f $name, $seen[$name]) }
    else { Note ("{0}: did not fire" -f $name) 'Red' }
}
Note ("Outage duration: {0}s | API self-recovery after DB start: {1}s" -f $outageSec, $recSec)

$dir = Join-Path $root 'docs\rca'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$file = Join-Path $dir ("drill-{0}-evidence.txt" -f (Get-Date -Format 'yyyy-MM-dd'))
[System.IO.File]::WriteAllLines($file, $log, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("Evidence saved to {0}" -f $file) -ForegroundColor Cyan
