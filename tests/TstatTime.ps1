param(
  [Parameter(Mandatory=$true, Position=0)]
  [string]$Ip   # e.g. 10.0.60.8
)

# API wants Mon=0..Sun=6 (in .NET Sunday=0..Saturday=6)
$now    = Get-Date
$apiDay = ([int]$now.DayOfWeek + 6) % 7

# Build JSON and POST to /tstat
$body = @{ time = @{ day = $apiDay; hour = $now.Hour; minute = $now.Minute } } | ConvertTo-Json -Compress
Write-Host ("Setting time on {0} to {1:yyyy-MM-dd HH:mm} (day={2})..." -f $Ip, $now, $apiDay)
Invoke-RestMethod -Uri "http://$Ip/tstat" -Method Post -ContentType "application/json" -Body $body | Out-Null

# Verify
$time = (Invoke-RestMethod -Uri "http://$Ip/tstat").time
Write-Host "Thermostat time now:" ($time | Format-List | Out-String)
