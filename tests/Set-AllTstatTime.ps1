param(
  [string]$StartIP = '2',      # accepts "2" or "10.0.60.2"
  [string]$EndIP   = '20',     # accepts "20" or "10.0.60.20"
  [int]   $TimeoutSec = 4      # per-host HTTP timeout (seconds)
)

function Get-HostOctet {
  param([string]$Arg)
  if ($Arg -match '^\d{1,3}(\.\d{1,3}){3}$') { return [int]($Arg.Split('.')[-1]) }
  else { return [int]$Arg }
}

function Test-IsThermostat {
  param([string]$Ip,[int]$TimeoutSec)
  try {
    $t = Invoke-RestMethod -Uri "http://$Ip/tstat" -TimeoutSec $TimeoutSec -ErrorAction Stop
    if (-not $t) { return $false }
    # Must have a time object with day/hour/minute and typical fields
    if (-not $t.PSObject.Properties.Name.Contains('time')) { return $false }
    $tt = $t.time
    if ($null -eq $tt) { return $false }
    # Validate ranges
    $hasDay  = $tt.PSObject.Properties.Name -contains 'day'
    $hasHour = $tt.PSObject.Properties.Name -contains 'hour'
    $hasMin  = $tt.PSObject.Properties.Name -contains 'minute'
    if (-not ($hasDay -and $hasHour -and $hasMin)) { return $false }
    if ( [int]$tt.day -lt 0 -or [int]$tt.day -gt 6 ) { return $false }
    if ( [int]$tt.hour -lt 0 -or [int]$tt.hour -gt 23 ) { return $false }
    if ( [int]$tt.minute -lt 0 -or [int]$tt.minute -gt 59 ) { return $false }
    # Optional sanity: tmode 0..3 if present
    if ($t.PSObject.Properties.Name -contains 'tmode') {
      $tm = [int]$t.tmode
      if ($tm -lt 0 -or $tm -gt 3) { return $false }
    }
    return $true
  } catch { return $false }
}

$base  = '10.0.60'
$start = Get-HostOctet $StartIP
$end   = Get-HostOctet $EndIP
if ($end -lt $start) { $t=$start; $start=$end; $end=$t }

$ips   = $start..$end | ForEach-Object { "$base.$_" }
$total = $ips.Count

# Local time → API (Mon=0..Sun=6)
$now    = Get-Date
$apiDay = ([int]$now.DayOfWeek + 6) % 7
$body   = @{ time = @{ day = $apiDay; hour = $now.Hour; minute = $now.Minute } } | ConvertTo-Json -Compress
$dayNames = @('Mon','Tue','Wed','Thu','Fri','Sat','Sun')

Write-Host ("Setting time to {0:yyyy-MM-dd HH:mm} (day={1}) on {2}.{3}..{4}  timeout={5}s`n" -f $now, $apiDay, $base, $start, $end, $TimeoutSec) -ForegroundColor Cyan

$i=0; $ok=0
foreach ($ip in $ips) {
  $i++
  Write-Host ("[{0,2}/{1}] {2} ..." -f $i,$total,$ip) -NoNewline
  if (-not (Test-IsThermostat -Ip $ip -TimeoutSec $TimeoutSec)) {
    Write-Host "  skip (not a thermostat)" -ForegroundColor DarkGray
    continue
  }
  try {
    # Optional: read /sys/name for nice output (ignore errors)
    $name = $null
    try { $name = (Invoke-RestMethod -Uri "http://$ip/sys/name" -TimeoutSec $TimeoutSec -ErrorAction Stop).name } catch {}

    # Set time
    #Invoke-RestMethod -Uri "http://$ip/tstat" -Method Post -ContentType "application/json" -Body $body -TimeoutSec $TimeoutSec -ErrorAction Stop
    # set time (discard any {"success":0} noise)
    Invoke-RestMethod -Uri "http://$ip/tstat" -Method Post -ContentType "application/json" -Body $body -TimeoutSec $TimeoutSec -ErrorAction Stop | Out-Null
    # or: > $null 2>&1

    # Verify actual time from device
    $t = (Invoke-RestMethod -Uri "http://$ip/tstat" -TimeoutSec $TimeoutSec -ErrorAction Stop).time
    $h = [int]$t.hour; $m = [int]$t.minute; $d = [int]$t.day
    $h12 = $h % 12; if ($h12 -eq 0) { $h12 = 12 }; $ampm = ($h -ge 12) ? 'PM' : 'AM'
    Write-Host ("  OK  {0}{1} -> {2} {3}:{4:D2} (24h) / {5}:{6:D2} {7}" -f ($name ?? ''), ($(if($name){' '}else{''})), $dayNames[$d], $h, $m, $h12, $m, $ampm) -ForegroundColor Green
    $ok++
  } catch {
    Write-Host "  -" 
  }
}

"`nDone. Updated {0} thermostat(s)." -f $ok
