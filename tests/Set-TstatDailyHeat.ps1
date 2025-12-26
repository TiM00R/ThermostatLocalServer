<#
.SYNOPSIS
  Set HEAT to a user-specified temperature for the entire day and set COOL to 30°C for each day on CT50 / RadioThermostat devices.

.EXAMPLE
  .\Set-TstatHeatAndCoolDaily.ps1 -Ip 10.0.60.8 -HeatTemp 21 -Unit C
#>

param(
  [Parameter(Mandatory=$true)][string]$Ip,
  [Parameter(Mandatory=$true)][double]$HeatTemp,
  [ValidateSet('C','F')] [string]$Unit = 'C'
)

# helper: safe print (tries JSON then fallback)
function Safe-Print {
  param($Obj)
  try {
    $json = $Obj | ConvertTo-Json -Depth 10 -ErrorAction Stop
    Write-Host $json
  } catch {
    $txt = $Obj | Format-List * -Force | Out-String
    Write-Host $txt
  }
}

# Convert input temp to Fahrenheit (thermostat expects °F)
function ToF {
  param(
    [double]$val,
    [string]$unit
  )
  if ($unit -eq 'C') {
    return [math]::Round((($val * 9.0/5.0) + 32.0), 1)
  } else {
    return [math]::Round($val, 1)
  }
}

# day names and index mapping
$dayNames = @('mon','tue','wed','thu','fri','sat','sun')
$dayIdxMap = @{ mon=0; tue=1; wed=2; thu=3; fri=4; sat=5; sun=6 }

# compute Fahrenheit temps for POST
$fHeatTemp = ToF -val $HeatTemp -unit $Unit
# COOL fixed at 30C per your request
$fCoolTemp = ToF -val 30.0 -unit 'C'

Write-Host ("Heat input: {0}°{1} -> {2}°F (will be posted to HEAT)." -f $HeatTemp, $Unit, $fHeatTemp)
Write-Host ("Cool fixed: 30°C -> {0}°F (will be posted to COOL)." -f $fCoolTemp)

# For each day: set COOL to 30C and HEAT to provided temp (both as whole-day single entry)
foreach ($day in $dayNames) {
  $idx = $dayIdxMap[$day].ToString()

  # 1) Set COOL to constant 30C for whole day -> POST {"<idx>":[0,<fCoolTemp>]} to /tstat/program/cool/<day>
  $coolBody = "{ `"$idx`":[0, $fCoolTemp] }"
  $coolUri  = "http://$Ip/tstat/program/cool/$day"

  Write-Host ""
  Write-Host ("Setting COOL for ${day}: POST {0}  (body: {1})" -f $coolUri, $coolBody)
  try {
    $respCool = Invoke-RestMethod -Uri $coolUri -Method Post -Body $coolBody -ContentType 'application/json' -TimeoutSec 15
    Safe-Print $respCool
  } catch {
    Write-Warning ("COOL POST failed for {0}: {1}" -f $day, $_)
  }

  Start-Sleep -Milliseconds 300

  # 2) Set HEAT to provided temperature for whole day -> POST {"<idx>":[0,<fHeatTemp>]} to /tstat/program/heat/<day>
  $heatBody = "{ `"$idx`":[0, $fHeatTemp] }"
  $heatUri  = "http://$Ip/tstat/program/heat/$day"

  Write-Host ("Setting HEAT for ${day}: POST {0}  (body: {1})" -f $heatUri, $heatBody)
  try {
    $respHeat = Invoke-RestMethod -Uri $heatUri -Method Post -Body $heatBody -ContentType 'application/json' -TimeoutSec 15
    Safe-Print $respHeat
  } catch {
    Write-Warning ("HEAT POST failed for {0}: {1}" -f $day, $_)
  }

  # small pause to avoid overloading device (single-threaded HTTP server)
  Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host ("Done. Verify schedules with: Invoke-RestMethod -Uri ""http://{0}/tstat/program/heat"" -Method Get | ConvertTo-Json -Depth 6" -f $Ip)
Write-Host ("And: Invoke-RestMethod -Uri ""http://{0}/tstat/program/cool"" -Method Get | ConvertTo-Json -Depth 6" -f $Ip)
