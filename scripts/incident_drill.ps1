param(
    [string]$RunName = 'run2',
    [int]$MaxWaitSeconds = 360
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$prom = 'http://localhost:30001'
$sink = 'http://localhost:30005'
$api = 'http://localhost:30000'
$watch = @('DatabaseDown', 'HighErrorRateFastBurn', 'HighErrorRate')
$log = New-Object System.Collections.Generic.List[string]
$ratio1m = '(sum(rate(http_requests_total{status=~"5.."}[1m])) or vector(0)) / sum(rate(http_requests_total[1m]))'
$p95Query = 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[1m])))'
$script:peakRatio = 0.0
$script:peakP95 = 0.0
$script:seen = 0
$script:notified = @{}

function Note($msg, $color = 'Gray') {
    $line = "[{0}] {1}" -f (Get-Date).ToString('HH:mm:ss'), $msg
    $log.Add($line)
    Write-Host $line -ForegroundColor $color
}
function Fmt($v) { if ($null -eq $v -or [double]::IsNaN($v)) { 'n/a' } else { '{0:N3}' -f $v } }
function PromValue($q) {
    try {
        $r = Invoke-RestMethod ("{0}/api/v1/query?query={1}" -f $prom, [uri]::EscapeDataString($q)) -TimeoutSec 5
        if ($r.data.result.Count -gt 0) { return [double]$r.data.result[0].value[1] }
    } catch { }
    return $null
}
function GetAlertMap {
    $map = @{}
    try {
        $r = Invoke-RestMethod "$prom/api/v1/alerts" -TimeoutSec 5
        foreach ($a in $r.data.alerts) { $map[$a.labels.alertname] = $a.state }
    } catch { }
    return $map
}
function MapText($m) {
    if ($m.Count -eq 0) { return 'none' }
    return (($m.GetEnumerator() | Sort-Object Name | ForEach-Object { "{0}={1}" -f $_.Name, $_.Value }) -join ', ')
}
function SinkEvents {
    try { return @(Invoke-RestMethod "$sink/events" -TimeoutSec 5) } catch { return @() }
}
function UpdatePeaks {
    $r = PromValue $ratio1m
    if ($null -ne $r -and -not [double]::IsNaN($r) -and $r -gt $script:peakRatio) { $script:peakRatio = $r }
    $p = PromValue $p95Query
    if ($null -ne $p -and -not [double]::IsNaN($p) -and $p -gt $script:peakP95) { $script:peakP95 = $p }
}
function ProcessEvents($t0) {
    foreach ($e in @(SinkEvents)) {
        if ($e.seq -le $script:seen) { continue }
        $script:seen = $e.seq
        $elapsed = [int]((Get-Date) - $t0).TotalSeconds
        $names = (@($e.alerts) | ForEach-Object { "{0}:{1}" -f $_.alertname, $_.status }) -join ', '
        Note ("WEBHOOK notification #{0} at T+{1}s: {2}" -f $e.seq, $elapsed, $names) 'Magenta'
        foreach ($a in @($e.alerts)) {
            if ($a.status -eq 'firing' -and ($watch -contains $a.alertname) -and -not $script:notified.ContainsKey($a.alertname)) {
                $script:notified[$a.alertname] = $elapsed
            }
        }
    }
}
function Cell($d, $k) { if ($d.ContainsKey($k)) { '{0}s' -f $d[$k] } else { 'did not fire' } }

Note ("DRILL ({0}): PostgreSQL outage under live traffic" -f $RunName) 'Cyan'
$base = Invoke-RestMethod "$api/health/ready"
Note ("Baseline readiness: {0}; alerts: {1}" -f $base.status, (MapText (GetAlertMap)))
$script:seen = @(SinkEvents).Count

$trafficScript = Join-Path $root 'scripts\traffic.ps1'
$job = Start-Job -ScriptBlock { param($s, $n) & $s -Mode normal -Seconds $n } -ArgumentList $trafficScript, ($MaxWaitSeconds + 240)
Note 'Background traffic started; letting baseline settle for 30s'
Start-Sleep -Seconds 30
Note ("Baseline: db_up={0}  5xx_ratio_1m={1}  p95_1m={2}s" -f (Fmt (PromValue 'db_up')), (Fmt (PromValue $ratio1m)), (Fmt (PromValue $p95Query)))

$t0 = Get-Date
Note 'FAULT INJECTED: docker compose stop postgres' 'Red'
docker compose stop postgres *> $null

$firing = @{}
$tick = 0
$deadline = $t0.AddSeconds($MaxWaitSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 5
    $tick++
    $elapsed = [int]((Get-Date) - $t0).TotalSeconds
    $map = GetAlertMap
    foreach ($name in $watch) {
        if (-not $firing.ContainsKey($name) -and $map[$name] -eq 'firing') {
            $firing[$name] = $elapsed
            Note ("ALERT FIRING in Prometheus: {0} at T+{1}s" -f $name, $elapsed) 'Yellow'
        }
    }
    ProcessEvents $t0
    if ($tick % 3 -eq 0) {
        UpdatePeaks
        Note ("T+{0,3}s  db_up={1}  5xx_ratio_1m={2}  p95_1m={3}s  alerts: {4}" -f $elapsed, (Fmt (PromValue 'db_up')), (Fmt (PromValue $ratio1m)), (Fmt (PromValue $p95Query)), (MapText $map))
    }
    if ($firing.Count -eq $watch.Count) { break }
}

UpdatePeaks
$err5xx = PromValue 'sum(increase(http_requests_total{status=~"5.."}[5m]))'
$outageSec = [int]((Get-Date) - $t0).TotalSeconds
$t1 = Get-Date
Note ("RECOVERY: docker compose start postgres (outage lasted {0}s)" -f $outageSec) 'Green'
docker compose start postgres *> $null

$ready = $false
$recSec = $null
$resolved = @{}
$post = $t1.AddSeconds(150)
while ((Get-Date) -lt $post) {
    Start-Sleep -Seconds 3
    if (-not $ready) {
        try {
            $r = Invoke-RestMethod "$api/health/ready" -TimeoutSec 3
            if ($r.status -eq 'ready') {
                $ready = $true
                $recSec = [int]((Get-Date) - $t1).TotalSeconds
                Note ("API readiness restored {0}s after Postgres start, with no API restart" -f $recSec) 'Green'
                try {
                    $o = Invoke-RestMethod -Method Post -Uri "$api/orders" -ContentType 'application/json' -Body '{"customer_id":"C-DRILL","channel":"online","lines":[{"sku":"WMT-1001","quantity":1,"unit_price":6.5}]}'
                    Note ("Post-recovery order accepted: id {0}" -f $o.id) 'Green'
                } catch { Note 'Post-recovery order FAILED' 'Red' }
            }
        } catch { }
    }
    $map = GetAlertMap
    foreach ($name in 'DatabaseDown', 'HighErrorRateFastBurn') {
        if (-not $resolved.ContainsKey($name) -and $map[$name] -ne 'firing') {
            $resolved[$name] = [int]((Get-Date) - $t1).TotalSeconds
            Note ("{0} cleared {1}s after recovery" -f $name, $resolved[$name]) 'Green'
        }
    }
    ProcessEvents $t0
    if ($ready -and $resolved.Count -eq 2 -and $script:notified.Count -ge $firing.Count) { break }
}
Note ("db_up={0}  alerts now: {1}" -f (Fmt (PromValue 'db_up')), (MapText (GetAlertMap)))
Stop-Job $job -ErrorAction SilentlyContinue
Remove-Job $job -Force -ErrorAction SilentlyContinue

$firstNotify = $null
if ($script:notified.Count -gt 0) { $firstNotify = ($script:notified.Values | Measure-Object -Minimum).Minimum }

Note '--- SUMMARY (before = run 1, polled every 15s; after = this run, polled every 5s) ---' 'Cyan'
Note ("{0,-36} {1,-20} {2,-16}" -f 'Metric', 'Run 1 (before)', ("{0} (after)" -f $RunName))
Note ("{0,-36} {1,-20} {2,-16}" -f 'DatabaseDown fired', '76s', (Cell $firing 'DatabaseDown'))
Note ("{0,-36} {1,-20} {2,-16}" -f 'HighErrorRateFastBurn fired', 'n/a (new alert)', (Cell $firing 'HighErrorRateFastBurn'))
Note ("{0,-36} {1,-20} {2,-16}" -f 'HighErrorRate (5m window) fired', '226s', (Cell $firing 'HighErrorRate'))
Note ("{0,-36} {1,-20} {2,-16}" -f 'First webhook notification', 'none (no receiver)', $(if ($null -ne $firstNotify) { '{0}s' -f $firstNotify } else { 'none' }))
Note ("{0,-36} {1,-20} {2,-16}" -f 'API recovery after DB start', '4s', $(if ($null -ne $recSec) { '{0}s' -f $recSec } else { 'not recovered' }))
Note ("{0,-36} {1,-20} {2,-16}" -f 'Peak 5xx ratio (1m window)', 'not captured', (Fmt $script:peakRatio))
Note ("{0,-36} {1,-20} {2,-16}" -f 'Peak p95 latency (1m window)', 'not captured', ((Fmt $script:peakP95) + 's'))
Note ("{0,-36} {1,-20} {2,-16}" -f '5xx responses in 5m window', 'not captured', (Fmt $err5xx))
Note ("{0,-36} {1,-20} {2,-16}" -f 'DatabaseDown cleared after recovery', 'not captured', $(if ($resolved.ContainsKey('DatabaseDown')) { '{0}s' -f $resolved['DatabaseDown'] } else { 'still firing' }))
Note ("{0,-36} {1,-20} {2,-16}" -f 'FastBurn cleared after recovery', 'n/a', $(if ($resolved.ContainsKey('HighErrorRateFastBurn')) { '{0}s' -f $resolved['HighErrorRateFastBurn'] } else { 'still firing' }))
Note ("Outage duration this run: {0}s (run 1: 226s)" -f $outageSec)

$dir = Join-Path $root 'docs\rca'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$file = Join-Path $dir ("drill-{0}-{1}-evidence.txt" -f (Get-Date -Format 'yyyy-MM-dd'), $RunName)
[System.IO.File]::WriteAllLines($file, $log, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("Evidence saved to {0}" -f $file) -ForegroundColor Cyan