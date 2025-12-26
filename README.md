# ThermostatLocalServer - Complete Documentation

## Table of Contents
1. [Overview](#overview)
2. [What This System Does](#what-this-system-does)
3. [System Architecture](#system-architecture)
4. [Key Features](#key-features)
5. [Components](#components)
6. [Installation & Deployment](#installation--deployment)
7. [Configuration](#configuration)
8. [API Reference](#api-reference)
9. [Database Schema](#database-schema)
10. [Operational Details](#operational-details)

---

## Overview

**ThermostatLocalServer** is a local edge server designed to monitor, control, and synchronize RadioThermostat WiFi thermostats (CT50, CT80, 3M50 models) at individual physical sites (homes, buildings). It acts as a bridge between local thermostat devices and a central public server, providing real-time monitoring, historical data aggregation, and remote command execution capabilities.

### Purpose
- Run at each physical location with thermostats (Cape House, Fram, New Hampshire, etc.)
- Discover and register thermostats on the local network
- Continuously monitor thermostat status (every 5 seconds)
- Aggregate data into minute-level statistics
- Synchronize data to a central public server via **HTTPS REST API**
- Execute remote commands from the public server
- Provide local API for direct thermostat control

### Communication Architecture
- **Local → Public Server**: HTTPS REST API with polling (every 10s for commands)
- **Web UI → Public Server**: WebSocket (WSS) for real-time updates
- **Reason for HTTPS polling**: Better reliability through firewalls/NAT, simpler implementation, acceptable latency for human-initiated commands

### Target Devices
- RadioThermostat CT50 (primary)
- RadioThermostat CT80
- 3M50 thermostats

All devices must support the RadioThermostat WiFi API v1.3.

---

## What This System Does

### Core Functions

1. **Network Discovery**
   - Discovers thermostats on local network using UDP multicast
   - Performs TCP scans across configured IP ranges
   - Implements progressive discovery for fast startup
   - Re-discovers devices periodically (every 30 minutes by default)

2. **Real-Time Monitoring**
   - Polls thermostat status every 5 seconds
   - Captures: temperature, setpoint, mode, HVAC state, hold status
   - Detects state changes (manual adjustments) within seconds
   - Integrates local weather data for indoor/outdoor comparison

3. **Data Aggregation**
   - Creates minute-level aggregations from raw 5-second readings
   - Calculates HVAC runtime percentage per minute
   - Stores 14 days of raw readings, 365 days of minute aggregations

4. **Public Server Synchronization (HTTPS)**
   - Registers discovered thermostats with central server
   - Uploads current status every 30 seconds
   - Uploads minute aggregations every 60 seconds
   - Implements immediate upload on state changes
   - Supports SSL/TLS encrypted communication
   - **Uses HTTPS polling** (not WebSocket) for reliable operation through firewalls

5. **Remote Command Execution**
   - Polls public server for pending commands every 10 seconds
   - Executes `set_state` commands (temperature, mode, hold)
   - Executes `set_away_temp` commands
   - Executes `discover_devices` commands with progress tracking
   - Sends command acknowledgments with detailed results

6. **Local API**
   - RESTful API for direct thermostat control
   - Query current status and historical data
   - Execute commands locally
   - Health monitoring endpoints

---

## System Architecture

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    ThermostatLocalServer                 │
│                  (Python FastAPI Application)            │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Discovery  │  │    Polling   │  │  Public Sync │    │
│  │   Service    │  │    Service   │  │   Manager    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Weather    │  │   Database   │  │  HTTP API    │    │
│  │   Service    │  │   Manager    │  │   Server     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                          │
└───────────────────────┬──────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   ┌─────────┐    ┌─────────┐    ┌──────────────┐
   │ CT50 #1 │    │ CT50 #2 │    │ PostgreSQL   │
   │10.0.60.1│    │10.0.60.2│    │ Database     │
   └─────────┘    └─────────┘    │ (Docker)     │
                                 └──────────────┘
                      │
                      ▼ (HTTPS polling)
                ┌──────────────┐
                │Public Server │
                │ (HTTPS/SSL)  │
                └──────┬───────┘
                       │
                       ▼ (WebSocket)
                ┌──────────────┐
                │  Web UI      │
                │  (Browser)   │
                └──────────────┘
```

### Component Interaction Flow

```
1. Startup Sequence
   ├─ Load configuration (YAML - all settings in config file)
   ├─ Initialize database connection pool
   ├─ Start weather service
   ├─ Run progressive discovery
   │  ├─ Test known devices from database (3s timeout)
   │  ├─ UDP multicast discovery (10s)
   │  └─ Optional: TCP scan (background or blocking)
   ├─ Register devices with public server (HTTPS POST)
   ├─ Apply initial device configuration
   └─ Start background services

2. Continuous Operation
   ├─ Polling Service (5s interval)
   │  ├─ Query all active thermostats
   │  ├─ Store raw readings
   │  ├─ Detect state changes
   │  └─ Queue immediate uploads on changes
   │
   ├─ Rollup Service (1 minute boundaries)
   │  └─ Create minute aggregations
   │
   ├─ Discovery Service (30 min interval)
   │  └─ Re-discover devices
   │
   ├─ Weather Service (configurable)
   │  └─ Update local temperature
   │
   ├─ Upload Services (HTTPS)
   │  ├─ Status upload (30s interval) → HTTPS POST
   │  ├─ Minute upload (60s interval) → HTTPS POST
   │  └─ Immediate upload processor (state changes) → HTTPS POST
   │
   └─ Command Polling (10s interval)
      ├─ Poll for pending commands → HTTPS GET
      ├─ Execute commands
      └─ Send acknowledgments → HTTPS POST
```

---

## Configuration

### Configuration File Structure

**All configuration is stored in `config/config.yaml`** - there are no environment variables or `.env` files used.

Located at `config/config.yaml`:

```yaml
# Site Information
site:
  site_id: "your_site_id"           # Unique identifier
  site_name: "Your Site Name"       # Display name
  timezone: "America/New_York"      # Timezone
  zip_code: "00000"                 # For weather service

# Network Discovery
network:
  progressive_discovery:
    enabled: true
    database_timeout_seconds: 3     # Test known devices
    udp_timeout_seconds: 10         # UDP discovery
    
    tcp_discovery:
      enable_background_tcp_discovery: false
      enable_periodic_tcp: false
      tcp_batch_register_first: true
      tcp_batch_size: 10
      tcp_batch_timeout_seconds: 5
  
  ip_ranges:
    - "10.0.60.1-10.0.60.254"       # IP ranges to scan
  
  discovery_timeout: 20
  request_timeout: 5
  scan_interval_minutes: 30         # Rediscovery interval

# Polling Configuration
polling:
  status_interval_seconds: 5        # Poll every 5 seconds
  max_concurrent_requests: 5
  retry_attempts: 3
  retry_delay_seconds: 2
  error_threshold: 10

# Database Configuration
database:
  host: "localhost"
  port: 5433                        # Different per location
  database: "thermostat_db"
  username: "postgres"
  password: "your_postgres_password"  # PLAINTEXT in YAML

# Local API Server
api:
  host: "0.0.0.0"
  port: 8000                        # Different per location
  cors_origins: ["*"]

# Public Server Sync
public_server:
  enabled: true
  base_url: "https://your-server.com:8001"
  site_token: "your_actual_site_token"  # PLAINTEXT in YAML
  
  # SSL Configuration
  ssl_enabled: true
  ssl_verify: true
  ca_cert_path: "certs/thermo-ca.crt"
  timeout_seconds: 30
  
  # Upload Intervals
  status_upload_seconds: 30
  minute_upload_seconds: 60
  command_poll_seconds: 10
  
  # Retry Configuration
  retry_attempts: 3
  retry_delay_seconds: 2
  max_batch_size: 100

# Weather Service (optional)
weather:
  enabled: true
  api_key: "your_openweathermap_api_key"  # PLAINTEXT in YAML
  update_interval_minutes: 15
  timeout_seconds: 10
  retry_attempts: 3
  fallback_temp: 32.0

# Logging
logging:
  level: "INFO"                     # DEBUG, INFO, WARNING, ERROR
  file: "logs/thermostat_server.log"
  console_output: true

# Thermostat Time Sync
thermostat_time_sync:
  sync_interval_days: 7
  sync_after_discovery: true

# Monitoring
monitoring:
  health_check_interval_minutes: 5
  device_timeout_minutes: 10
```

### Configuration Notes

⚠️ **Security Warning**: 
- All configuration values (including passwords and tokens) are stored **in plaintext** in the YAML file
- **Do not commit** `config/config.yaml` to version control if it contains sensitive data
- Consider using `config.yaml.template` as a base and add `config.yaml` to `.gitignore`

### Environment Variable Support

The **only** environment variable supported is:
```bash
CONFIG_FILE=config/config-cape.yaml python -m src.main
```

This allows you to specify which config file to use at runtime.

---


## Installation & Deployment

### Prerequisites

- **Operating System**: Ubuntu 22.04+ (tested) or Debian-based Linux
- **Python**: 3.10 or higher
- **Docker**: For PostgreSQL database
- **Network**: Access to thermostat devices and public server

### Deployment Scripts

Located in `deployment/` directory:

1. **00-make-executable.sh**: Make all scripts executable
2. **01-install-docker.sh**: Install Docker and Docker Compose
3. **02-setup-postgres.sh**: Create PostgreSQL container
4. **03-restore-database.sh**: Restore database from backup
5. **04-install-python.sh**: Install Python 3.10+
6. **05-install-packages.sh**: Install Python dependencies
7. **06-start-server.sh**: Start the server manually
8. **07-create-systemd-service.sh**: Create systemd service for auto-start

### Installation Steps

```bash
# 1. Clone repository
cd /opt
git clone <repository-url> ThermostatLocalServer
cd ThermostatLocalServer

# 2. Make scripts executable
chmod +x deployment/*.sh

# 3. Run installation scripts in order
./deployment/01-install-docker.sh
./deployment/02-setup-postgres.sh
./deployment/03-restore-database.sh  # If you have a backup
./deployment/04-install-python.sh
./deployment/05-install-packages.sh

# 4. Configure for your location (Only if you run test before on windows 
#    with multiple locations setup and want to preserve database.)
cp config/config-cape.yaml config/config.yaml
# Edit config/config.yaml with your actual values:
#   - database password
#   - public_server site_token
#   - weather api_key 
#   - IP ranges for your network

# 5. Test run
./deployment/06-start-server.sh

# 6. Install systemd service (optional)
./deployment/07-create-systemd-service.sh
```

⚠️ **Important**: Edit `config/config.yaml` to set:
- `database.password` - Your PostgreSQL password
- `public_server.site_token` - Your site authentication token
- `weather.api_key` - Your OpenWeatherMap API key (if enabled)
- `network.ip_ranges` - Your local network IP ranges


## Multi-Location Support (Development Only)

⚠️ **Note**: This feature is **only for development/testing on Windows** when running the local server on a laptop while traveling between multiple physical locations.

**Production deployment**: Each Linux server runs at a single location with one `config/config.yaml` file. Multi-location support is NOT needed.

**Development use case**: When testing on Windows while traveling between houses (House1, House2, House3), multiple configs allow quick switching without confusing the public server database.

Supports running multiple instances on the same machine with different configs:
- Different PostgreSQL containers per location
- Different ports per location
- See `setup-multi-location.ps1` and `switch-location.ps1`


### Multi-Location Setup

For running multiple instances on the same machine:

```powershell
# From Windows machine managing the server
.\setup-multi-location.ps1

# Switch between locations
.\switch-location.ps1 -Location House1
.\switch-location.ps1 -Location House2
.\switch-location.ps1 -Location House3
```

Each location uses:
- Separate PostgreSQL container (different ports)
- Separate data directory
- Separate configuration file

### Location-Specific Configurations

**Cape House** (`config-cape.yaml`):
- site_id: home1
- PostgreSQL port: 5433
- API port: 8000
- IP range: 10.0.60.x

**Fram** (`config-fram.yaml`):
- site_id: home2
- PostgreSQL port: 5434
- API port: 8001
- IP range: 10.0.70.x

**New Hampshire** (`config-nh.yaml`):
- site_id: home3
- PostgreSQL port: 5435
- API port: 8002
- IP range: 192.168.1.x
---


## Related Documentation

- **RadioThermostat API**: `docs/RadioThermostat_CT50_Honeywell_Wifi_API_V1.3.pdf`
- **SSH Tunnels**: `docs/ssh-tunnel-guide.md`
- **Deployment**: `deployment/README.md`
- **GitHub Setup**: `GITHUB_SETUP.md`
- **Quick Reference**: `docs/QUICK_REFERENCE.md`
- **Architecture Details**: `docs/ARCHITECTURE.md`
- **API Reference**: `docs/API_REFERENCE.md`

---

## Version History

- **v2.0** (Current)
  - Progressive discovery system
  - State change detection with immediate uploads
  - Discovery command progress tracking (Protocol v2.0)
  - SSL/TLS support for public server (HTTPS)
  - Weather service integration
  - Intelligent device configuration
  - Away temperature support
  - **HTTPS polling** for public server communication (not WebSocket)

- **v1.0**
  - Basic discovery and polling
  - Database storage
  - Public server sync
  - Command execution

---

## Communication Architecture Notes

### Why HTTPS Polling Instead of WebSocket?

**ThermostatLocalServer uses HTTPS polling** to communicate with the public server instead of WebSocket for several important reasons:

1. **Firewall Compatibility**: HTTPS outbound works through virtually any firewall, while WebSocket can be blocked
2. **NAT Traversal**: Local servers behind home routers reliably send HTTPS requests; persistent WebSocket connections are problematic
3. **Connection Stability**: Home internet connections are unstable; stateless HTTPS is simpler than managing WebSocket reconnections
4. **Acceptable Latency**: Commands are human-initiated; 10-second polling delay is acceptable
5. **Debugging**: HTTPS requests are easy to log and troubleshoot
6. **Simplicity**: Much simpler implementation and fewer edge cases

### WebSocket Usage

**WebSocket IS used** but only between:
- **Web UI (browser) ↔ Public Server** for real-time thermostat status updates
- This works well because browser-to-server connections are stable and WebSocket support is excellent

The architecture is:
```
ThermostatLocalServer --[HTTPS polling]--> PublicServer <--[WebSocket]--> Web UI
```

---

*This documentation is based on source code analysis as of December 2024.*
*For latest changes, refer to git commit history.*
