param(
    [ValidateSet('seed', 'normal', 'stockout')][string]$Mode = 'normal',
    [int]$Seconds = 120,
    [string]$Base = 'http://localhost:30000'
)

$script:failed = 0

function Api($method, $path, $body) {
    $p = @{ Method = $method; Uri = "$Base$path" }
    if ($body) { $p.ContentType = 'application/json'; $p.Body = ConvertTo-Json -InputObject $body -Depth 6 }
    try { return Invoke-RestMethod @p } catch { $script:failed++; return $null }
}

if ($Mode -eq 'seed') {
    $catalog = @(
        @('WMT-1001', 'Great Value Rice 5kg', 500),
        @('WMT-1002', 'Great Value Whole Milk 1L', 500),
        @('WMT-1003', 'Mainstays Desk Lamp', 500),
        @('WMT-1004', 'Ozark Trail Water Bottle', 500),
        @('WMT-1005', 'Parents Choice Diapers', 500),
        @('WMT-1006', 'Marketside Salad Kit', 500),
        @('WMT-1007', 'Mainstays Bath Towel', 500),
        @('WMT-1008', 'Limited Edition Thermos', 40)
    )
    foreach ($c in $catalog) {
        Api 'POST' '/inventory' @{ sku = $c[0]; name = $c[1]; on_hand = $c[2] } | Out-Null
    }
    Write-Host "Seeded $($catalog.Count) SKUs (WMT-1008 has 40 units; run -Mode stockout to drain it)"
    return
}

$end = (Get-Date).AddSeconds($Seconds)
$created = 0

if ($Mode -eq 'normal') {
    $skus = 'WMT-1001', 'WMT-1002', 'WMT-1003', 'WMT-1004', 'WMT-1005', 'WMT-1006', 'WMT-1007'
    $channels = 'online', 'store_pickup', 'delivery'
    $flow = 'PICKING', 'PACKED', 'SHIPPED', 'DELIVERED'
    while ((Get-Date) -lt $end) {
        $line = @{ sku = ($skus | Get-Random); quantity = (Get-Random -Minimum 1 -Maximum 4); unit_price = [math]::Round((Get-Random -Minimum 2 -Maximum 40) + 0.99, 2) }
        $order = Api 'POST' '/orders' @{ customer_id = "C-$(Get-Random -Minimum 100 -Maximum 999)"; channel = ($channels | Get-Random); lines = @($line) }
        if ($order) {
            $created++
            $depth = Get-Random -Minimum 0 -Maximum 5
            for ($i = 0; $i -lt $depth; $i++) {
                Api 'PATCH' "/orders/$($order.id)/status" @{ status = $flow[$i] } | Out-Null
            }
        }
        Api 'GET' '/inventory' $null | Out-Null
        Start-Sleep -Milliseconds (Get-Random -Minimum 150 -Maximum 450)
    }
}

if ($Mode -eq 'stockout') {
    while ((Get-Date) -lt $end) {
        $order = Api 'POST' '/orders' @{ customer_id = 'C-FLASH'; channel = 'online'; lines = @(@{ sku = 'WMT-1008'; quantity = 3; unit_price = 24.99 }) }
        if ($order) { $created++ }
        Start-Sleep -Milliseconds 300
    }
}

Write-Host "Mode=$Mode finished: $created orders accepted, $($script:failed) requests rejected or failed"