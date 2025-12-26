<#
.SYNOPSIS
  Discover devices using SSDP M-SEARCH and attempt to read thermostat info (via /sys).

.DESCRIPTION
  - Sends a single SSDP M-SEARCH over UDP multicast to 239.255.255.250:1900.
  - Listens for responses during the specified timeout window.
  - Parses each response for a LOCATION header (URL) and queries that host's /sys endpoint.
  - Prints a compact table of discovered devices: Name, IP, Version, LOCATION URL.
  - Adjustable timeout (seconds) and optional custom ST (search target).

.NOTES
  - SSDP responses are UDP replies which often include a LOCATION header pointing to a device description URL.
  - Many CT50/RadioThermostat devices respond via SSDP; success depends on network configuration (multicast allowed).
  - If your network blocks multicast/UDP, this will not find devices.
#>

param(
  [int]$TimeoutSeconds = 4,
  [string]$St = "ssdp:all",     # search target; device-specific ST may be used if known
  [int]$MSearchPort = 1900,
  [string]$MSearchAddress = "239.255.255.250"
)

# Build M-SEARCH payload
$msearch = @"
M-SEARCH * HTTP/1.1
HOST: ${MSearchAddress}:$MSearchPort
MAN: "ssdp:discover"
MX: 2
ST: $St

"@ -replace "`r?`n", "`r`n"  # normalize line endings

Write-Host "Sending SSDP M-SEARCH (ST=$St), listening for $TimeoutSeconds seconds..."

# helper: parse headers from raw UDP response string
function Parse-HttpHeaders {
  param([string]$raw)
  $headers = @{}
  $lines = $raw -split "`r?`n"
  foreach ($line in $lines) {
    if ($line -match "^\s*$") { continue }
    if ($line -match "^\s*[A-Za-z0-9\-]+:\s*(.+)$") {
      $name = ($line -split ":",2)[0].Trim().ToUpper()
      $value = ($line -split ":",2)[1].Trim()
      $headers[$name] = $value
    }
  }
  return $headers
}

# Send UDP multicast and collect responses in a list
$locations = [System.Collections.Generic.HashSet[string]]::new()

$udp = New-Object System.Net.Sockets.UdpClient
try {
  # Allow sending to multicast; set TTL so it stays on local network
  $udp.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IP, [System.Net.Sockets.SocketOptionName]::MulticastTimeToLive, 2)
  $udp.Client.ReceiveTimeout = 1000  # initial short timeout for Receive
  $endpoint = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($MSearchAddress)), $MSearchPort

  $bytes = [System.Text.Encoding]::ASCII.GetBytes($msearch)
  $udp.Send($bytes, $bytes.Length, $endpoint) | Out-Null

  $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
  while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
    try {
      $remoteEP = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any), 0
      $respBytes = $udp.Receive([ref]$remoteEP)   # blocks until data or timeout
      if (-not $respBytes) { continue }
      $raw = [System.Text.Encoding]::ASCII.GetString($respBytes)
      $hdrs = Parse-HttpHeaders -raw $raw

      # prefer LOCATION header
      if ($hdrs.ContainsKey("LOCATION")) {
        $loc = $hdrs["LOCATION"]
        # normalize and store unique (HashSet)
        try { $uri = [Uri]$loc; $norm = $uri.AbsoluteUri } catch { $norm = $loc.Trim() }
        $locations.Add($norm) | Out-Null
      } else {
        # some devices put location-like info in other headers (optional)
        if ($hdrs.ContainsKey("URL")) {
          $locations.Add($hdrs["URL"].Trim()) | Out-Null
        }
      }
    } catch [System.Net.Sockets.SocketException] {
      # timeout occurred on Receive; continue loop and check total timeout
      continue
    } catch {
      continue
    }
  }
} finally {
  $udp.Close()
}

if ($locations.Count -eq 0) {
  Write-Host "No SSDP responses with LOCATION received within $TimeoutSeconds seconds."
  exit 0
}

Write-Host "Found {0} unique LOCATION(s). Querying /sys for each device..." -f $locations.Count

# For each LOCATION, attempt to query its host /sys (some LOCATIONs point directly to device XML)
$results = @()
foreach ($loc in $locations) {
  # extract host/ip from the LOCATION URI; if LOCATION points to a path on the device, build base URL
  try {
    $u = [Uri]$loc
    $base = ("{0}://{1}" -f $u.Scheme, $u.Host)
    $sysUrl = "$base/sys"
    # Try fetching /sys; if that fails, attempt to fetch the LOCATION itself (some devices only host XML there)
    $sysResp = $null
    try {
      $sysResp = Invoke-RestMethod -Uri $sysUrl -Method Get -TimeoutSec 6 -ErrorAction Stop
    } catch {
      # fallback: try the LOCATION url - this may be device description XML
      try { $desc = Invoke-WebRequest -Uri $loc -Method Get -TimeoutSec 6 -ErrorAction Stop; $descContent = $desc.Content } catch { $descContent = $null }
      $sysResp = $null
    }

    # Extract info for table
    $name = "<unknown>"
    $version = "<n/a>"

    if ($sysResp) {
      # parsed JSON likely
      if ($sysResp -is [System.Management.Automation.PSCustomObject]) {
        if ($sysResp.PSObject.Properties.Name -contains 'name' -and $sysResp.name) { $name = [string]$sysResp.name }
        elseif ($sysResp.PSObject.Properties.Name -contains 'device' -and $sysResp.device) { $name = [string]$sysResp.device }
        elseif ($sysResp.PSObject.Properties.Name -contains 'model' -and $sysResp.model) { $name = [string]$sysResp.model }
        if ($sysResp.PSObject.Properties.Name -contains 'fw_version' -and $sysResp.fw_version) { $version = [string]$sysResp.fw_version }
        elseif ($sysResp.PSObject.Properties.Name -contains 'api_version' -and $sysResp.api_version) { $version = "api:$($sysResp.api_version)" }
      } else {
        # treat scalar string as name
        if ($sysResp -is [string]) { $name = $sysResp.Trim() }
      }
    } elseif ($descContent) {
      # try extract <modelName> or <friendlyName> or title from device description XML/HTML
      if ($descContent -match '<friendlyName[^>]*>([^<]+)</friendlyName>') { $name = $matches[1].Trim() }
      elseif ($descContent -match '<modelName[^>]*>([^<]+)</modelName>') { $name = $matches[1].Trim() }
      elseif ($descContent -match '<title[^>]*>([^<]+)</title>') { $name = $matches[1].Trim() }
      else {
        # use first non-empty line as fallback
        $first = ($descContent -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 } | Select-Object -First 1)
        if ($first) { $name = $first.Trim() }
      }
    }

    $results += [PSCustomObject]@{
      Name = $name
      IP = $u.Host
      Version = $version
      Location = $loc
    }
  } catch {
    # skip malformed LOCATIONs
    continue
  }
}

if ($results.Count -eq 0) {
  Write-Host "No devices returned usable /sys or description content."
  exit 0
}

# De-duplicate by IP and print table
$results | Sort-Object {[System.Net.IPAddress]::Parse($_.IP).GetAddressBytes()} `
  | Sort-Object IP -Unique `
  | Format-Table -AutoSize @{Label='Name';Expression={$_.Name}}, IP, @{Label='Version';Expression={$_.Version}}, @{Label='Location';Expression={$_.Location}}
