param(
  [string]$CaPath = 'D:\ThermostatLocalServer\certs\thermo-ca.crt',
  [Parameter(Mandatory=$true)]
  [string]$PublicIP
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

# --- Test HTTPS connection to public server ---
Write-Host "`nTesting HTTPS connection to ${PublicIP}:8001..." -ForegroundColor Cyan
try {
  $response = Invoke-WebRequest -Uri "https://${PublicIP}:8001/api/v1/health" -UseBasicParsing -TimeoutSec 10
  Write-Host "SUCCESS: Connected to public server (Status: $($response.StatusCode))" -ForegroundColor Green
} catch {
  Write-Warning "Could not connect to public server: $_"
  Write-Host "This is normal if the server is not running or firewall is blocking." -ForegroundColor Yellow
}

Write-Host "`nCA certificate installed successfully!" -ForegroundColor Green
