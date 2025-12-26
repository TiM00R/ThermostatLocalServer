<#
.SYNOPSIS
  Discover CT50 / RadioThermostat devices in an IPv4 range (only /sys and /sys/name) and return objects with Name, IP, Version, BaseUri.

.DESCRIPTION
  - Minimal checks: requests /sys and /sys/name only.
  - Validates /sys content: accepts devices that provide fw_version, api_version, uuid, or a non-empty /sys/name (and rejects HTML status pages).
  - Outputs PSCustomObject items (Name, IP, Version, BaseUri) so this script can be consumed by other scripts.

.EXAMPLE
  # Get list into a variable for further scripting:
  $tstats = & .\Get-TstatsList.ps1 -Start 4 -End 15

  # Iterate and perform actions:
  foreach ($t in $tstats) {
    Write-Host "Doing action on $($t.Name) ($($t.IP))"
    # call your action function here, e.g. Set-TstatDailyHeat -Ip $t.IP -Temp 21 ...
  }

.EXAMPLE
  # Output machine-readable JSON (for non-PS consumers):
  .\Get-TstatsList.ps1 -Start 4 -End 15 -AsJson | Out-File thermostats.json

.PARAMETER BasePrefix
  First three octets, default '10.0.60'.

.PARAMETER Start, End
  Last-octet inclusive range to scan.

.PARAMETER TimeoutSec
  HTTP timeout in seconds (default 2).

.PARAMETER AsJson
  Emit JSON (instead of PS objects).

.PARAMETER AsCsv
  Emit CSV (instead of PS objects).

.PARAMETER ShowProgress
  Write a short progress message per IP (useful when running interactively).

#>

param(
  [string]$BasePrefix = '10.0.60',
  [Parameter(Mandatory=$true)][ValidateRange(1,254)][int]$Start,
  [Parameter(Mandatory=$true)][ValidateRange(1,254)][int]$End,
  [int]$TimeoutSec = 2,
  [switch]$AsJson = $false,
  [switch]$AsCsv = $false,
  [switch]$ShowProgress = $true
)

if ($End -lt $Start) { throw "End must be >= Start" }

function Try-Get {
  param([string]$Url)
  $out = [ordered]@{ Url = $Url; Parsed = $null; Raw = $null; Ok = $false; Err = $null }
  try {
    $parsed = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec $TimeoutSec -ErrorAction Stop
    $out.Parsed = $parsed
    try { $out.Raw = ($parsed | ConvertTo-Json -Depth 6) } catch { $out.Raw = ($parsed | Out-String) }
    $out.Ok = $true
  } catch {
    $out.Err = $_
    # fallback: attempt raw fetch to capture HTML or text
    try {
      $wr = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec $TimeoutSec -ErrorAction Stop
      $out.Raw = $wr.Content
      $out.Ok = $true
    } catch {
      $out.Err = ($out.Err.ToString() + " | " + $_.ToString())
    }
  }
  # If parsed is XML/HtmlDocument, keep OuterXml for raw
  if ($out.Parsed -and ($out.Parsed -is [System.Xml.XmlDocument] -or $out.Parsed -is [System.Xml.XmlNode])) {
    try { $out.Raw = $out.Parsed.OuterXml } catch {}
  }
  return $out
}

function LooksLikeHtmlStatus {
  param([string]$s)
  if (-not $s) { return $false }
  $low = $s.ToLower()
  return ($low -match '<html' -or $low -match '200 ok' -or $low -match '<title>')
}

function IsThermostat {
  param($sysResp, $nameResp)
  # If parsed object exists with known keys -> accept
  if ($sysResp -and $sysResp.Ok -and $sysResp.Parsed) {
    $p = $sysResp.Parsed
    if ($p -is [System.Management.Automation.PSCustomObject]) {
      foreach ($k in @('fw_version','api_version','uuid','wlan_fw_version')) {
        if ($p.PSObject.Properties.Name -contains $k -and $p.$k) { return $true }
      }
      # accept if there's at least one non-empty property (guard vs nested empty arrays)
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
      # scan nested arrays/objects for known keys
      foreach ($elem in $p) {
        if ($elem -is [System.Management.Automation.PSCustomObject]) {
          foreach ($k in @('fw_version','api_version','uuid')) {
            if ($elem.PSObject.Properties.Name -contains $k -and $elem.$k) { return $true }
          }
        }
      }
    }
  }

  # If sys raw looks like an HTML status page, reject unless /sys/name proves otherwise
  if ($sysResp -and $sysResp.Raw) {
    if (LooksLikeHtmlStatus -s $sysResp.Raw) {
      if ($nameResp -and $nameResp.Ok -and $nameResp.Parsed -and ($nameResp.Parsed -is [string]) -and ($nameResp.Parsed.Trim().Length -gt 0) -and -not (LooksLikeHtmlStatus -s $nameResp.Raw)) {
        return $true
      }
      return $false
    }
  }

  # fallback: accept if /sys/name returns a plain non-empty string (not HTML)
  if ($nameResp -and $nameResp.Ok -and $nameResp.Parsed) {
    if ($nameResp.Parsed -is [string]) {
      $s = $nameResp.Parsed.Trim()
      if ($s.Length -gt 0 -and -not (LooksLikeHtmlStatus -s $nameResp.Raw)) { return $true }
    }
    if ($nameResp.Parsed -is [System.Management.Automation.PSCustomObject]) {
      if ($nameResp.Parsed.PSObject.Properties.Name -contains 'name' -and $nameResp.Parsed.name) { return $true }
    }
  }

  return $false
}

function ExtractInfo {
  param($sysResp, $nameResp)
  $name = '<unknown>'; $version = '<n/a>'; $baseUri = $null
  # Try name from /sys/name first
  if ($nameResp -and $nameResp.Ok -and $nameResp.Parsed) {
    if ($nameResp.Parsed -is [string]) { $name = $nameResp.Parsed.Trim() }
    elseif ($nameResp.Parsed -is [System.Management.Automation.PSCustomObject]) {
      if ($nameResp.Parsed.PSObject.Properties.Name -contains 'name' -and $nameResp.Parsed.name) { $name = [string]$nameResp.Parsed.name }
    }
  }
  # If still unknown, try from /sys parsed object
  if ($name -eq '<unknown>' -and $sysResp -and $sysResp.Ok -and $sysResp.Parsed -and ($sysResp.Parsed -is [System.Management.Automation.PSCustomObject])) {
    foreach ($k in @('name','hostname','device','model')) {
      if ($sysResp.Parsed.PSObject.Properties.Name -contains $k -and $sysResp.Parsed.$k) { $name = [string]$sysResp.Parsed.$k; break }
    }
  }
  # Version
  if ($sysResp -and $sysResp.Ok -and $sysResp.Parsed -and ($sysResp.Parsed -is [System.Management.Automation.PSCustomObject])) {
    if ($sysResp.Parsed.PSObject.Properties.Name -contains 'fw_version' -and $sysResp.Parsed.fw_version) { $version = [string]$sysResp.Parsed.fw_version }
    elseif ($sysResp.Parsed.PSObject.Properties.Name -contains 'api_version' -and $sysResp.Parsed.api_version) { $version = "api:$($sysResp.Parsed.api_version)" }
  } elseif ($nameResp -and $nameResp.Ok -and $nameResp.Parsed -is [System.Management.Automation.PSCustomObject]) {
    # sometimes name endpoint returns object with info
    if ($nameResp.Parsed.PSObject.Properties.Name -contains 'fw_version' -and $nameResp.Parsed.fw_version) { $version = [string]$nameResp.Parsed.fw_version }
  }

  return @{ Name = $name; Version = $version }
}

# main
$resultList = @()

for ($i = $Start; $i -le $End; $i++) {
  $ip = "$BasePrefix.$i"
  if ($ShowProgress) { Write-Host -NoNewline ("Checking {0} ... " -f $ip) }

  # Build base URL (assume http)
  $base = "http://$ip"

  $sysResp  = Try-Get -Url ("$base/sys")
  $nameResp = Try-Get -Url ("$base/sys/name")

  if ($ShowProgress) {
    if (($sysResp -and $sysResp.Ok) -or ($nameResp -and $nameResp.Ok)) { Write-Host "api response" } else { Write-Host "no response" }
  }

  if (-not (IsThermostat -sysResp $sysResp -nameResp $nameResp)) {
    continue
  }

  $info = ExtractInfo -sysResp $sysResp -nameResp $nameResp

  $obj = [PSCustomObject]@{
    Name    = $info.Name
    IP      = $ip
    Version = $info.Version
    BaseUri = $base
  }

  $resultList += $obj
}

# Output: either objects, JSON, or CSV (machine-friendly)
if ($AsJson) {
  $resultList | ConvertTo-Json -Depth 6
  return
}

if ($AsCsv) {
  $resultList | Select-Object Name,IP,Version,BaseUri | ConvertTo-Csv -NoTypeInformation
  return
}

# Default: emit PS objects so other scripts can consume them directly
$resultList
