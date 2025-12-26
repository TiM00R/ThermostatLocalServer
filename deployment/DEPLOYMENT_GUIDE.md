# Ubuntu Server Deployment Guide

Complete guide for deploying ThermostatLocalServer on Ubuntu 22.04+ with step-by-step instructions, file checklist, and troubleshooting.

**Installation Directory**: `~/local-server`

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Files to Transfer](#files-to-transfer)
3. [Deployment Steps](#deployment-steps)
4. [Configuration](#configuration)
5. [Service Management](#service-management)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Ubuntu 22.04+ server with sudo access
- SSH access to the server
- At least 2GB RAM and 10GB disk space
- Internet connection for package installation

---

## Files to Transfer

### Required Files (Must Copy)

#### Application Source Code
```
src/                          # Complete source code directory
├── api/
│   ├── main_api.py
│   ├── system_routes.py
│   └── thermostat_routes.py
├── database/
├── discovery/
├── public_sync/
├── services/
├── __init__.py
├── apply_initial_config.py
├── asgi.py
├── config_loader.py
├── discovery_command_handler.py
├── http_helper.py
├── main.py
└── weather_service.py
```

#### Configuration Files
```
config/
└── config.yaml.template      # Template only - edit on server
```

**Note**: Do NOT copy actual config files (config.yaml, config-*.yaml) with passwords/tokens. Copy only the template and edit it on the server.

#### Database Data (Optional - for migration)
```
data/
├── postgres_cape/            # Cape House database files
├── postgres_fram/            # Framingham database files
└── postgres_nh/              # New Hampshire database files
```

#### Dependencies and Deployment Scripts
```
requirements.txt              # Python package dependencies
deployment/                   # Deployment scripts
├── 00-make-executable.sh
├── 01-install-docker.sh
├── 02-setup-postgres.sh
├── 03-restore-database.sh
├── 04-install-python.sh
├── 05-install-packages.sh
├── 06-start-server.sh
└── 07-create-systemd-service.sh
```

#### SSL Certificates
```
certs/
├── thermo-ca.crt             # CA certificate for public server
└── thermostat.crt            # Server certificate
```

### Optional Files

```
Dockerfile                    # For Docker deployment (future use)
.dockerignore                 # Docker build exclusions
docs/                         # Documentation (reference only)
tests/                        # Test scripts (not needed for production)
```

### Files NOT to Copy

**Do NOT copy these to Ubuntu server**:

```
*.ps1                         # PowerShell scripts (Windows only)
config/*.yaml                 # Config files with secrets (use template)
data/postgres_*/              # Database data (unless migrating)
logs/                         # Log files (created fresh on server)
backups/                      # Backup files (optional)
.venv/                        # Virtual environment (created on server)
__pycache__/                  # Python cache (recreated)
Temp/                         # Temporary files
.git/                         # Git repository (optional)
```

### Copy Command Example

Create target directory on Ubuntu server:
```bash
mkdir -p ~/local-server
cd ~/local-server
```

Copy from Windows/local machine (using SCP):
```bash
# From Windows PowerShell or WSL
scp -r src/ tstat@server:~/local-server/
scp -r deployment/ tstat@server:~/local-server/
scp -r certs/ tstat@server:~/local-server/
scp -r config/ tstat@server:~/local-server/
scp requirements.txt tstat@server:~/local-server/
scp Dockerfile tstat@server:~/local-server/
scp .dockerignore tstat@server:~/local-server/
```

Or using rsync (recommended):
```bash
rsync -avz --exclude='*.yaml' --exclude='data/' --exclude='.venv/' \
  --exclude='__pycache__/' --exclude='logs/' --exclude='*.ps1' \
  ./ tstat@server:~/local-server/
```

---

## Deployment Steps

### Step 0: Make Scripts Executable

```bash
cd ~/local-server
chmod +x deployment/*.sh
./deployment/00-make-executable.sh
```

This ensures all deployment scripts have execute permissions.

---

### Step 1: Install Docker

```bash
./deployment/01-install-docker.sh
```

**What it does**:
- Installs Docker Engine
- Adds current user to docker group
- Enables Docker service

**Important**: After Docker installation, **log out and log back in** to use docker without sudo.

**Verify installation**:
```bash
docker --version
docker ps
```

---

### Step 2: Setup PostgreSQL Container

```bash
./deployment/02-setup-postgres.sh
```

**What it does**:
- Creates PostgreSQL 15 container named `thermostat_postgres`
- Creates database `thermostat_db`
- Sets up user `postgres` with password `postgres`
- Exposes PostgreSQL on port **5433** (not 5432)
- Creates data directory at `./data/postgres_data`
- Sets container to auto-restart

**Verify installation**:
```bash
docker ps | grep thermostat_postgres
docker exec thermostat_postgres pg_isready -U postgres -d thermostat_db
```

---

### Step 3: Restore Database (Optional - For Migration)

**Only needed if migrating existing database from another server.**

```bash
./deployment/03-restore-database.sh
```

**What it does**:
- Stops PostgreSQL container temporarily
- Lists available database backups from `data/` directory
- Copies selected database data to container
- Sets correct ownership and permissions
- Restarts container with restored data

**Interactive prompts**:
- Select which location database to restore (Cape, Fram, or NH)
- Confirm before proceeding

**Skip this step** if setting up fresh installation.

---

### Step 4: Install Python 3.10+

```bash
./deployment/04-install-python.sh
```

**What it does**:
- Adds deadsnakes PPA repository (for latest Python)
- Installs Python 3.10+ and development headers
- Installs pip and venv
- Creates python3 symlink for convenience

**Verify installation**:
```bash
python3 --version    # Should be 3.10 or higher
pip3 --version
```

---

### Step 5: Install Python Packages

```bash
./deployment/05-install-packages.sh
```

**What it does**:
- Creates Python virtual environment in `./venv`
- Installs all packages from `requirements.txt`
- Verifies installation of critical packages:
  - FastAPI
  - uvicorn
  - asyncpg
  - aiohttp
  - PyYAML

**Verify installation**:
```bash
source venv/bin/activate
pip list | grep -E "fastapi|uvicorn|asyncpg"
```

---

### Step 6: Configure Application

**Edit configuration file**:
```bash
cd ~/local-server
cp config/config.yaml.template config/config.yaml
nano config/config.yaml
```

**Required configuration changes**:

1. **Site Information**:
   ```yaml
   site:
     site_id: "your_site_id"        # e.g., "cape_home"
     site_name: "Your Site Name"    # e.g., "Cape House"
     timezone: "America/New_York"
     zip_code: "02632"              # For weather service
   ```

2. **Database** (verify these match):
   ```yaml
   database:
     host: "localhost"
     port: 5433                      # NOT 5432!
     database: "thermostat_db"
     username: "postgres"
     password: "postgres"
   ```

3. **Network Discovery**:
   ```yaml
   network:
     ip_ranges:
       - "10.0.60.1-10.0.60.254"    # Your thermostat IP range
   ```

4. **Public Server Sync**:
   ```yaml
   public_server:
     enabled: true
     base_url: "https://your-public-server.com:8001"
     site_token: "your_actual_site_token_here"  # Get from public server
     ssl_enabled: true
     ssl_verify: true
     ca_cert_path: "certs/thermo-ca.crt"
   ```

5. **Weather Service** (optional):
   ```yaml
   weather:
     enabled: true
     api_key: "your_openweathermap_api_key"    # From openweathermap.org
   ```

6. **Local API**:
   ```yaml
   api:
     host: "0.0.0.0"
     port: 8000                      # Or 8001, 8002 for other locations
   ```

**Save and exit**: `Ctrl+X`, then `Y`, then `Enter`

---

### Step 7: Test Run Server

```bash
./deployment/06-start-server.sh
```

**What it does**:
- Activates virtual environment
- Checks PostgreSQL container is running
- Starts thermostat server
- Shows real-time logs

**Expected output**:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Test from another terminal**:
```bash
curl http://localhost:8000/api/system/health | jq .
```

**Stop server**: Press `Ctrl+C`

---

### Step 8: Install Systemd Service (Production)

**For production deployment with auto-start on boot:**

```bash
./deployment/07-create-systemd-service.sh
```

**What it does**:
- Creates systemd service file at `/etc/systemd/system/thermostat.service`
- Configures service to:
  - Auto-start on boot
  - Auto-restart on failure
  - Run as user tstat
  - Use correct paths and virtual environment
- Enables and starts the service

**Service management commands**:
```bash
# Check status
sudo systemctl status thermostat

# Start service
sudo systemctl start thermostat

# Stop service
sudo systemctl stop thermostat

# Restart service
sudo systemctl restart thermostat

# View logs
sudo journalctl -u thermostat -f

# Disable auto-start
sudo systemctl disable thermostat

# Enable auto-start
sudo systemctl enable thermostat
```

---

## Configuration

### Port Configuration by Location

Each location uses different ports to avoid conflicts when testing:

| Location | PostgreSQL Port | API Port | Site ID |
|----------|----------------|----------|---------|
| Cape House | 5433 | 8000 | cape_home |
| Framingham | 5434 | 8001 | fram_home |
| New Hampshire | 5435 | 8002 | nh_home |

**Production servers** typically run one location each, so you can use the default ports.

### Network Configuration

**Firewall rules** (if needed):
```bash
# Allow API port
sudo ufw allow 8000/tcp

# Allow PostgreSQL (only if remote access needed)
sudo ufw allow 5433/tcp

# Check firewall status
sudo ufw status
```

### SSL Certificates

Place certificates in `certs/` directory:
- `thermo-ca.crt` - CA certificate for public server verification
- `thermostat.crt` - Server certificate (if needed)

Certificate paths are configured in `config.yaml`:
```yaml
public_server:
  ca_cert_path: "certs/thermo-ca.crt"
```

---

## Service Management

### Using Systemd (Production)

After running script #7, manage with systemd:

```bash
# Check service status
sudo systemctl status thermostat

# View real-time logs
sudo journalctl -u thermostat -f

# View recent logs
sudo journalctl -u thermostat -n 100

# Restart after config changes
sudo systemctl restart thermostat

# Stop service
sudo systemctl stop thermostat

# Start service
sudo systemctl start thermostat
```

### Manual Operation (Development/Testing)

Start server manually:
```bash
cd ~/local-server
source venv/bin/activate
python -m src.main
```

Stop server: `Ctrl+C`

### PostgreSQL Container Management

```bash
# Check container status
docker ps | grep thermostat_postgres

# View PostgreSQL logs
docker logs thermostat_postgres

# Follow PostgreSQL logs
docker logs -f thermostat_postgres

# Restart PostgreSQL
docker restart thermostat_postgres

# Stop PostgreSQL
docker stop thermostat_postgres

# Start PostgreSQL
docker start thermostat_postgres

# Access PostgreSQL shell
docker exec -it thermostat_postgres psql -U postgres -d thermostat_db
```

### Application Logs

**Log locations**:
- Application logs: `~/local-server/logs/thermostat_server.log`
- Systemd logs: `sudo journalctl -u thermostat`

**View application logs**:
```bash
# Real-time
tail -f ~/local-server/logs/thermostat_server.log

# Last 100 lines
tail -n 100 ~/local-server/logs/thermostat_server.log

# Search for errors
grep ERROR ~/local-server/logs/thermostat_server.log
```

---

## Troubleshooting

### PostgreSQL Connection Issues

**Symptom**: Application can't connect to database

**Check container is running**:
```bash
docker ps | grep thermostat_postgres
```

**Check database is accessible**:
```bash
docker exec thermostat_postgres pg_isready -U postgres -d thermostat_db
```

**Check PostgreSQL logs**:
```bash
docker logs thermostat_postgres | tail -50
```

**Verify port mapping**:
```bash
docker port thermostat_postgres
# Should show: 5432/tcp -> 0.0.0.0:5433
```

**Test connection**:
```bash
docker exec -it thermostat_postgres psql -U postgres -d thermostat_db -c "SELECT 1;"
```

**Common fixes**:
```bash
# Restart PostgreSQL container
docker restart thermostat_postgres

# Check config.yaml has correct port (5433)
grep "port:" config/config.yaml

# Recreate container if needed
docker stop thermostat_postgres
docker rm thermostat_postgres
./deployment/02-setup-postgres.sh
```

---

### Python/Package Issues

**Symptom**: Import errors or missing packages

**Verify virtual environment**:
```bash
source venv/bin/activate
which python
# Should show: /home/tstat/local-server/venv/bin/python
```

**Check Python version**:
```bash
python --version
# Should be 3.10 or higher
```

**Reinstall packages**:
```bash
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Verify critical packages**:
```bash
pip list | grep -E "fastapi|uvicorn|asyncpg|aiohttp|pyyaml"
```

**Common fixes**:
```bash
# Recreate virtual environment
rm -rf venv/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### Application Startup Issues

**Symptom**: Server won't start or crashes immediately

**Check configuration file**:
```bash
# Verify config file exists
ls -lh config/config.yaml

# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

**Check logs**:
```bash
# Application logs
tail -50 logs/thermostat_server.log

# If using systemd
sudo journalctl -u thermostat -n 50
```

**Test configuration loading**:
```bash
source venv/bin/activate
python -c "from config_loader import load_config; print(load_config('config/config.yaml'))"
```

**Check port availability**:
```bash
# Check if port 8000 is already in use
sudo netstat -tulpn | grep 8000

# Or use ss
sudo ss -tulpn | grep 8000
```

**Common fixes**:
```bash
# Kill process using port
sudo fuser -k 8000/tcp

# Verify config has all required fields
diff config/config.yaml.template config/config.yaml

# Check file permissions
chmod 644 config/config.yaml
```

---

### Network Discovery Issues

**Symptom**: Thermostats not discovered

**Check IP ranges in config**:
```yaml
network:
  ip_ranges:
    - "10.0.60.1-10.0.60.254"  # Must match your network
```

**Test network connectivity**:
```bash
# Ping a known thermostat
ping 10.0.60.1

# Check if you can access thermostat API
curl http://10.0.60.1/tstat
```

**Verify discovery settings**:
```bash
grep -A 10 "network:" config/config.yaml
```

**Manual discovery trigger**:
```bash
curl -X POST http://localhost:8000/api/discovery/scan
```

---

### Public Server Sync Issues

**Symptom**: Not syncing with public server

**Check sync status**:
```bash
curl http://localhost:8000/api/system/sync/status | jq .
```

**Verify public server settings**:
```yaml
public_server:
  enabled: true
  base_url: "https://your-server.com:8001"
  site_token: "valid_token_here"
  ssl_enabled: true
```

**Test public server connectivity**:
```bash
curl -k https://your-server.com:8001/api/v1/health
```

**Check SSL certificate**:
```bash
ls -lh certs/thermo-ca.crt
```

**View sync logs**:
```bash
grep "sync" logs/thermostat_server.log | tail -20
```

---

### Systemd Service Issues

**Symptom**: Service won't start or keeps restarting

**Check service status**:
```bash
sudo systemctl status thermostat
```

**View detailed logs**:
```bash
sudo journalctl -u thermostat -n 100 --no-pager
```

**Verify service file**:
```bash
cat /etc/systemd/system/thermostat.service
```

**Reload systemd after changes**:
```bash
sudo systemctl daemon-reload
sudo systemctl restart thermostat
```

**Check file permissions**:
```bash
# Service should run as your user
whoami
# Check ownership of files
ls -la ~/local-server/
```

---

## Directory Structure After Deployment

```
/home/tstat/local-server/
├── src/                      # Application source code
│   ├── api/
│   ├── database/
│   ├── discovery/
│   ├── public_sync/
│   ├── services/
│   └── main.py
├── config/
│   ├── config.yaml           # Active configuration (with secrets)
│   └── config.yaml.template  # Template (safe to commit)
├── certs/
│   ├── thermo-ca.crt
│   └── thermostat.crt
├── data/
│   └── postgres_data/        # PostgreSQL database files
├── logs/
│   └── thermostat_server.log # Application logs
├── venv/                     # Python virtual environment
├── deployment/               # Deployment scripts
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker configuration (future use)
└── .dockerignore            # Docker build exclusions
```

---

## Quick Reference Commands

### Service Control
```bash
sudo systemctl status thermostat      # Check status
sudo systemctl start thermostat       # Start service
sudo systemctl stop thermostat        # Stop service
sudo systemctl restart thermostat     # Restart service
sudo journalctl -u thermostat -f      # Follow logs
```

### API Testing
```bash
curl http://localhost:8000/api/system/health | jq .
curl http://localhost:8000/api/thermostats | jq .
curl http://localhost:8000/api/site/status | jq .
curl http://localhost:8000/api/weather/status | jq .
```

### PostgreSQL
```bash
docker ps | grep thermostat_postgres          # Check status
docker logs thermostat_postgres               # View logs
docker restart thermostat_postgres            # Restart
docker exec -it thermostat_postgres \
  psql -U postgres -d thermostat_db           # Access shell
```

### Logs
```bash
tail -f logs/thermostat_server.log            # Application logs
sudo journalctl -u thermostat -f              # Systemd logs
docker logs -f thermostat_postgres            # PostgreSQL logs
```

---

## Support and Documentation

For detailed information, see:
- **API Reference**: `docs/API_REFERENCE.md`
- **Architecture**: `docs/ARCHITECTURE.md`
- **Quick Reference**: `docs/QUICK_REFERENCE.md`
- **Main Documentation**: `docs/README.md`

---

*Ubuntu Server Deployment Guide - Updated December 2024*
