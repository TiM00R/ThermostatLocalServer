param(
  [string]$CaPath   = 'D:\ThermostatLocalServer\certs\thermo-ca.crt',
  [string]$PublicIP = 'YOUR_PUBLIC_IP_HERE'
)

# --- Admin check ---
$wi = [Security.Principal.WindowsIdentity]::GetCurrent()
$wp = New-Object Security.Principal.WindowsPrincipal $wi
if (-not $wp.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Error 'Please run this script in an **elevated** PowerShell (Run as Administrator).'
  exit 1
}

# --- Validate CA file ---
if (-not (Test-Path -Path $CaPath)) {
  Write-Error "CA file not found: $CaPath"
  exit 2
}

# --- Install CA into LocalMachine\Root ---
$import = Import-Certificate -FilePath $CaPath -CertStoreLocation 'Cert:\LocalMachine\Root' -ErrorAction Stop

# --- Show the installed CA (by Subject) ---
Get-ChildItem 'Cert:\LocalMachine\Root' |
  Where-Object { $_.Subject -like '*Thermostat Local CA*' } |
  Format-List Subject, Thumbprint, NotBefore, NotAfter

# --- Force TLS 1.2 (helps older hosts) ---
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# --- Test HTTPS ---
$healthUrl = "https://$PublicIP`:8001/health"
try {
  $r = Invoke-WebRequest $healthUrl -TimeoutSec 10
  Write-Host "OK: $healthUrl  Status=$($r.StatusCode)"
  exit 0
}
catch {
  Write-Error "HTTPS test failed for $healthUrl"
  Write-Error $_.Exception.Message
  exit 3
}
