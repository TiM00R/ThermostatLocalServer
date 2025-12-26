<#
.SYNOPSIS
    Multi-Location Thermostat Server Setup - INITIAL SETUP SCRIPT

.DESCRIPTION
    Sets up multi-location architecture with separate databases and configs.
    Run ONCE when transitioning from single-location to multi-location setup.

.USAGE
    .\setup-multi-location.ps1              # Full setup (run once)
    .\setup-multi-location.ps1 -ShowStatus  # Check current status only

.WHAT IT DOES
    - Creates separate database folders (postgres_cape, postgres_fram, postgres_nh)
    - Moves existing data to proper location folders
    - Creates missing config files for each location
    - Sets up complete multi-location structure

.WHEN TO USE
    - First time setting up multi-location
    - After moving existing single-location setup
    - To check current multi-location status

.NOTE
    All locations use the same port (5433) since only one location runs at a time.
    This avoids port conflicts and simplifies configuration.
#>

# Multi-Location Thermostat Server Setup Script
# Configures separate databases and configs for each location

param(
    [switch]$SetupOnly,  # Just setup folders and configs, don't run server
    [switch]$ShowStatus  # Show current configuration status
)

Write-Host "=== Multi-Location Thermostat Server Setup ===" -ForegroundColor Green
Write-Host ""

# Define locations - All use same port since only one runs at a time
$locations = @{
    "cape" = @{
        "name" = "Cape House"
        "site_id" = "cape_home"
        "zip_code" = "02632"
        "config_file" = "config/config-cape.yaml"
        "db_folder" = "data/postgres_cape"
        "container_name" = "thermostat_cape_db"
        "port" = 5433
        "token" = "FSqEZuZE3lwYq80rPF8MAxF2724cgP6f"
    }
    "fram" = @{
        "name" = "Fram House"
        "site_id" = "fram_home" 
        "zip_code" = "01701"
        "config_file" = "config/config-fram.yaml"
        "db_folder" = "data/postgres_fram"
        "container_name" = "thermostat_fram_db"
        "port" = 5433
        "token" = "rL7GcpQI8Vx69jdw9KBtCfaJhzjnsSsu"
    }
    "nh" = @{
        "name" = "Mountain Home"
        "site_id" = "nh_home"
        "zip_code" = "03000"  # Update with actual NH zip
        "config_file" = "config/config-nh.yaml"
        "db_folder" = "data/postgres_nh"
        "container_name" = "thermostat_nh_db"
        "port" = 5433
        "token" = "uO6b9ZeaIZvj5ql8FBaElkP6f6iJUL1I"
    }
}

function Show-LocationStatus {
    Write-Host "Current Multi-Location Setup:" -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($loc in $locations.Keys) {
        $location = $locations[$loc]
        Write-Host "[$($loc.ToUpper())] $($location.name)" -ForegroundColor Yellow
        
        # Check config file
        $configExists = Test-Path $location.config_file
        Write-Host "  Config: $($location.config_file) " -NoNewline
        if ($configExists) {
            Write-Host "EXISTS" -ForegroundColor Green
        } else {
            Write-Host "MISSING" -ForegroundColor Red
        }
        
        # Check database folder
        $dbExists = Test-Path $location.db_folder
        Write-Host "  Database: $($location.db_folder) " -NoNewline
        if ($dbExists) {
            $fileCount = (Get-ChildItem $location.db_folder -Recurse -File | Measure-Object).Count
            Write-Host "EXISTS ($fileCount files)" -ForegroundColor Green
        } else {
            Write-Host "MISSING" -ForegroundColor Red
        }
        
        # Check container
        $containerRunning = docker ps --format "{{.Names}}" | Where-Object { $_ -eq $location.container_name }
        Write-Host "  Container: $($location.container_name) " -NoNewline
        if ($containerRunning) {
            Write-Host "RUNNING" -ForegroundColor Green
        } else {
            $containerExists = docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $location.container_name }
            if ($containerExists) {
                Write-Host "STOPPED" -ForegroundColor Yellow
            } else {
                Write-Host "NONE" -ForegroundColor Gray
            }
        }
        
        Write-Host "  Port: $($location.port) | Token: $($location.token.Substring(0,8))..." -ForegroundColor Gray
        Write-Host ""
    }
    
    Write-Host "NOTE: All locations use the same port (5433) since only one runs at a time." -ForegroundColor Cyan
    Write-Host "This prevents port conflicts and simplifies configuration." -ForegroundColor Gray
}

function Setup-LocationFolders {
    Write-Host "Setting up database folders..." -ForegroundColor Cyan
    
    # Handle existing data
    if (Test-Path "data/postgres_cape_backup") {
        Write-Host "Moving postgres_cape_backup to postgres_cape..." -ForegroundColor Yellow
        if (Test-Path "data/postgres_cape") {
            Remove-Item "data/postgres_cape" -Recurse -Force
        }
        Move-Item "data/postgres_cape_backup" "data/postgres_cape"
        Write-Host "Cape House database restored" -ForegroundColor Green
    }
    
    # Move current postgres folder to fram if it exists and isn't empty
    if (Test-Path "data/postgres") {
        $fileCount = (Get-ChildItem "data/postgres" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        if ($fileCount -gt 0) {
            Write-Host "Moving current postgres data to postgres_fram..." -ForegroundColor Yellow
            if (Test-Path "data/postgres_fram") {
                Remove-Item "data/postgres_fram" -Recurse -Force
            }
            Move-Item "data/postgres" "data/postgres_fram"
        } else {
            Remove-Item "data/postgres" -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    
    # Create all location database folders
    foreach ($loc in $locations.Keys) {
        $dbFolder = $locations[$loc].db_folder
        if (-not (Test-Path $dbFolder)) {
            New-Item -ItemType Directory -Path $dbFolder -Force | Out-Null
            Write-Host "Created: $dbFolder" -ForegroundColor Green
        }
    }
}

function Create-LocationConfigs {
    Write-Host "Creating location-specific config files..." -ForegroundColor Cyan
    
    # Use current config.yaml as Framingham template
    if ((Test-Path "config/config.yaml") -and (-not (Test-Path "config/config-fram.yaml"))) {
        Copy-Item "config/config.yaml" "config/config-fram.yaml"
        Write-Host "Created: config/config-fram.yaml" -ForegroundColor Green
    }
    
    # Create NH config if it doesn't exist
    if (-not (Test-Path "config/config-nh.yaml")) {
        # Copy from cape config and modify
        if (Test-Path "config/config-cape.yaml") {
            $nhConfig = Get-Content "config/config-cape.yaml" -Raw
            $nhConfig = $nhConfig -replace 'site_id: "cape_home"', 'site_id: "nh_home"'
            $nhConfig = $nhConfig -replace 'site_name: "Cape House"', 'site_name: "Mountain Home"'
            $nhConfig = $nhConfig -replace 'zip_code: "02632"', 'zip_code: "03000"'
            # Keep port 5433 - no need to change it
            $nhConfig = $nhConfig -replace 'FSqEZuZE3lwYq80rPF8MAxF2724cgP6f', 'uO6b9ZeaIZvj5ql8FBaElkP6f6iJUL1I'
            
            $nhConfig | Out-File "config/config-nh.yaml" -Encoding UTF8
            Write-Host "Created: config/config-nh.yaml" -ForegroundColor Green
        }
    }
}

# Show current status if requested
if ($ShowStatus) {
    Show-LocationStatus
    exit 0
}

# Run setup
Write-Host "Setting up multi-location configuration..." -ForegroundColor Yellow
Write-Host ""

Setup-LocationFolders
Create-LocationConfigs

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""

Show-LocationStatus

Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Use the location switcher script: .\switch-location.ps1 -Location cape|fram|nh" -ForegroundColor White
Write-Host "2. Or run directly: .\run-location.ps1 -Location fram" -ForegroundColor White
Write-Host ""
Write-Host "Each location will have:" -ForegroundColor Cyan
Write-Host "  - Separate database folder (postgres_cape, postgres_fram, postgres_nh)" -ForegroundColor Gray
Write-Host "  - Separate config files" -ForegroundColor Gray
Write-Host "  - Separate Docker containers" -ForegroundColor Gray
Write-Host "  - Same database port (5433) for simplicity" -ForegroundColor Gray