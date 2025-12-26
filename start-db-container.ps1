<#
.SYNOPSIS
    Location-Aware Server Runner - COMPLETE SERVER MANAGEMENT

.DESCRIPTION
    Runs thermostat server for specific location with correct database and config.
    Handles database containers, configuration, and server startup.

.USAGE
    .\run-location.ps1 -Location fram                    # Run Framingham server
    .\run-location.ps1 -Location cape                    # Run Cape House server
    .\run-location.ps1 -Location nh                      # Run New Hampshire server
    .\run-location.ps1 -Location fram -DebugMode         # Run with debug logging
    .\run-location.ps1 -Location fram -DisableSync       # Run without public sync
    .\run-location.ps1 -StatusOnly -Location fram        # Show container status
    .\run-location.ps1 -StopOnly -Location fram          # Stop all containers

.WHAT IT DOES
    - Stops all existing thermostat containers
    - Starts correct database container for location
    - Validates location-specific configuration
    - Runs thermostat server with location database

.WHEN TO USE
    - Daily operation - most commonly used script
    - Every time you want to start server for specific location
    - To check status or stop all containers
    - When traveling between locations

.LOCATIONS
    cape = Cape House    (port 5433, postgres_cape, config-cape.yaml)
    fram = Framingham    (port 5433, postgres_fram, config-fram.yaml)  
    nh   = New Hampshire (port 5433, postgres_nh,   config-nh.yaml)
    
.NOTE
    All locations use the same port (5433) since only one location runs at a time.
    This avoids port conflicts and simplifies configuration.
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("cape", "fram", "nh")]
    [string]$Location,
    
    [switch]$DisableSync,
    [switch]$DebugMode,
    [switch]$StopOnly,
    [switch]$StatusOnly
)

# Location configurations - All use same port since only one runs at a time
$locations = @{
    "cape" = @{
        "name" = "Cape House"
        "site_id" = "cape_home"
        "config_file" = "config/config-cape.yaml"
        "db_folder" = "data/postgres_cape"
        "container_name" = "thermostat_cape_db"
        "port" = 5433
    }
    "fram" = @{
        "name" = "Fram House"
        "site_id" = "fram_home"
        "config_file" = "config/config-fram.yaml"
        "db_folder" = "data/postgres_fram"
        "container_name" = "thermostat_fram_db"
        "port" = 5433
    }
    "nh" = @{
        "name" = "Mountain Home"
        "site_id" = "nh_home"
        "config_file" = "config/config-nh.yaml"
        "db_folder" = "data/postgres_nh"
        "container_name" = "thermostat_nh_db"
        "port" = 5433
    }
}

$selectedLocation = $locations[$Location]

Write-Host "=== Thermostat Server - $($selectedLocation.name) ===" -ForegroundColor Green
Write-Host ""

function Show-LocationStatus {
    Write-Host "Current Status:" -ForegroundColor Cyan
    
    foreach ($loc in $locations.Keys) {
        $location = $locations[$loc]
        $isSelected = ($loc -eq $Location)
        
        $prefix = if ($isSelected) { "[SELECTED]" } else { "          " }
        $color = if ($isSelected) { "Yellow" } else { "Gray" }
        
        Write-Host "$prefix $($location.name)" -ForegroundColor $color
        
        # Check container status
        $containerRunning = docker ps --format "{{.Names}}" | Where-Object { $_ -eq $location.container_name }
        $containerExists = docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $location.container_name }
        
        if ($containerRunning) {
            $status = "RUNNING"
            $statusColor = "Green"
        } elseif ($containerExists) {
            $status = "STOPPED"
            $statusColor = "Yellow"
        } else {
            $status = "NONE"
            $statusColor = "Gray"
        }
        
        Write-Host "          Container: $($location.container_name) - $status" -ForegroundColor $statusColor
        Write-Host "          Port: $($location.port) | Config: $($location.config_file)" -ForegroundColor Gray
        Write-Host ""
    }
}

function Stop-AllThermostatContainers {
    Write-Host "Cleaning up all thermostat containers..." -ForegroundColor Yellow
    
    foreach ($loc in $locations.Keys) {
        $containerName = $locations[$loc].container_name
        
        # Check if container exists (running or stopped)
        $containerExists = docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $containerName }
        
        if ($containerExists) {
            Write-Host "  Removing $containerName..." -ForegroundColor Gray
            docker rm -f $containerName | Out-Null
        }
    }
    
    Write-Host "All containers cleaned up" -ForegroundColor Green
}

function Start-LocationDatabase {
    param([hashtable]$locationConfig)
    
    Write-Host "Starting database for $($locationConfig.name)..." -ForegroundColor Cyan
    
    # Ensure database folder exists
    if (-not (Test-Path $locationConfig.db_folder)) {
        New-Item -ItemType Directory -Path $locationConfig.db_folder -Force | Out-Null
        Write-Host "Created database folder: $($locationConfig.db_folder)" -ForegroundColor Green
    }
    
    # Start PostgreSQL container
    $dockerCmd = @(
        "run", "-d"
        "--name", $locationConfig.container_name
        "-e", "POSTGRES_DB=thermostat_db"
        "-e", "POSTGRES_USER=postgres"
        "-e", "POSTGRES_PASSWORD=postgres"
        "-v", "$($PWD.Path)/$($locationConfig.db_folder):/var/lib/postgresql/data"
        "-p", "$($locationConfig.port):5432"
        "postgres:15"
    )
    
    try {
        $result = & docker @dockerCmd 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Database container started successfully" -ForegroundColor Green
            Write-Host "  Container: $($locationConfig.container_name)" -ForegroundColor Gray
            Write-Host "  Port: $($locationConfig.port)" -ForegroundColor Gray
            Write-Host "  Data: $($locationConfig.db_folder)" -ForegroundColor Gray
        } else {
            Write-Host "ERROR: Failed to start database container" -ForegroundColor Red
            Write-Host $result -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "ERROR: Failed to start database container: $($_)" -ForegroundColor Red
        return $false
    }
    
    # Wait for database to be ready
    Write-Host "Waiting for database to be ready..." -ForegroundColor Yellow
    $maxWait = 30
    $waited = 0
    
    do {
        Start-Sleep -Seconds 2
        $waited += 2
        
        $dbReady = docker exec $locationConfig.container_name pg_isready -U postgres -d thermostat_db 2>$null
        if ($dbReady -like "*accepting connections*") {
            Write-Host "Database is ready" -ForegroundColor Green
            return $true
        }
        
        Write-Host "  Waiting... ($waited/$maxWait seconds)" -ForegroundColor Gray
    } while ($waited -lt $maxWait)
    
    Write-Host "WARNING: Database may not be fully ready yet" -ForegroundColor Yellow
    return $true
}

function Test-Configuration {
    param([string]$configFile)
    
    Write-Host "Validating configuration: $configFile" -ForegroundColor Cyan
    
    if (-not (Test-Path $configFile)) {
        Write-Host "ERROR: Configuration file not found: $configFile" -ForegroundColor Red
        return $false
    }
    
    # Test config loading
    $configTest = @"
try:
    from src.config_loader import load_config
    config = load_config('$configFile')
    print(f"Site: {config['site']['site_name']} ({config['site']['site_id']})")
    print(f"Database port: {config['database']['port']}")
    print("Configuration: OK")
except Exception as e:
    print(f"Configuration error: {e}")
    import sys
    sys.exit(1)
"@
    
    try {
        $result = & .venv\Scripts\python.exe -c $configTest
        Write-Host $result -ForegroundColor Green
        return $true
    } catch {
        Write-Host "Configuration validation failed" -ForegroundColor Red
        return $false
    }
}






# Main execution
if ($StatusOnly) {
    Show-LocationStatus
    exit 0
}

# Stop all containers first
Stop-AllThermostatContainers

if ($StopOnly) {
    Write-Host "All thermostat servers stopped" -ForegroundColor Green
    exit 0
}

Write-Host "Selected location: $($selectedLocation.name)" -ForegroundColor Yellow
Write-Host ""

# Validate configuration
if (-not (Test-Configuration $selectedLocation.config_file)) {
    exit 1
}

# Start database
if (-not (Start-LocationDatabase $selectedLocation)) {
    exit 1
}

Write-Host ""

