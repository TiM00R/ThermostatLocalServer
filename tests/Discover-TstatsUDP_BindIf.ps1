<#
.SYNOPSIS
  SSDP discovery (M-SEARCH) for RadioThermostat/CT50 devices with optional binding to a specific local interface.

.DESCRIPTION
  - Sends an SSDP M-SEARCH (ST=com.rtcoa.tstat* by default) to 239.255.255.250:1900
  - Optionally binds the UDP socket to a specific local IP/interface so the multicast/outbound traffic uses that interface
  - Collects LOCATION headers and verifies devices by querying /sys and /sys/name
#>

param(
  [int]$TimeoutSeconds = 4,
  [string]$St = "com.rtcoa.tstat*",
  [int]$MSearchPort = 1900,
  [string]$MSearchAddress = "239.255.255.250",
  [int]$HttpTimeout = 6,
  [string]$LocalAddress = $null,   # <-- new: local IP to bind to (optional)
  [switch]$ShowRaw = $false
)

function Write-ErrAndExit($msg) { Write-Error $msg; exit 1 }

# Validate LocalAddress if provided
if ($LocalAddress) {
  try {
    [void][System.Net.IPAddress]::Parse($LocalAddress)
  } catch {
    Write-ErrAndExit "LocalAddress '$LocalAddress' is not a valid IPv4/IPv6 address."
  }
}

# Build M-SEARCH payload (CRLF normalized)
$msearch = @"
M-SEARCH * HTTP/1.1
HOST: ${MSearchAddress}:$MSearchPort
MAN: "ssdp:discover"
MX: 2
ST: $St

"@ -replace "`r?`n", "`r`n"

Write-Host "SSDP M-SEARCH (ST=$St) -> ${MSearchAddress}:$MSearchPort (listening $TimeoutSeconds s)..."
if ($LocalAddress) { Write-Host "Binding UDP socket to local address: $LocalAddress" }

function Parse-HttpHeaders {
  param([string]$raw)
  $headers = @{}
  $lines = $raw -split "`r?`n"
  foreach ($line in $lines) {
    if ($line -match "^\s*$") { continue }
    if ($line -match "^\s*([^:]+):\s*(.+)$") {
      $name = $matches[1].Trim().ToUpper()
      $value = $matches[2].Trim()
      $headers[$name] = $value
    }
  }
  return $headers
}

# Create and bind UDP client
$udp = $null
try {
  if ($LocalAddress) {
    # Bind to specific local endpoint (port 0 lets OS pick ephemeral port)
    $localEP = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($LocalAddress), 0)
    $udp = New-Object System.Net.Sockets.UdpClient($localEP)
  } else {
    # default behavior: OS chooses source/interface
    $udp = New-Object System.Net.Sockets.UdpClient
  }

  # Set options: TTL and receive timeout for the underlying socket
  $udp.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IP, [System.Net.Sockets.SocketOptionName]::MulticastTimeToLive, 2)
  $udp.Client.ReceiveTimeout = 1000
} catch {
  Write-ErrAndExit "Failed to create/bind UDP client: $_"
}

# Send M-SEARCH and collect unique LOCATIONs
$locations = [System.Collections.Generic.HashSet[string]]::new()
try {
  $endpoint = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($MSearchAddress)), $MSearchPort
  $bytes = [System.Text.Encoding]::ASCII.GetBytes($msearch)
  $udp.Send($bytes, $bytes.Length, $endpoint) | Out-Null

  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
    try {
      $remoteEP = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any), 0
      $respBytes = $udp.Receive([ref]$remoteEP)
      if (-not $respBytes) { continue }
      $raw = [System.Text.Encoding]::ASCII.GetString($respBytes)
      $hdrs = Parse-HttpHeaders -raw $raw
      if ($hdrs.ContainsKey("LOCATION")) {
        try {
          $uri = [Uri]$hdrs["LOCATION"]
          $locations.Add($uri.AbsoluteUri) | Out-Null
        } catch {
          $locations.Add($hdrs["LOCATION"].Trim()) | Out-Null
        }
      }
    } catch [System.Net.Sockets.SocketException] {
      # receive timeout; continue until overall timeout
      continue
    } catch {
      continue
    }
  }
} finally {
  $udp.Close()
}

if ($locations.Count -eq 0) {
  Write-Host "No SSDP LOCATION responses found in $TimeoutSeconds seconds."
  exit 0
}

Write-Host "Found $($locations.Count) LOCATION(s). Verifying via /sys and /sys/name..."

function Fetch-SysAndName {
  param($baseUri)
  $out = [ordered]@{ Base = $baseUri; Sys = $null; Name = $null; SysRaw = $null; NameRaw = $null }
  $sysUrl = "$baseUri/sys"
  $nameUrl = "$baseUri/sys/name"
  try {
    $parsed = Invoke-RestMethod -Uri $sysUrl -Method Get -TimeoutSec $HttpTimeout -ErrorAction Stop
    $out.Sys = $parsed
    try { $out.SysRaw = ($parsed | ConvertTo-Json -Depth 6) } catch { $out.SysRaw = ($parsed | Out-String) }
  } catch {
    try {
      $wr = Invoke-WebRequest -Uri $sysUrl -Method Get -TimeoutSec $HttpTimeout -ErrorAction Stop
      $out.SysRaw = $wr.Content
    } catch { $out.SysRaw = $null }
  }
  try {
    $parsed = Invoke-RestMethod -Uri $nameUrl -Method Get -TimeoutSec $HttpTimeout -ErrorAction Stop
    $out.Name = $parsed
    try { $out.NameRaw = ($parsed | ConvertTo-Json -Depth 6) } catch { $out.NameRaw = ($parsed | Out-String) }
  } catch {
    try {
      $wr = Invoke-WebRequest -Uri $nameUrl -Method Get -TimeoutSec $HttpTimeout -ErrorAction Stop
      $out.NameRaw = $wr.Content
    } catch { $out.NameRaw = $null }
  }
  return $out
}

function Looks-Like-HttpStatus {
  param([string]$s)
  if (-not $s) { return $false }
  $l = $s.ToLower()
  return ($l -match '<html' -or $l -match '200 ok' -or $l -match '<title>')
}

function Is-Thermostat {
  param($fetch)
  if ($fetch.Sys -is [System.Management.Automation.PSCustomObject]) {
    foreach ($k in @('fw_version','api_version','uuid','wlan_fw_version')) {
      if ($fetch.Sys.PSObject.Properties.Name -contains $k -and $fetch.Sys.$k) { return $true }
    }
    foreach ($prop in $fetch.Sys.PSObject.Properties) {
      $val = $prop.Value
      if ($null -ne $val) {
        if ($val -is [System.Array]) {
          if ($val.Count -gt 0) { return $true }
        } else { return $true }
      }
    }
  }
  if ($fetch.SysRaw -and (Looks-Like-HttpStatus -s $fetch.SysRaw)) {
    if ($fetch.Name -and ($fetch.Name -is [string]) -and ($fetch.Name.Trim().Length -gt 0) -and -not (Looks-Like-HttpStatus -s $fetch.NameRaw)) {
      return $true
    }
    return $false
  }
  if ($fetch.Name -and ($fetch.Name -is [string])) {
    $s = $fetch.Name.Trim()
    if ($s.Length -gt 0 -and -not (Looks-Like-HttpStatus -s $fetch.NameRaw)) { return $true }
  }
  return $false
}

function Extract-Info {
  param($fetch)
  $name = '<unknown>'; $version = '<n/a>'
  if ($fetch.Name -and ($fetch.Name -is [string])) { $name = $fetch.Name.Trim() }
  elseif ($fetch.Sys -is [System.Management.Automation.PSCustomObject]) {
    foreach ($k in @('name','hostname','device','model')) {
      if ($fetch.Sys.PSObject.Properties.Name -contains $k -and $fetch.Sys.$k) { $name = [string]$fetch.Sys.$k; break }
    }
  } elseif ($fetch.SysRaw) {
    try {
      $j = $fetch.SysRaw | ConvertFrom-Json -ErrorAction Stop
      if ($j -is [System.Management.Automation.PSCustomObject]) {
        foreach ($k in @('name','model')) {
          if ($j.PSObject.Properties.Name -contains $k -and $j.$k) { $name = [string]$j.$k; break }
        }
      }
    } catch {}
  }
  if ($fetch.Sys -is [System.Management.Automation.PSCustomObject]) {
    if ($fetch.Sys.PSObject.Properties.Name -contains 'fw_version' -and $fetch.Sys.fw_version) { $version = [string]$fetch.Sys.fw_version }
    elseif ($fetch.Sys.PSObject.Properties.Name -contains 'api_version' -and $fetch.Sys.api_version) { $version = "api:$($fetch.Sys.api_version)" }
  }
  return @{ Name = $name; Version = $version }
}

$results = @()
foreach ($loc in $locations) {
  try { $u = [Uri]$loc } catch { continue }
  $base = ("{0}://{1}:{2}" -f $u.Scheme, $u.Host, $u.Port)
  $fetch = Fetch-SysAndName -baseUri $base

  if ($ShowRaw) {
    Write-Host "`n== LOCATION: $loc = base $base =="
    if ($fetch.SysRaw) { Write-Host "  /sys raw (snippet):"; ($fetch.SysRaw -replace "`r","") -split "`n" | Select-Object -First 6 | ForEach-Object { Write-Host "    $_" } }
    if ($fetch.NameRaw) { Write-Host "  /sys/name raw (snippet):"; ($fetch.NameRaw -replace "`r","") -split "`n" | Select-Object -First 6 | ForEach-Object { Write-Host "    $_" } }
  }

  if (-not (Is-Thermostat -fetch $fetch)) {
    if ($ShowRaw) { Write-Host "  Not recognized as thermostat (skipping)." }
    continue
  }

  $info = Extract-Info -fetch $fetch
  $results += [PSCustomObject]@{
    Name = $info.Name
    IP = $u.Host
    Version = $info.Version
    Location = $loc
  }
}

if ($results.Count -eq 0) {
  Write-Host "No thermostats discovered/verified."
  exit 0
}

$results | Sort-Object {[System.Net.IPAddress]::Parse($_.IP).GetAddressBytes()} `
  | Group-Object -Property IP -AsHashTable -AsString `
  | ForEach-Object { $_.Value[0] } `
  | Format-Table -AutoSize @{Label='Name';Expression={$_.Name}}, IP, @{Label='Version';Expression={$_.Version}}, @{Label='Location';Expression={$_.Location}}
