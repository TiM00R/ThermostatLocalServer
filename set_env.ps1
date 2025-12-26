# RadioThermostat CT50 - Environment Setup and Activation
# Checks for .venv, creates if needed, and activates it


Write-Host ""
Write-Host "[ENV] RadioThermostat CT50 - Environment Check" -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green
Write-Host "To remove old env: "
Write-Host "Remove-Item -Path '.venv' -Recurse -Force"
Write-Host ""

# Check if .venv exists
if (Test-Path ".venv\Scripts\python.exe") {
    Write-Host "[OK] Virtual environment exists" -ForegroundColor Green
} else {
    Write-Host "[CREATE] Virtual environment not found, creating..." -ForegroundColor Yellow
    
    # Check if Python is available
    try {
        $pythonVersion = python --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Python found: $pythonVersion" -ForegroundColor Green
        } else {
            throw "Python not found"
        }
    } catch {
        Write-Host "[ERROR] Python is not installed or not in PATH" -ForegroundColor Red
        exit 1
    }
    
    # Remove any broken .venv directory
    if (Test-Path ".venv") {
        Write-Host "[CLEANUP] Removing broken virtual environment..." -ForegroundColor Yellow
        Remove-Item -Path ".venv" -Recurse -Force
    }
    
    # Create fresh virtual environment
    Write-Host "[CREATE] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    
    # Install dependencies
    Write-Host "[INSTALL] Installing dependencies..." -ForegroundColor Yellow
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "[OK] Virtual environment created and configured" -ForegroundColor Green
}

# Activate the environment
Write-Host ""
Write-Host "[ACTIVATE] Activating virtual environment..." -ForegroundColor Yellow

# Try PowerShell activation first
$activateScript = ".venv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    try {
        & $activateScript
        Write-Host "[OK] Environment activated via PowerShell script" -ForegroundColor Green
    } catch {
        Write-Host "[WARNING] PowerShell activation failed: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "[INFO] You can still use: .venv\Scripts\python.exe" -ForegroundColor Cyan
    }
} else {
    Write-Host "[WARNING] Activate.ps1 not found" -ForegroundColor Yellow
    Write-Host "[INFO] You can use: .venv\Scripts\python.exe" -ForegroundColor Cyan
}

# Verify environment
Write-Host ""
Write-Host "[VERIFY] Environment verification:" -ForegroundColor Yellow
try {
    & ".venv\Scripts\python.exe" -c "import aiohttp, asyncio; print('[OK] All packages available')"
} catch {
    Write-Host "[ERROR] Package verification failed" -ForegroundColor Red
}

Write-Host ""
Write-Host "[READY] Environment is ready!" -ForegroundColor Green
Write-Host "[INFO] Python executable: .venv\Scripts\python.exe" -ForegroundColor Cyan
Write-Host "[NEXT] Run discovery test: .venv\Scripts\python.exe tests\test_discovery.py" -ForegroundColor Cyan
Write-Host ""