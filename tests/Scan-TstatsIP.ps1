param(
  [string]$StartIP = '2',    # accepts "2" or "10.0.60.2"
  [string]$EndIP   = '20',   # accepts "20" or "10.0.60.20"
  [int]   $TimeoutSec = 5    # per-host HTTP timeout (seconds)
)

function Get-HostOctet {
  param([string]$Arg)
  if ($Arg -match '^\d{1,3}(\.\d{1,3}){3}$') { return [int]($Arg.Split('.')[-1]) }
  else { return [int]$Arg }
}

$base  = '10.0.60'
$start = Get-HostOctet $StartIP
$end   = Get-HostOctet $EndIP
if ($end -lt $start) { $t=$start; $start=$end; $end=$t }

$ips   = $start..$end | ForEach-Object { "$base.$_" }
$total = $ips.Count
Write-Host ("Scanning {0}.{1}..{2}  (timeout={3}s per host)`n" -f $base,$start,$end,$TimeoutSec) -ForegroundColor Cyan

$i = 0
$found = @()

foreach ($ip in $ips) {
  $i++
  Write-Host ("[{0,2}/{1}] {2} ..." -f $i,$total,$ip) -NoNewline
  try {
    $sys  = Invoke-RestMethod -Uri "http://$ip/sys" -TimeoutSec $TimeoutSec -ErrorAction Stop
    $name = $null
    try { $name = (Invoke-RestMethod -Uri "http://$ip/sys/name" -TimeoutSec $TimeoutSec -ErrorAction Stop).name } catch {}
    Write-Host ("  FOUND  {0}  {1}" -f ($name ?? ''), $sys.model) -ForegroundColor Green
    $found += [pscustomobject]@{
      IP=$ip; Name=$name; Model=$sys.model; ApiVersion=$sys.api_version; FwVersion=$sys.fw_version
    }
  } catch {
    Write-Host "  -"  # no response
  }
}

"`nFound $($found.Count) thermostat(s):"
if ($found.Count) { $found | Sort-Object IP | Format-Table -AutoSize IP,Name,Model,ApiVersion,FwVersion }
