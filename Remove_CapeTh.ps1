<# 
.SYNOPSIS
  Delete the specified thermostats from all listed tables inside a Dockerized Postgres.
  Ensures the container is present, starts it if stopped, and waits until Postgres is ready.

.USAGE
  Save as Remove-CapeThermostats-Docker.ps1, then run:
    .\Remove-CapeTh.ps1
#>

[CmdletBinding()]
param(
  [string]$ContainerName = 'thermostat_fram_db',
  [string]$DbName        = 'thermostat_db',
  [string]$DbUser        = 'postgres',
  [string]$DbPassword    = 'postgres',
  [int]$ReadyTimeoutSec  = 90,
  [switch]$DryRun
)

# Keep these in the list as requested
$cape_thermostats = @(
  '2002af72cce9',
  '2002af72cd92',
  '2002af7368bb',
  '2002af770936'
)

$idsSql = ($cape_thermostats | ForEach-Object { "'$($_)'" }) -join ','

# SQL (children first → parent last)
$sql = @"
BEGIN;
DELETE FROM minute_readings WHERE thermostat_id IN ($idsSql);
DELETE FROM raw_readings     WHERE thermostat_id IN ($idsSql);
DELETE FROM current_state    WHERE thermostat_id IN ($idsSql);
DELETE FROM device_config    WHERE thermostat_id IN ($idsSql);
DELETE FROM thermostats      WHERE thermostat_id IN ($idsSql);
COMMIT;
"@

function Assert-ContainerExists {
  param([string]$Name)
  $list = docker ps -a --format "{{.Names}}" 2>$null | ForEach-Object { $_.Trim() }
  if (-not ($list -contains $Name)) {
    throw "Container '$Name' not found. Create it or check the name."
  }
}

function Ensure-ContainerRunning {
  param([string]$Name)
  $status = (docker inspect -f "{{.State.Status}}" $Name 2>$null).Trim()
  if ($status -ne 'running') {
    Write-Host "Container '$Name' status: $status. Starting..."
    docker start $Name | Out-Null
    # Re-check
    $status = (docker inspect -f "{{.State.Status}}" $Name 2>$null).Trim()
    if ($status -ne 'running') {
      throw "Failed to start container '$Name'. Current status: $status"
    }
    Write-Host "Container '$Name' is now running."
  } else {
    Write-Host "Container '$Name' is already running."
  }
}

function Wait-PostgresReady {
  param(
    [string]$Name,
    [string]$User,
    [string]$Password,
    [int]$TimeoutSec = 60
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  do {
    # Try pg_isready first (available in official Postgres images)
    docker exec -e PGPASSWORD=$Password $Name pg_isready -h localhost -p 5432 -U $User | Out-Null
    if ($LASTEXITCODE -eq 0) {
      Write-Host "Postgres is accepting connections."
      return
    }
    # Fallback to a lightweight SELECT if pg_isready isn't conclusive
    docker exec -e PGPASSWORD=$Password $Name psql -h localhost -p 5432 -U $User -d postgres -tAc "SELECT 1" | Out-Null
    if ($LASTEXITCODE -eq 0) {
      Write-Host "Postgres responded to a test query."
      return
    }
    Start-Sleep -Seconds 2
    Write-Host -NoNewline "."
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for Postgres in container '$Name' to become ready."
}

if ($DryRun) {
  Write-Host "DryRun: Would run this SQL inside container '$ContainerName' against $DbUser@${DbName}:`n"
  Write-Host $sql
  exit 0
}

# --- Ensure container is running and DB ready ---
Assert-ContainerExists -Name $ContainerName
Ensure-ContainerRunning -Name $ContainerName
Wait-PostgresReady -Name $ContainerName -User $DbUser -Password $DbPassword -TimeoutSec $ReadyTimeoutSec

# Write SQL to a temp file and copy it into the container
$tmpSql = Join-Path $env:TEMP ("delete_cape_{0}.sql" -f ([guid]::NewGuid()))
Set-Content -Path $tmpSql -Value $sql -Encoding UTF8

docker cp $tmpSql "$ContainerName`:/tmp/delete_cape.sql" | Out-Null

try {
  # Execute via psql inside the container (internal port 5432)
  $args = @(
    "exec","-e","PGPASSWORD=$DbPassword","-i",$ContainerName,
    "psql","-h","localhost","-p","5432","-U",$DbUser,"-d",$DbName,
    "-v","ON_ERROR_STOP=1","-q","-f","/tmp/delete_cape.sql"
  )
  docker @args
  if ($LASTEXITCODE -ne 0) { throw "psql exited with code $LASTEXITCODE." }

  Write-Host "Done. Deleted rows for thermostat_ids: $($cape_thermostats -join ', ')"
}
finally {
  docker exec $ContainerName sh -lc "rm -f /tmp/delete_cape.sql" | Out-Null
  if (Test-Path $tmpSql) { Remove-Item $tmpSql -Force }
}

