<#
Set-AllTstatsHeat_IPScan_WithReadSchedule.ps1
IP-range HTTP scan (/sys + /sys/name only), set HEAT whole-day, then read back HEAT schedule for all discovered thermostats.

Usage examples:
  # dry-run (no POSTs), still reads existing schedules
  .\Set-AllTstatsHeat_IPScan_WithReadSchedule.ps1 -BasePrefix '10.0.60' -Start 4 -End 9 -HeatTemp 11 -Unit C -DryRun

  # apply changes and read schedules
  .\Set-AllTstatsHeat_IPScan_WithReadSchedule.ps1 -BasePrefix '10.0.60' -Start 4 -End 9 -HeatTemp 11 -Unit C
#>

param(
  [string]$BasePrefix = '10.0.60',
  [Parameter(Mandatory=$true)][ValidateRange(1,254)][int]$Start,
  [Parameter(Mandatory=$true)][ValidateRange(1,254)][int]$End,
  [Parameter(Mandatory=$true)][double]$HeatTemp,
  [ValidateSet('C','F')][string]$Unit = 'C',
  [int]$HttpTimeout = 3,
  [int]$PostDelayMs = 500,
  [switch]$DryRun,
  [switch]$ShowProgress = $true
)

if ($End -lt $Start) { throw "End must be >= Start" }

function ToF([double]$val, [string]$unit) {
  if ($unit -eq 'C') { return [math]::Round((($val * 9.0/5.0) + 32.0), 1) }
  return [math]::Round($val, 1)
}
function FtoC([double]$f) { return [math]::Round((($f - 32.0) * 5.0/9.0), 1) }

function Try-Get {
  param([string]$Url, [int]$TimeoutSec = 3)
  $out = [ordered]@{ Ok = $false; Parsed = $null; Raw = $null; Err = $null }
  try {
    $parsed = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec $TimeoutSec -ErrorAction Stop
    $out.Parsed = $parsed
    try { $out.Raw = ($parsed | ConvertTo-Json -Depth 6) } catch { $out.Raw = ($parsed | Out-String) }
    $out.Ok = $true
    return $out
  } catch {
    $out.Err = $_
    try {
      $wr = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec $TimeoutSec -ErrorAction Stop
      $out.Raw = $wr.Content
      $out.Ok = $true
      return $out
    } catch {
      $out.Err = ($out.Err.ToString() + " | " + $_.ToString())
      return $out
    }
  }
}

function Looks-Like-HttpStatus {
  param([string]$s)
  if (-not $s) { return $false }
  $l = $s.ToLower()
  return ($l -match '<html' -or $l -match '200 ok' -or $l -match '<title>')
}

function Is-Thermostat {
  param($sysResp, $nameResp)
  # Accept if parsed /sys contains thermostat keys
  if ($sysResp -and $sysResp.Ok -and $sysResp.Parsed) {
    $p = $sysResp.Parsed
    if ($p -is [System.Management.Automation.PSCustomObject]) {
      foreach ($k in @('fw_version','api_version','uuid','wlan_fw_version')) {
        if ($p.PSObject.Properties.Name -contains $k -and $p.$k) { return $true }
      }
      foreach ($prop in $p.PSObject.Properties) {
        $val = $prop.Value
        if ($null -ne $val) {
          if ($val -is [System.Array]) {
            if ($val.Count -gt 0) { return $true }
          } else { return $true }
        }
      }
    }
    if ($p -is [System.Array]) {
      foreach ($elem in $p) {
        if ($elem -is [System.Management.Automation.PSCustomObject]) {
          foreach ($k in @('fw_version','api_version','uuid')) {
            if ($elem.PSObject.Properties.Name -contains $k -and $elem.$k) { return $true }
          }
        }
      }
    }
  }

  # If sys raw looks like HTML status page, reject unless /sys/name gives a plain non-HTML string
  if ($sysResp -and $sysResp.Raw) {
    if (Looks-Like-HttpStatus -s $sysResp.Raw) {
      if ($nameResp -and $nameResp.Ok -and $nameResp.Parsed -and ($nameResp.Parsed -is [string]) -and ($nameResp.Parsed.Trim().Length -gt 0) -and -not (Looks-Like-HttpStatus -s $nameResp.Raw)) {
        return $true
      }
      return $false
    }
  }

  # fallback: accept if /sys/name is a plain non-empty string
  if ($nameResp -and $nameResp.Ok -and $nameResp.Parsed) {
    if ($nameResp.Parsed -is [string]) {
      $s = $nameResp.Parsed.Trim()
      if ($s.Length -gt 0 -and -not (Looks-Like-HttpStatus -s $nameResp.Raw)) { return $true }
    } elseif ($nameResp.Parsed -is [System.Management.Automation.PSCustomObject]) {
      if ($nameResp.Parsed.PSObject.Properties.Name -contains 'name' -and $nameResp.Parsed.name) { return $true }
    }
  }

  return $false
}

function Extract-NameVersion {
  param($sysResp, $nameResp)
  $name = '<unknown>'; $version = '<n/a>'
  if ($nameResp -and $nameResp.Ok -and $nameResp.Parsed) {
    if ($nameResp.Parsed -is [string]) { $name = $nameResp.Parsed.Trim() }
    elseif ($nameResp.Parsed -is [System.Management.Automation.PSCustomObject]) {
      if ($nameResp.Parsed.PSObject.Properties.Name -contains 'name' -and $nameResp.Parsed.name) { $name = [string]$nameResp.Parsed.name }
    }
  }
  if ($name -eq '<unknown>' -and $sysResp -and $sysResp.Ok -and $sysResp.Parsed -and ($sysResp.Parsed -is [System.Management.Automation.PSCustomObject])) {
    foreach ($k in @('name','hostname','device','model')) {
      if ($sysResp.Parsed.PSObject.Properties.Name -contains $k -and $sysResp.Parsed.$k) { $name = [string]$sysResp.Parsed.$k; break }
    }
  }
  if ($sysResp -and $sysResp.Ok -and $sysResp.Parsed -and ($sysResp.Parsed -is [System.Management.Automation.PSCustomObject])) {
    if ($sysResp.Parsed.PSObject.Properties.Name -contains 'fw_version' -and $sysResp.Parsed.fw_version) { $version = [string]$sysResp.Parsed.fw_version }
    elseif ($sysResp.Parsed.PSObject.Properties.Name -contains 'api_version' -and $sysResp.Parsed.api_version) { $version = "api:$($sysResp.Parsed.api_version)" }
  }
  return @{ Name = $name; Version = $version }
}

# Start scanning IP range (HTTP only)
$discovered = @()
for ($i = $Start; $i -le $End; $i++) {
  $ip = "$BasePrefix.$i"
  if ($ShowProgress) { Write-Host -NoNewline ("Checking {0} ... " -f $ip) }

  $base = "http://$ip"
  $sysResp  = Try-Get -Url ("$base/sys") -TimeoutSec $HttpTimeout
  $nameResp = Try-Get -Url ("$base/sys/name") -TimeoutSec $HttpTimeout

  if ($sysResp.Ok -or $nameResp.Ok) {
    if (Is-Thermostat -sysResp $sysResp -nameResp $nameResp) {
      $iv = Extract-NameVersion -sysResp $sysResp -nameResp $nameResp
      $discovered += [PSCustomObject]@{ Name = $iv.Name; IP = $ip; Version = $iv.Version; BaseUri = $base }
      if ($ShowProgress) { Write-Host ("thermostat -> {0}" -f $iv.Name) } else { Write-Host '' }
      continue
    }
  }

  if ($ShowProgress) { Write-Host "no response or not thermostat" } else { Write-Host '' }
}

if ($discovered.Count -eq 0) { Write-Host "No thermostats found in range $BasePrefix.$Start..$BasePrefix.$End"; exit 0 }

# Prepare Fahrenheit value for device
$fTemp = ToF -val $HeatTemp -unit $Unit
Write-Host ("Setting HEAT to {0}°{1} -> {2}°F on {3} thermostat(s)" -f $HeatTemp, $Unit, $fTemp, $discovered.Count)

$dayNames = @('mon','tue','wed','thu','fri','sat','sun')

foreach ($t in $discovered) {
  Write-Host ""
  Write-Host ("Applying to {0} ({1})" -f $t.Name, $t.IP)
  foreach ($d in $dayNames) {
    $idx = switch ($d) { 'mon' {0} 'tue' {1} 'wed' {2} 'thu' {3} 'fri' {4} 'sat' {5} 'sun' {6} }
    # build JSON payload with dynamic key as string
    $payload = @{ ($idx.ToString()) = @(0, $fTemp) } | ConvertTo-Json -Depth 3 -Compress
    $uri = ("{0}/tstat/program/heat/{1}" -f $t.BaseUri, $d)
    Write-Host ("  POST {0}  body: {1}" -f $uri, $payload)
    if ($DryRun) { continue }
    try {
      $resp = Invoke-RestMethod -Uri $uri -Method Post -Body $payload -ContentType 'application/json' -TimeoutSec $HttpTimeout -ErrorAction Stop
      try { $resp | ConvertTo-Json -Depth 6 | Write-Host } catch { $resp | Format-List * -Force | Out-String | Write-Host }
    } catch {
      Write-Warning ("  POST failed for {0}: {1}" -f $uri, $_)
    }
    Start-Sleep -Milliseconds $PostDelayMs
  }
}

### === NEW: Read HEAT schedule for all thermostats ===

function Parse-DaySchedule {
  param($respParsed, $respRaw)
  # Expected common shapes:
  #  - PSCustomObject with numeric keys mapping to arrays: { "0":[360,78,480,85,...] }
  #  - Array directly: [360,78,480,85,...]
  #  - Raw JSON string containing the above
  $arr = $null

  if ($respParsed) {
    if ($respParsed -is [System.Management.Automation.PSCustomObject]) {
      # pick the first property value that is a numeric array
      foreach ($prop in $respParsed.PSObject.Properties) {
        $val = $prop.Value
        if ($val -is [System.Array]) { $arr = $val; break }
      }
    } elseif ($respParsed -is [System.Array]) {
      $arr = $respParsed
    } else {
      # scalar string maybe containing JSON
      try {
        $tryj = $respParsed | ConvertFrom-Json -ErrorAction Stop
        if ($tryj -is [System.Array]) { $arr = $tryj }
        elseif ($tryj -is [System.Management.Automation.PSCustomObject]) {
          foreach ($prop in $tryj.PSObject.Properties) {
            if ($prop.Value -is [System.Array]) { $arr = $prop.Value; break }
          }
        }
      } catch {}
    }
  }

  if (-not $arr -and $respRaw) {
    try {
      $j = $respRaw | ConvertFrom-Json -ErrorAction Stop
      if ($j -is [System.Array]) { $arr = $j }
      elseif ($j -is [System.Management.Automation.PSCustomObject]) {
        foreach ($prop in $j.PSObject.Properties) {
          if ($prop.Value -is [System.Array]) { $arr = $prop.Value; break }
        }
      }
    } catch {}
  }

  # Ensure it's an array of numbers
  if (-not $arr -or -not ($arr -is [System.Array]) -or $arr.Count -eq 0) { return @() }

  # If elements are objects with min/temp, handle that (unlikely). Expect numeric list.
  $pairs = @()
  for ($i = 0; $i -lt $arr.Count; $i += 2) {
    if ($i + 1 -ge $arr.Count) { break }
    $minutes = $null; $temp = $null
    try { $minutes = [int]$arr[$i] } catch { $minutes = $null }
    try { $temp = [double]$arr[$i+1] } catch { $temp = $null }
    if ($minutes -ne $null -and $temp -ne $null) { $pairs += [PSCustomObject]@{ Minutes = $minutes; TempF = $temp } }
  }
  return $pairs
}

function Print-ScheduleForThermostat {
  param($baseUri, $name, $unitPref)
  Write-Host ""
  Write-Host "Schedule for $name ($baseUri):"
  foreach ($d in $dayNames) {
    $url = ("{0}/tstat/program/heat/{1}" -f $baseUri, $d)
    try {
      $r = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec $HttpTimeout -ErrorAction Stop
      $raw = $null
      try { $raw = ($r | ConvertTo-Json -Depth 6) } catch { $raw = ($r | Out-String) }
      $pairs = Parse-DaySchedule -respParsed $r -respRaw $raw
    } catch {
      # fallback: try raw webrequest
      try {
        $wr = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec $HttpTimeout -ErrorAction Stop
        $raw = $wr.Content
        $pairs = Parse-DaySchedule -respParsed $null -respRaw $raw
      } catch {
        Write-Host ("  {0}: error reading schedule ({1})" -f $d.ToUpper(), $_.Exception.Message) ; continue
      }
    }

    if (-not $pairs -or $pairs.Count -eq 0) {
      Write-Host ("  {0}: <no schedule or empty>" -f $d.ToUpper()) ; continue
    }

    Write-Host ("  {0}:" -f $d.ToUpper())
    foreach ($p in $pairs) {
      $ts = [TimeSpan]::FromMinutes([int]$p.Minutes)
      $timeStr = $ts.ToString('hh\:mm')
      $f = [double]$p.TempF
      $c = FtoC $f
      if ($unitPref -eq 'C') {
        Write-Host ("    {0} -> {1}°C ({2}°F)" -f $timeStr, $c, $f)
      } else {
        Write-Host ("    {0} -> {1}°F ({2}°C)" -f $timeStr, $f, $c)
      }
    }
  }
}

Write-Host "`nReading HEAT schedules for all discovered thermostats..."
foreach ($t in $discovered) {
  Print-ScheduleForThermostat -baseUri $t.BaseUri -name $t.Name -unitPref $Unit
}

Write-Host "`nDone."
