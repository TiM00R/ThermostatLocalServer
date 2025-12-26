# ThermostatLocalServer - Technical Architecture

## Document Purpose

This document provides detailed technical architecture information for developers and system administrators working with the ThermostatLocalServer codebase.

---

## Table of Contents

1. [Code Organization](#code-organization)
2. [Data Flow](#data-flow)
3. [Component Details](#component-details)
4. [API Implementation](#api-implementation)
5. [Database Operations](#database-operations)
6. [Network Protocols](#network-protocols)
7. [Error Handling](#error-handling)
8. [Testing](#testing)

---

## Code Organization

### Project Structure

```
ThermostatLocalServer/
├── src/                              # Main application code
│   ├── api/                          # REST API implementation
│   │   ├── __init__.py
│   │   ├── main_api.py              # FastAPI app initialization
│   │   ├── system_routes.py         # System endpoints
│   │   └── thermostat_routes.py     # Thermostat control endpoints
│   │
│   ├── database/                     # Database layer
│   │   ├── __init__.py
│   │   ├── manager.py               # DatabaseManager class
│   │   └── models.py                # Pydantic/dataclass models
│   │
│   ├── discovery/                    # Device discovery
│   │   ├── __init__.py
│   │   ├── manager.py               # ThermostatDiscovery orchestrator
│   │   ├── models.py                # Discovery models
│   │   └── network_discovery.py     # UDP/TCP discovery
│   │
│   ├── public_sync/                  # Public server sync
│   │   ├── __init__.py
│   │   ├── command_executor.py      # Command execution
│   │   ├── sync_manager.py          # EnhancedPublicServerSync
│   │   └── upload_services.py       # Upload handling
│   │
│   ├── services/                     # Core services
│   │   ├── __init__.py
│   │   └── thermostat_server.py     # ThermostatServer orchestrator
│   │
│   ├── __init__.py
│   ├── apply_initial_config.py      # Device configuration
│   ├── asgi.py                      # ASGI entry point
│   ├── config_loader.py             # Configuration management
│   ├── discovery_command_handler.py # Remote discovery commands
│   ├── http_helper.py               # HTTP session utilities
│   ├── main.py                      # Main entry point
│   └── weather_service.py           # Weather integration
│
├── config/                           # Configuration files
│   ├── config.yaml                  # Active configuration
│   ├── config-cape.yaml             # Cape House config
│   ├── config-fram.yaml             # Fram config
│   ├── config-nh.yaml               # NH config
│   └── config.yaml.template         # Configuration template
│
├── data/                             # PostgreSQL data volumes
│   ├── postgres_cape/               # Cape database
│   ├── postgres_fram/               # Fram database
│   └── postgres_nh/                 # NH database
│
├── deployment/                       # Deployment scripts
│   ├── 00-make-executable.sh
│   ├── 01-install-docker.sh
│   ├── 02-setup-postgres.sh
│   ├── 03-restore-database.sh
│   ├── 04-install-python.sh
│   ├── 05-install-packages.sh
│   ├── 06-start-server.sh
│   └── 07-create-systemd-service.sh
│
├── docs/                             # Documentation
│   ├── RadioThermostat_CT50_API.pdf
│   ├── ssh-tunnel-guide.md
│   └── README.md                    # This document's parent
│
├── tests/                            # Test scripts (PowerShell)
│   ├── Discover-TstatsUDP.ps1
│   ├── Get-TstatsList.ps1
│   ├── Scan-Tstats.ps1
│   └── ...
│
├── certs/                            # SSL certificates
│   ├── thermo-ca.crt                # Public server CA
│   └── ...
│
├── logs/                             # Application logs
│   └── thermostat_server.log
│
├── .env                              # Environment variables (not in git)
├── .env.example                      # Environment template
├── requirements.txt                  # Python dependencies
└── README.md                         # Project overview
```

### Module Dependencies

```
┌─────────────────────────────────────────────┐
│           ThermostatServer                  │
│         (services/thermostat_server.py)     │
└─────────────────┬───────────────────────────┘
                  │
    ┌─────────────┼─────────────┬──────────────┬──────────────┐
    │             │             │              │              │
    ▼             ▼             ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│Database│  │Discovery │  │PublicSync│  │Weather   │  │HTTP API  │
│Manager │  │Manager   │  │Manager   │  │Service   │  │Server    │
└────┬───┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │           │             │              │              │
     │      ┌────┴────┐   ┌────┴────┐    ┌───┴───┐     ┌───┴────┐
     │      │Network  │   │Command  │    │OpenWx │     │Routes  │
     │      │Discovery│   │Executor │    │API    │     │        │
     │      └─────────┘   └─────────┘    └───────┘     └────────┘
     │           │             │
     │      ┌────┴────┐   ┌────┴────┐
     │      │UDP/TCP  │   │Upload   │
     │      │Protocol │   │Services │
     │      └─────────┘   └─────────┘
     │
     ▼
┌──────────────────┐
│   PostgreSQL     │
│   (asyncpg)      │
└──────────────────┘
```

---

## Data Flow

### 1. Startup Sequence

```
main.py
  └─> ThermostatServer.__init__()
       ├─> load_config()
       ├─> DatabaseManager()
       ├─> ThermostatDiscovery()
       ├─> WeatherService()
       ├─> ThermostatAPI()
       └─> EnhancedPublicServerSync()

ThermostatServer.start()
  ├─> db.initialize()
  │    └─> create_pool() → create_schema()
  │
  ├─> weather.start()
  │    └─> fetch initial temperature
  │
  ├─> public_sync.start()
  │    └─> create HTTP session with SSL
  │
  ├─> _enhanced_discovery_and_registration()
  │    ├─> Phase 1: Database + UDP (fast)
  │    │    ├─> Test known IPs from DB (3s timeout)
  │    │    ├─> UDP multicast (10s timeout)
  │    │    └─> Register found devices
  │    │
  │    └─> Phase 2: TCP (if Phase 1 = 0 devices)
  │         ├─> Batched TCP scan
  │         └─> Register as found
  │
  ├─> Start background tasks:
  │    ├─> _discovery_service() (30 min loop)
  │    ├─> _polling_service() (5 sec loop)
  │    ├─> _rollup_service() (minute boundaries)
  │    ├─> _monitoring_service() (5 min loop)
  │    ├─> _weather_service() (configurable)
  │    ├─> immediate_upload_processor()
  │    ├─> status_upload_service() (30 sec)
  │    ├─> minute_upload_service() (60 sec)
  │    ├─> _command_polling_service() (10 sec)
  │    ├─> _command_ack_service() (2 sec)
  │    └─> _stats_reporter() (5 min)
  │
  └─> _start_api_server()
       └─> uvicorn.Server.serve()
```

### 2. Polling Cycle (5 Second Loop)

```
_polling_service()
  │
  ├─> Get active thermostats from DB
  │
  ├─> Get current weather temperature
  │
  ├─> For each thermostat (concurrent):
  │    │
  │    └─> _poll_single_and_store()
  │         ├─> HTTP GET http://{ip}/tstat
  │         │
  │         ├─> Create StatusRecord with:
  │         │    ├─> temp, t_heat, tmode, tstate
  │         │    ├─> hold, override
  │         │    └─> local_temp (from weather)
  │         │
  │         ├─> _detect_state_change()
  │         │    ├─> Compare with cached previous state
  │         │    ├─> Check for changes (temp ±0.5°F, setpoint, mode, etc.)
  │         │    └─> Return: (changed, change_type, fields)
  │         │
  │         ├─> db.save_status_reading()
  │         │    ├─> Upsert current_state table
  │         │    └─> Insert raw_readings table
  │         │
  │         ├─> db.update_thermostat_last_seen()
  │         │
  │         ├─> If state_changed:
  │         │    ├─> Log change details
  │         │    ├─> Create upload_data dict
  │         │    └─> public_sync.queue_immediate_update()
  │         │
  │         └─> _update_state_cache()
  │
  └─> Sleep for remaining time to maintain 5s interval
```

### 3. Discovery Process

```
_enhanced_discovery_and_registration()
  │
  ├─> Phase 1: discover_combined_startup()
  │    │
  │    ├─> _discover_from_database()
  │    │    ├─> Get known thermostats from DB
  │    │    ├─> Test each IP with 3s timeout
  │    │    └─> Return working devices
  │    │
  │    ├─> _discover_udp_multicast()
  │    │    ├─> Send UDP broadcast to 239.255.255.250:1900
  │    │    ├─> Collect responses for 10s
  │    │    ├─> Parse WM-NOTIFY responses
  │    │    └─> Get device details via HTTP
  │    │
  │    └─> Return: (devices_found, should_continue_tcp)
  │
  ├─> If devices_found > 0:
  │    ├─> _register_and_configure_devices()
  │    │    ├─> For each device:
  │    │    │    ├─> Get existing device from DB
  │    │    │    ├─> Preserve away_temp
  │    │    │    ├─> Create ThermostatRecord
  │    │    │    ├─> db.upsert_thermostat()
  │    │    │    └─> apply_intelligent_config()
  │    │    │         ├─> Read current thermostat settings
  │    │    │         ├─> Determine configuration strategy
  │    │    │         └─> Apply settings based on hold status
  │    │    │
  │    │    └─> public_sync.register_thermostats()
  │    │
  │    └─> Start background TCP discovery (if enabled)
  │
  └─> Elif should_continue_tcp:
       └─> _blocking_tcp_discovery()
            ├─> Scan IP ranges in batches
            ├─> Register first batch immediately
            └─> Continue background scanning
```

### 4. Command Execution Flow

```
_command_polling_service() [every 10s]
  │
  ├─> HTTP GET /api/v1/sites/{site_id}/commands/pending
  │
  └─> For each command received:
       │
       └─> _execute_command()
            │
            ├─> If command == "set_state":
            │    └─> command_executor.execute_command()
            │         ├─> Get thermostat from DB
            │         ├─> HTTP POST http://{ip}/tstat with params
            │         ├─> Update device_config table
            │         └─> Return result
            │
            ├─> If command == "set_away_temp":
            │    └─> command_executor.execute_command()
            │         ├─> db.update_thermostat_away_temp()
            │         └─> Return result
            │
            ├─> If command == "discover_devices":
            │    └─> discovery_handler.execute_discovery_command()
            │         ├─> Parse command parameters
            │         ├─> Run discovery with progress callbacks
            │         ├─> _send_discovery_progress() for each phase
            │         └─> Return final result
            │
            └─> _queue_ack()
                 └─> Add to command_acks list

_command_ack_service() [every 2s]
  │
  └─> _send_command_acks()
       └─> HTTP POST /api/v1/sites/{site_id}/commands/results
            └─> Send batched acknowledgments
```

### 5. Data Upload Flow

```
Upload Services (3 types):

1. Immediate Upload (state changes)
   queue_immediate_update()
     └─> Add to upload_queue
   
   immediate_upload_processor() [continuous]
     ├─> Wait for items in queue
     ├─> Batch up to 10 items or 5s timeout
     └─> _execute_immediate_upload()
          └─> HTTP POST /status with batched data

2. Status Upload (periodic 30s)
   status_upload_service()
     ├─> Get current_status from DB
     ├─> Create status payload
     └─> HTTP POST /status

3. Minute Upload (periodic 60s)
   minute_upload_service()
     ├─> Get minute_readings since last checkpoint
     ├─> Batch into groups of 100
     ├─> For each batch:
     │    └─> HTTP POST /minute
     └─> Update checkpoint timestamp
```

---

## Component Details

### ThermostatServer

**File**: `src/services/thermostat_server.py`

Main orchestrator class that coordinates all services.

**Key Attributes**:
```python
self.config: Dict                    # Loaded configuration
self.db: DatabaseManager             # Database operations
self.discovery: ThermostatDiscovery  # Device discovery
self.weather: WeatherService         # Weather data
self.api: ThermostatAPI             # FastAPI server
self.public_sync: EnhancedPublicServerSync  # Cloud sync
self.running: bool                   # Service state
self.tasks: List[asyncio.Task]      # Background tasks
self._last_states: Dict             # State change cache
self._state_change_stats: Dict      # Statistics
```

**Key Methods**:
```python
async def start()
    # Initialize all services and start background tasks

async def stop()
    # Gracefully shutdown all services

async def _enhanced_discovery_and_registration()
    # Progressive discovery with registration

async def _register_and_configure_devices(devices, phase_name)
    # Register devices and apply configuration

async def _polling_service()
    # Main 5-second polling loop

async def _poll_single_and_store(ip, thermostat_id, local_temp)
    # Poll single thermostat and store result

def _detect_state_change(thermostat_id, current_status)
    # Compare states and detect changes

async def _rollup_service()
    # Create minute aggregations

async def _discovery_service()
    # Periodic device discovery

async def _monitoring_service()
    # Health monitoring

async def _weather_service()
    # Weather updates
```

### DatabaseManager

**File**: `src/database/manager.py`

Manages all PostgreSQL operations using asyncpg.

**Connection Pool**:
```python
self.pool: asyncpg.Pool
    min_size = 5
    max_size = 20
    command_timeout = 10
```

**Key Methods**:
```python
async def initialize()
    # Create connection pool and schema

async def create_schema()
    # Create/update database tables

async def upsert_thermostat(device: ThermostatRecord) -> bool
    # Insert or update thermostat

async def save_status_reading(status: StatusRecord) -> bool
    # Save status to current_state and raw_readings

async def get_active_thermostats() -> List[ThermostatRecord]
    # Get all active devices

async def get_current_status(thermostat_id: Optional[str]) -> List[StatusRecord]
    # Get latest status

async def create_minute_aggregation(start_time, end_time)
    # Create minute aggregation from raw data

async def cleanup_old_data(raw_retention_days, minute_retention_days)
    # Delete old data

async def update_thermostat_last_seen(thermostat_id: str) -> bool
    # Update last_seen timestamp

async def get_minute_readings_since(since_timestamp) -> List[MinuteReading]
    # Get minute data for sync

async def get_sync_checkpoint(name: str) -> Optional[datetime]
async def update_sync_checkpoint(name: str, timestamp: datetime)
    # Manage sync checkpoints
```

**Transaction Handling**:
```python
async with self.pool.acquire() as conn:
    async with conn.transaction():
        # Atomic operations
        await conn.execute(...)
```

### ThermostatDiscovery

**File**: `src/discovery/manager.py`

Orchestrates device discovery using multiple methods.

**Key Methods**:
```python
async def discover_combined_startup() -> Tuple[List[ThermostatDevice], bool]
    # Fast startup: DB + UDP
    # Returns (devices, should_continue_tcp)

async def discover_tcp_batched(callback=None) -> List[BatchResult]
    # Batched TCP scanning with optional callback

async def progressive_discovery_with_callback(callback)
    # Full progressive discovery with callbacks

async def _discover_from_database() -> List[ThermostatDevice]
    # Test known devices from DB

async def _discover_udp_multicast() -> List[ThermostatDevice]
    # UDP multicast discovery
```

**Discovery Strategy**:
1. Database-first (fastest for known devices)
2. UDP multicast (fast for responsive devices)
3. TCP scan (comprehensive but slow)

### NetworkDiscovery

**File**: `src/discovery/network_discovery.py`

Low-level network discovery protocols.

**UDP Multicast**:
```python
async def udp_multicast_discovery() -> List[ThermostatDevice]
    # Send to 239.255.255.250:1900
    # Protocol: WM-DISCOVER/WM-NOTIFY
    # Timeout: configurable (default 10s)
```

**TCP Scan**:
```python
async def tcp_scan_range(ip_list: List[str]) -> List[ThermostatDevice]
    # Concurrent HTTP probes (semaphore: 10)
    # GET /sys for device info
    # GET /sys/name for device name
    # GET /tstat/model for model
```

**IP Range Generation**:
```python
def generate_ip_range() -> List[str]
    # Supports ranges: "10.0.60.1-10.0.60.254"
    # Supports CIDR: "192.168.1.0/24"
```

### EnhancedPublicServerSync

**File**: `src/public_sync/sync_manager.py`

Manages synchronization with public server.

**HTTP Session**:
```python
self.session: aiohttp.ClientSession
    # Created with SSL configuration
    # Headers include X-Site-Token
    # Timeout: configurable (default 30s)
```

**Key Methods**:
```python
async def start()
    # Initialize session and services

async def get_sync_tasks() -> List[asyncio.Task]
    # Return all background sync tasks

async def register_thermostats(thermostats: List) -> bool
    # Register devices with public server

async def queue_immediate_update(thermostats_data: List[Dict])
    # Queue for immediate upload

async def _poll_and_execute_commands()
    # Poll for pending commands

async def _execute_command(command: Dict)
    # Execute single command

async def _send_command_acks()
    # Send batched acknowledgments

async def _handle_discovery_progress(progress: DiscoveryProgress)
    # Send discovery progress (Protocol v2.0)
```

**Upload Services** (delegated to `upload_services.py`):
```python
async def immediate_upload_processor()
    # Process immediate upload queue

async def status_upload_service()
    # Periodic status uploads (30s)

async def minute_upload_service()
    # Periodic minute uploads (60s)
```

### WeatherService

**File**: `src/weather_service.py`

Integrates with OpenWeatherMap API.

**Configuration**:
```python
self.api_key: str               # OpenWeatherMap API key
self.zip_code: str             # US zip code
self.update_interval: int      # Seconds between updates
self.current_temp: Optional[float]  # Cached temperature
self.last_update: Optional[datetime]  # Last fetch time
```

**Key Methods**:
```python
async def start()
    # Initialize and fetch initial data

async def get_current_temperature() -> Optional[float]
    # Return cached or fetch new temperature

async def update_temperature()
    # Fetch from OpenWeatherMap API
    # URL: api.openweathermap.org/data/2.5/weather
    # Params: zip={zip},US&appid={key}&units=imperial

def get_status() -> Dict
    # Return service status for monitoring
```

**Error Handling**:
- Retry up to 3 times with exponential backoff
- Falls back to configured fallback_temp
- Logs errors but continues operation
- Tracks error count for monitoring

### ThermostatAPI

**File**: `src/api/main_api.py`

FastAPI application for local REST API.

**Initialization**:
```python
app = FastAPI(
    title="Thermostat Local Server API",
    version="2.0",
    description="Local edge server for thermostat monitoring"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include routers
app.include_router(thermostat_routes)
app.include_router(system_routes)
```

**Routes**:

From `thermostat_routes.py`:
```python
GET  /api/thermostats
GET  /api/thermostats/{id}/status
POST /api/thermostats/{id}/temperature
POST /api/thermostats/{id}/mode
GET  /api/site/status
POST /api/discovery/scan
```

From `system_routes.py`:
```python
GET  /api/system/info
GET  /api/system/health
GET  /api/system/config
GET  /api/weather/status
```

---

## API Implementation

### Request/Response Models

**Pydantic Models** (`api/thermostat_routes.py`):

```python
class TemperatureRequest(BaseModel):
    t_heat: float
    hold: bool = False

class ModeRequest(BaseModel):
    tmode: int  # 0=OFF, 1=HEAT, 2=COOL, 3=AUTO

class ThermostatResponse(BaseModel):
    thermostat_id: str
    name: str
    ip_address: str
    status: str
    response: Optional[dict] = None
    error: Optional[str] = None
```

### Command Execution

**Internal Function** (`thermostat_routes.py`):
```python
async def _execute_thermostat_command(db_manager, thermostat_id: str, command: dict):
    # Get thermostat from DB
    thermostat = await db_manager.get_thermostat_by_id(thermostat_id)
    
    # Build URL
    url = f"http://{thermostat.ip_address}/tstat"
    
    # Execute HTTP POST
    async with create_thermostat_session(5) as session:
        async with session.post(url, json=command) as response:
            if response.status == 200:
                result = await response.json()
                
                # Track configuration if successful
                if result.get("success") == 0:
                    await _update_config_tracking(db_manager, thermostat_id, command)
                
                return {...}
```

**Configuration Tracking**:
```python
async def _update_config_tracking(db_manager, thermostat_id: str, command: dict):
    config_updates = {}
    now = datetime.now(timezone.utc)
    
    if "tmode" in command:
        config_updates["tmode_set"] = command["tmode"]
        config_updates["tmode_applied_at"] = now
    
    if "t_heat" in command:
        config_updates["t_heat_set"] = command["t_heat"]
        config_updates["t_heat_applied_at"] = now
    
    if "hold" in command:
        config_updates["hold_set"] = command["hold"]
        config_updates["hold_applied_at"] = now
    
    await db_manager.update_device_config(thermostat_id, config_updates)
```

---

## Database Operations

### Query Performance

**Indexes**:
```sql
CREATE INDEX idx_raw_readings_device_ts 
ON raw_readings(thermostat_id, ts DESC);

CREATE INDEX idx_minute_readings_device_ts 
ON minute_readings(thermostat_id, minute_ts DESC);

CREATE INDEX idx_current_state_ts 
ON current_state(ts DESC);
```

**Query Patterns**:

Get Active Thermostats (cached in memory):
```sql
SELECT thermostat_id, ip_address, name, model, api_version,
       fw_version, capabilities, discovery_method, active, away_temp, last_seen
FROM thermostats 
WHERE active = true;
```

Get Current Status (frequently called):
```sql
SELECT cs.*, t.name, t.model
FROM current_state cs
JOIN thermostats t ON cs.thermostat_id = t.thermostat_id
WHERE t.active = true
ORDER BY cs.thermostat_id;
```

Get Minute Readings for Sync:
```sql
SELECT thermostat_id, minute_ts, temp_avg, t_heat_last, tmode_last, 
       hvac_runtime_percent, poll_count, poll_failures, local_temp_avg
FROM minute_readings 
WHERE minute_ts > $1
ORDER BY thermostat_id, minute_ts;
```

### Transaction Management

**Atomic Status Update**:
```python
async with conn.transaction():
    # Update current_state
    await conn.execute("""
        INSERT INTO current_state (...)
        VALUES (...)
        ON CONFLICT (thermostat_id) DO UPDATE SET ...
    """)
    
    # Insert raw reading
    await conn.execute("""
        INSERT INTO raw_readings (...)
        VALUES (...)
        ON CONFLICT (thermostat_id, ts) DO NOTHING
    """)
```

**Minute Aggregation**:
```sql
INSERT INTO minute_readings (...)
SELECT 
    thermostat_id,
    date_trunc('minute', $1::TIMESTAMPTZ) as minute_ts,
    AVG(temp) as temp_avg,
    (array_agg(t_heat ORDER BY ts DESC))[1] as t_heat_last,
    (array_agg(tmode ORDER BY ts DESC))[1] as tmode_last,
    ROUND(
        (COUNT(CASE WHEN tstate > 0 THEN 1 END) * 100.0 / COUNT(*))::NUMERIC, 
        1
    ) as hvac_runtime_percent,
    COUNT(*) as poll_count,
    0 as poll_failures,
    AVG(local_temp) as local_temp_avg
FROM raw_readings
WHERE ts >= $1::TIMESTAMPTZ AND ts < $2::TIMESTAMPTZ
GROUP BY thermostat_id
ON CONFLICT (thermostat_id, minute_ts) DO NOTHING;
```

### Connection Pool Management

```python
self.pool = await asyncpg.create_pool(
    host=self.db_host,
    port=self.db_port,
    database=self.db_name,
    user=self.db_user,
    password=self.db_password,
    min_size=5,           # Always maintain 5 connections
    max_size=20,          # Maximum 20 concurrent connections
    command_timeout=10    # 10 second query timeout
)
```

**Usage Pattern**:
```python
async with self.pool.acquire() as conn:
    # Connection is acquired from pool
    result = await conn.fetch(...)
    # Connection automatically returned to pool
```

---

## Network Protocols

### RadioThermostat HTTP API

**Base Operations**:

Get System Information:
```http
GET http://{ip}/sys HTTP/1.1

Response:
{
    "uuid": "...",
    "api_version": 1,
    "fw_version": "1.2.3"
}
```

Get Device Name:
```http
GET http://{ip}/sys/name HTTP/1.1

Response:
{
    "name": "Living Room"
}
```

Get Model:
```http
GET http://{ip}/tstat/model HTTP/1.1

Response:
{
    "model": "CT50"
}
```

Get Status:
```http
GET http://{ip}/tstat HTTP/1.1

Response:
{
    "temp": 68.5,
    "t_heat": 70.0,
    "tmode": 1,
    "tstate": 0,
    "hold": 0,
    "override": 0,
    "time": {
        "day": 3,
        "hour": 14,
        "minute": 30
    }
}
```

Set State:
```http
POST http://{ip}/tstat HTTP/1.1
Content-Type: application/json

{
    "tmode": 1,
    "t_heat": 72.0,
    "hold": 1
}

Response:
{
    "success": 0
}
```

**Mode Values**:
- 0: OFF
- 1: HEAT
- 2: COOL
- 3: AUTO

**State Values** (tstate):
- 0: OFF
- 1: HEATING
- 2: COOLING

### UDP Multicast Protocol

**Discovery Request**:
```
TYPE: WM-DISCOVER
VERSION: 1.0
SERVICES: com.rtcoa.tstat:1.0
```

Sent to: `239.255.255.250:1900` (UDP multicast)

**Discovery Response**:
```
TYPE: WM-NOTIFY
VERSION: 1.0
SERVICES: com.rtcoa.tstat:1.0
UUID: {device-uuid}
LOCATION: http://{ip}:80/
```

**Implementation**:
```python
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('', 0))
sock.settimeout(2.0)

discover_msg = (
    "TYPE: WM-DISCOVER\n"
    "VERSION: 1.0\n"
    "SERVICES: com.rtcoa.tstat:1.0"
)

sock.sendto(discover_msg.encode('utf-8'), ('239.255.255.250', 1900))

# Collect responses for timeout period
while time.time() - start_time < timeout:
    data, addr = sock.recvfrom(1024)
    # Parse WM-NOTIFY response
```

### Public Server Protocol

**Authentication**:
```http
X-Site-Token: {site_token}
Content-Type: application/json
```

**SSL/TLS**:
```python
ssl_context = ssl.create_default_context(cafile=ca_cert_path)
if not ssl_verify:
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

connector = aiohttp.TCPConnector(ssl=ssl_context)
session = aiohttp.ClientSession(connector=connector, timeout=timeout)
```

**Discovery Progress (Protocol v2.0)**:
```json
{
  "command_id": "cmd-123",
  "site_id": "cape_home",
  "status": "inprogress",
  "execution_time_seconds": 15.3,
  "phase_history": [
    {
      "phase": "database",
      "status": "completed",
      "start_time": "2024-12-24T10:30:00Z",
      "elapsed_time": 2.1,
      "devices_found": 3,
      "current_action": "Testing known devices"
    },
    {
      "phase": "udp",
      "status": "inprogress",
      "start_time": "2024-12-24T10:30:02Z",
      "elapsed_time": 13.2,
      "devices_found": 2,
      "current_action": "Waiting for UDP responses"
    }
  ]
}
```

---

## Error Handling

### Database Errors

**Connection Failures**:
```python
try:
    async with self.pool.acquire() as conn:
        await conn.execute(...)
except asyncpg.PostgresError as e:
    logger.error(f"Database error: {e}")
    return False
```

**Transaction Rollback**:
```python
async with conn.transaction():
    try:
        await conn.execute(...)
        await conn.execute(...)
    except Exception:
        # Transaction automatically rolled back
        raise
```

### Network Errors

**HTTP Timeouts**:
```python
async with create_thermostat_session(timeout_seconds=5) as session:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
    except asyncio.TimeoutError:
        logger.warning(f"Timeout connecting to {url}")
        return None
    except aiohttp.ClientError as e:
        logger.warning(f"Connection error: {e}")
        return None
```

**Retry Logic**:
```python
for attempt in range(retry_attempts):
    try:
        async with session.post(url, json=data) as response:
            if response.status in [200, 201]:
                return True
            elif response.status == 429:  # Rate limited
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                await asyncio.sleep(retry_delay)
    except Exception as e:
        logger.warning(f"Attempt {attempt + 1} failed: {e}")
        if attempt < retry_attempts - 1:
            await asyncio.sleep(retry_delay)
```

### Service Recovery

**Background Task Errors**:
```python
async def _polling_service():
    while self.running:
        try:
            # Polling logic
            await asyncio.sleep(interval)
        except Exception as e:
            logger.error(f"Polling service error: {e}")
            # Continue running - error logged but service continues
            await asyncio.sleep(interval)
```

**Graceful Shutdown**:
```python
async def stop(self):
    self.running = False
    
    # Stop weather service
    await self.weather.stop()
    
    # Stop public sync
    await self.public_sync.stop()
    
    # Cancel all background tasks
    for task in self.tasks:
        task.cancel()
    
    # Wait for cancellation
    if self.tasks:
        await asyncio.gather(*self.tasks, return_exceptions=True)
    
    # Close database
    await self.db.close()
```

---

## Testing

### Test Scripts

Located in `tests/` directory (PowerShell):

**Discovery Testing**:
```powershell
# UDP broadcast discovery
.\Discover-TstatsUDP.ps1

# TCP scan
.\Scan-Tstats.ps1

# List thermostats
.\Get-TstatsList.ps1
```

**Command Testing**:
```powershell
# Set all thermostats to heat mode
.\Set-AllTstatsHeat.ps1

# Set time on all thermostats
.\Set-AllTstatTime.ps1

# View thermostat schedule
.\Show-TstatSchedule.ps1
```

**Database Testing**:
```powershell
# Comprehensive database diagnostic
.\comprehensive_db_diagnostic.ps1

# Minute readings analysis
.\minute_readings_analysis.ps1

# Gap analysis
.\gap_analysis_script.ps1
```

### Manual Testing

**Test Discovery**:
```bash
# Run discovery manually
python -c "
import asyncio
from src.discovery.manager import ThermostatDiscovery
from src.config_loader import load_config

async def test():
    config = load_config()
    discovery = ThermostatDiscovery(config['network'], None)
    devices, _ = await discovery.discover_combined_startup()
    print(f'Found {len(devices)} devices')

asyncio.run(test())
"
```

**Test Database**:
```bash
# Check database
docker exec -it postgres_cape psql -U postgres thermostat_db

# Query thermostats
SELECT * FROM thermostats WHERE active = true;

# Check current status
SELECT * FROM current_state ORDER BY ts DESC LIMIT 10;

# Check minute aggregations
SELECT * FROM minute_readings 
WHERE minute_ts > NOW() - INTERVAL '1 hour' 
ORDER BY minute_ts DESC;
```

**Test API**:
```bash
# List thermostats
curl http://localhost:8000/api/thermostats

# Get status
curl http://localhost:8000/api/thermostats/{id}/status

# Set temperature
curl -X POST http://localhost:8000/api/thermostats/{id}/temperature \
  -H "Content-Type: application/json" \
  -d '{"t_heat": 72.0, "hold": true}'

# System info
curl http://localhost:8000/api/system/info

# Health check
curl http://localhost:8000/api/system/health
```

---

## Performance Tuning

### Database Optimization

**Connection Pool Sizing**:
```python
# Formula: max_size = (num_background_tasks * 2) + buffer
# Example: (6 tasks * 2) + 8 buffer = 20 connections
min_size=5,
max_size=20
```

**Query Optimization**:
- Use indexes on frequently queried columns
- Limit result sets with LIMIT clauses
- Use pagination for large datasets
- Avoid SELECT * in production queries

**Data Cleanup**:
```python
# Run daily at 2 AM
if now.hour == 2 and now.minute == 0:
    await self.db.cleanup_old_data(
        raw_retention_days=14,
        minute_retention_days=365
    )
```

### Polling Optimization

**Concurrent Requests**:
```python
# Poll thermostats concurrently (max 5 at once)
max_concurrent_requests = 5

tasks = []
for ip in ip_list:
    task = self._poll_single_and_store(ip, ...)
    tasks.append(task)

await asyncio.gather(*tasks, return_exceptions=True)
```

**Timing Management**:
```python
cycle_start_time = time.time()

# Do work...
await self._poll_and_store(...)

# Calculate sleep time to maintain exact interval
elapsed_time = time.time() - cycle_start_time
remaining_time = poll_interval - elapsed_time

if elapsed_time > poll_interval:
    logger.warning("Work exceeded interval - skipping sleep")
    continue  # Prevent pile-up

await asyncio.sleep(remaining_time)
```

### Network Optimization

**Session Reuse**:
```python
# Create session once, reuse for all requests
self.session = create_public_server_session(...)

# Use session for all public server requests
async with self.session.post(url, json=data) as response:
    ...
```

**Batch Uploads**:
```python
# Batch minute readings (100 per request)
max_batch_size = 100
for i in range(0, len(readings), max_batch_size):
    batch = readings[i:i+max_batch_size]
    await self._upload_minute_batch(batch)
```

---

*This technical architecture document is based on source code analysis as of December 2024.*
