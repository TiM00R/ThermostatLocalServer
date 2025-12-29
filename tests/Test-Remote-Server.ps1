# Test Remote Public Server Connection (FIXED VERSION)
# Tests connectivity to the remote public server

param(
    [string]$PublicServerIP,
    [string]$Port = "8001"
)

Write-Host "=== TESTING REMOTE PUBLIC SERVER ===" -ForegroundColor Green
Write-Host ""

$HttpURL = "http://${PublicServerIP}:${Port}"
$HttpsURL = "https://${PublicServerIP}:${Port}"

Write-Host "Target Server: ${PublicServerIP}:$Port" -ForegroundColor Cyan
Write-Host ""

# Test HTTP
Write-Host "Testing HTTP connection: $HttpURL" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$HttpURL/health" -TimeoutSec 15 -UseBasicParsing -ErrorAction Stop
    Write-Host "  ✅ HTTP CONNECTION SUCCESSFUL" -ForegroundColor Green
    Write-Host "  Status: $($response.StatusCode)" -ForegroundColor Gray
    Write-Host "  Response: $($response.Content)" -ForegroundColor Gray
    $httpWorks = $true
} catch {
    Write-Host "  ❌ HTTP connection failed: $($_.Exception.Message)" -ForegroundColor Red
    $httpWorks = $false
}

Write-Host ""

# Test HTTPS
Write-Host "Testing HTTPS connection: $HttpsURL" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$HttpsURL/health" -TimeoutSec 15 -UseBasicParsing -SkipCertificateCheck -ErrorAction Stop
    Write-Host "  ✅ HTTPS CONNECTION SUCCESSFUL" -ForegroundColor Green
    Write-Host "  Status: $($response.StatusCode)" -ForegroundColor Gray
    Write-Host "  Response: $($response.Content)" -ForegroundColor Gray
    $httpsWorks = $true
} catch {
    Write-Host "  ❌ HTTPS connection failed: $($_.Exception.Message)" -ForegroundColor Red
    $httpsWorks = $false
}

Write-Host ""

# Network diagnostics
Write-Host "=== NETWORK DIAGNOSTICS ===" -ForegroundColor Cyan

# Test basic connectivity (FIXED VERSION)
Write-Host "Testing basic network connectivity (ping)..." -ForegroundColor Yellow
try {
    $pingResult = Test-Connection -ComputerName $PublicServerIP -Count 2 -Quiet -ErrorAction Stop
    if ($pingResult) {
        Write-Host "  ✅ Server is reachable via ping" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Server is not reachable via ping" -ForegroundColor Red
    }
} catch {
    Write-Host "  ❌ Ping failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  This could indicate network connectivity issues" -ForegroundColor Yellow
}

Write-Host ""

# Test if port is open
Write-Host "Testing if port $Port is open..." -ForegroundColor Yellow
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $connection = $tcpClient.BeginConnect($PublicServerIP, $Port, $null, $null)
    $wait = $connection.AsyncWaitHandle.WaitOne(5000, $false)
    
    if ($wait) {
        $tcpClient.EndConnect($connection)
        Write-Host "  ✅ Port $Port is open and accepting connections" -ForegroundColor Green
        $tcpClient.Close()
    } else {
        Write-Host "  ❌ Port $Port is not responding (timeout)" -ForegroundColor Red
        Write-Host "  Server may not be running or port may be blocked" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ❌ Cannot connect to port ${Port}: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Simple connectivity test using telnet-style connection
Write-Host "Testing raw TCP connection..." -ForegroundColor Yellow
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpClient.ReceiveTimeout = 5000
    $tcpClient.SendTimeout = 5000
    $tcpClient.Connect($PublicServerIP, $Port)
    
    if ($tcpClient.Connected) {
        Write-Host "  ✅ TCP connection established successfully" -ForegroundColor Green
    }
    $tcpClient.Close()
} catch {
    Write-Host "  ❌ TCP connection failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Recommendations
Write-Host "=== RECOMMENDATIONS ===" -ForegroundColor Magenta
Write-Host ""

if ($httpWorks -and -not $httpsWorks) {
    Write-Host "✅ PUBLIC SERVER IS RUNNING IN HTTP MODE" -ForegroundColor Green
    Write-Host ""
    Write-Host "Configure your local server for HTTP:" -ForegroundColor White
    Write-Host ".\Fix-Remote-Server-Config.ps1 -Protocol http" -ForegroundColor Cyan
    
} elseif ($httpsWorks -and -not $httpWorks) {
    Write-Host "✅ PUBLIC SERVER IS RUNNING IN HTTPS MODE" -ForegroundColor Green
    Write-Host ""
    Write-Host "Configure your local server for HTTPS:" -ForegroundColor White
    Write-Host ".\Fix-Remote-Server-Config.ps1 -Protocol https" -ForegroundColor Cyan
    
} elseif ($httpWorks -and $httpsWorks) {
    Write-Host "✅ PUBLIC SERVER SUPPORTS BOTH HTTP AND HTTPS" -ForegroundColor Green
    Write-Host ""
    Write-Host "Choose your preferred mode:" -ForegroundColor White
    Write-Host "For HTTP:  .\Fix-Remote-Server-Config.ps1 -Protocol http" -ForegroundColor Cyan
    Write-Host "For HTTPS: .\Fix-Remote-Server-Config.ps1 -Protocol https" -ForegroundColor Cyan
    
} else {
    Write-Host "❌ PUBLIC SERVER IS NOT RESPONDING" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible issues:" -ForegroundColor Yellow
    Write-Host "• Public server is not running" -ForegroundColor White
    Write-Host "• Server is running on a different port" -ForegroundColor White
    Write-Host "• Firewall is blocking connections" -ForegroundColor White
    Write-Host "• Network connectivity issues" -ForegroundColor White
    Write-Host ""
    Write-Host "Contact your server administrator or check:" -ForegroundColor White
    Write-Host "• Server logs on $PublicServerIP" -ForegroundColor Gray
    Write-Host "• Firewall settings" -ForegroundColor Gray
    Write-Host "• AWS Security Groups (if using AWS)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== MANUAL TEST COMMANDS ===" -ForegroundColor Cyan
Write-Host "You can also test manually with these commands:" -ForegroundColor Gray
Write-Host ""
Write-Host "# Test HTTP:" -ForegroundColor Gray
Write-Host "Invoke-WebRequest -Uri `"$HttpURL/health`" -TimeoutSec 10" -ForegroundColor White
Write-Host ""
Write-Host "# Test HTTPS:" -ForegroundColor Gray
Write-Host "Invoke-WebRequest -Uri `"$HttpsURL/health`" -TimeoutSec 10 -SkipCertificateCheck" -ForegroundColor White

Write-Host ""
Write-Host "Current server details:" -ForegroundColor Gray
Write-Host "IP: $PublicServerIP" -ForegroundColor Gray
Write-Host "Port: $Port" -ForegroundColor Gray
Write-Host "HTTP URL: $HttpURL" -ForegroundColor Gray
Write-Host "HTTPS URL: $HttpsURL" -ForegroundColor Gray
