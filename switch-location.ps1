<#
.SYNOPSIS
    Location Configuration Switcher - SWITCH CONFIG ONLY

.DESCRIPTION
    Switches active config/config.yaml to point to different location.
    Does NOT start servers - just changes configuration.

.USAGE
    .\switch-location.ps1 -Location fram     # Switch to Framingham
    .\switch-location.ps1 -Location cape     # Switch to Cape House
    .\switch-location.ps1 -Location nh       # Switch to New Hampshire
    .\switch-location.ps1 -ShowCurrent -Location fram  # Show active config

.WHAT IT DOES
    - Changes config/config.yaml to selected location
    - Backs up current config before switching
    - Validates new configuration

.WHEN TO USE
    - To switch locations before using existing run_server.ps1
    - When you want to change config without running server
    - To check which config is currently active

.WORKFLOW
    1. .\switch-location.ps1 -Location fram
    2. .\run_server.ps1    # Uses switched config
#>

# Location Configuration Switcher
# Switches the active configuration without running the server

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("cape", "fram", "nh")]
    [string]$Location,
    
    [switch]$ShowCurrent
)

# Location mappings
$locations = @{
    "cape" = @{
        "name" = "Cape House"
        "config_file" = "config/config-cape.yaml"
    }
    "fram" = @{
        "name" = "Fram House" 
        "config_file" = "config/config-fram.yaml"
    }
    "nh" = @{
        "name" = "Mountain Home"
        "config_file" = "config/config-nh.yaml"
    }
}

function Get-CurrentLocation {
    if (-not (Test-Path "config/config.yaml")) {
        return "NONE"
    }
    
    try {
        $content = Get-Content "config/config.yaml" -Raw
        if ($content -match 'site_id:\s*"([^"]+)"') {
            $siteId = $matches[1]
            switch ($siteId) {
                "cape_home" { return "cape" }
                "fram_home" { return "fram" }
                "nh_home" { return "nh" }
                default { return "UNKNOWN" }
            }
        }
    } catch {
        return "ERROR"
    }
    
    return "UNKNOWN"
}

function Show-CurrentLocation {
    $current = Get-CurrentLocation
    
    Write-Host "Current Active Configuration:" -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($loc in $locations.Keys) {
        $location = $locations[$loc]
        $isActive = ($loc -eq $current)
        
        $prefix = if ($isActive) { "[ACTIVE]" } else { "        " }
        $color = if ($isActive) { "Green" } else { "Gray" }
        
        Write-Host "$prefix $($loc.ToUpper()): $($location.name)" -ForegroundColor $color
        
        $configExists = Test-Path $location.config_file
        $status = if ($configExists) { "EXISTS" } else { "MISSING" }
        $statusColor = if ($configExists) { "Green" } else { "Red" }
        
        Write-Host "         Config: $($location.config_file) - $status" -ForegroundColor $statusColor
    }
    
    Write-Host ""
    if ($current -eq "NONE") {
        Write-Host "No active configuration found (config/config.yaml missing)" -ForegroundColor Yellow
    } elseif ($current -eq "UNKNOWN") {
        Write-Host "Active configuration is not recognized" -ForegroundColor Yellow
    } elseif ($current -eq "ERROR") {
        Write-Host "Error reading active configuration" -ForegroundColor Red
    }
}

if ($ShowCurrent) {
    Show-CurrentLocation
    exit 0
}

$selectedLocation = $locations[$Location]

Write-Host "=== Location Configuration Switcher ===" -ForegroundColor Green
Write-Host ""

Show-CurrentLocation

Write-Host "Switching to: $($selectedLocation.name)" -ForegroundColor Yellow
Write-Host ""

# Check if source config exists
if (-not (Test-Path $selectedLocation.config_file)) {
    Write-Host "ERROR: Configuration file not found: $($selectedLocation.config_file)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Available config files:" -ForegroundColor Cyan
    Get-ChildItem "config/config*.yaml" | ForEach-Object {
        Write-Host "  $($_.Name)" -ForegroundColor Gray
    }
    exit 1
}

# Backup current config if it exists and is different
if (Test-Path "config/config.yaml") {
    $currentHash = Get-FileHash "config/config.yaml" -Algorithm MD5
    $newHash = Get-FileHash $selectedLocation.config_file -Algorithm MD5
    
    if ($currentHash.Hash -ne $newHash.Hash) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupName = "config/config_backup_$timestamp.yaml"
        Copy-Item "config/config.yaml" $backupName
        Write-Host "Backed up current config to: $backupName" -ForegroundColor Gray
    } else {
        Write-Host "Configuration is already set to $($selectedLocation.name)" -ForegroundColor Green
        exit 0
    }
}

# Copy the new config
Copy-Item $selectedLocation.config_file "config/config.yaml"

Write-Host "SUCCESS: Configuration switched to $($selectedLocation.name)" -ForegroundColor Green
Write-Host "Active config file: config/config.yaml" -ForegroundColor Gray
Write-Host ""

# Show site info from new config
try {
    $configTest = @"
from src.config_loader import load_config
config = load_config('config/config.yaml')
print(f"Site: {config['site']['site_name']} ({config['site']['site_id']})")
print(f"ZIP Code: {config['site']['zip_code']}")
print(f"Database Port: {config['database']['port']}")
"@
    
    $result = & .venv\Scripts\python.exe -c $configTest 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "New Configuration Details:" -ForegroundColor Cyan
        $result | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    }
} catch {
    # Ignore config validation errors for now
}

Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "  Run server: .\run-location.ps1 -Location $Location" -ForegroundColor White
Write-Host "  Or use existing script: .\run_server.ps1" -ForegroundColor White