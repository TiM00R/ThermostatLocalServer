<#
.SYNOPSIS
  Show CT50 / RadioThermostat weekly schedules (heat + cool) with temps in Celsius.

.EXAMPLE
  .\Show-TstatSchedule.ps1 -Ip 10.0.60.8
#>

param(
  [Parameter(Mandatory=$true)]
  [string]$Ip
)

# helper: fetch JSON from given endpoint, return $null on failure
function Fetch {
  param($Path)
  try {
    return Invoke-RestMethod -Uri "http://$Ip$Path" -Method Get -TimeoutSec 12
  } catch {
    return $null
  }
}

# helper: normalize program container and extract day's array (index '0'..'6')
function Get-DayArray {
  param($ProgramObj, [string]$Idx)

  if (-not $ProgramObj) { return $null }

  # direct keyed access (string index)
  if ($ProgramObj.PSObject.Properties.Name -contains $Idx) {
    return $ProgramObj."$Idx"
  }

  # if first-level object contains objects per day (wrapped)
  $first = $ProgramObj | Select-Object -First 1
  if ($first -and $first.PSObject.Properties.Name -contains $Idx) {
    return $first."$Idx"
  }

  # if programObj is an array of objects
  if ($ProgramObj -is [System.Array]) {
    foreach ($item in $ProgramObj) {
      if ($item -and $item.PSObject.Properties.Name -contains $Idx) {
        return $item."$Idx"
      }
    }
  }

  return $null
}

# helper: flatten various array-like shapes into simple numeric list
function Flatten-ToList {
  param($Arr)
  if (-not $Arr) { return @() }
  $out = @()
  foreach ($el in $Arr) {
    if ($el -is [System.Array] -or $el -is [System.Collections.IEnumerable]) {
      $out += $el
    } else {
      $out += $el
    }
  }
  return $out
}

# convert F -> C rounded to 1 decimal
function FtoC {
  param([double]$f)
  return [math]::Round((($f - 32.0) * 5.0/9.0), 1)
}

# format minutes into HH:MM (24h)
function MinToTime {
  param([int]$min)
  $ts = [TimeSpan]::FromMinutes($min)
  return "{0:D2}:{1:D2}" -f $ts.Hours, $ts.Minutes
}

# map day name -> index string
$dayMap = @{ mon = 0; tue = 1; wed = 2; thu = 3; fri = 4; sat = 5; sun = 6 }
$dayNames = @{ 0='Mon'; 1='Tue'; 2='Wed'; 3='Thu'; 4='Fri'; 5='Sat'; 6='Sun' }

# fetch thermostat name (try /sys/name then fallback to /tstat/model)
$nameObj = Fetch '/sys/name'
if ($nameObj) {
  # could be string or object with 'name' property
  if ($nameObj -is [string]) { $tstatName = $nameObj } else { $tstatName = $nameObj.name }
}
if (-not $tstatName) {
  $modelObj = Fetch '/tstat/model'
  if ($modelObj) {
    $tstatName = $modelObj.model
  } else {
    $tstatName = '<unknown>'
  }
}

# print header
Write-Host "Thermostat: $tstatName  —  IP: $Ip"
Write-Host ('-' * 60)

# for each mode, fetch weekly program and print all days
foreach ($mode in @('heat','cool')) {
  Write-Host ""
  Write-Host ("Mode: {0}" -f ($mode.ToUpper()))
  Write-Host ('=' * 60)

  $prog = Fetch "/tstat/program/$mode"
  if (-not $prog) {
    Write-Warning "No program data available for mode '$mode'."
    continue
  }

  for ($d = 0; $d -le 6; $d++) {
    $idx = $d.ToString()
    $dayArr = Get-DayArray -ProgramObj $prog -Idx $idx
    if (-not $dayArr) {
      Write-Host ("{0}: (no program)" -f $dayNames[$d])
      continue
    }

    $flat = Flatten-ToList -Arr $dayArr
    if ($flat.Count -eq 0) {
      Write-Host ("{0}: (empty)" -f $dayNames[$d])
      continue
    }

    Write-Host ("{0}:" -f $dayNames[$d])
    for ($i = 0; $i -lt $flat.Count; $i += 2) {
      $minutes = 0
      $fTemp = $null
      try { $minutes = [int]$flat[$i] } catch { $minutes = 0 }
      try { $fTemp = [double]$flat[$i + 1] } catch { $fTemp = $null }

      $timeStr = MinToTime -min $minutes
      if ($fTemp -ne $null) {
        $cTemp = FtoC -f $fTemp
        Write-Host ("  {0} -> {1}°C  ({2}°F)" -f $timeStr, $cTemp, $fTemp)
      } else {
        Write-Host ("  {0} -> <no temp>" -f $timeStr)
      }
    }
  }
}

Write-Host ('-' * 60)
Write-Host "Done."
