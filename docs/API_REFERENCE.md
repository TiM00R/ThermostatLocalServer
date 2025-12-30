# ThermostatLocalServer - Complete API Reference

**Version**: 2.1.0  
**Base URL**: `http://localhost:8000` (default port, configurable per location)  
**Format**: All requests and responses use JSON  
**Authentication**: None (assumes trusted local network)

---

## Table of Contents

1. [Local REST API](#local-rest-api)
   - [Thermostat Endpoints](#thermostat-endpoints)
   - [System Health Endpoints](#system-health-endpoints)
   - [Weather Endpoints](#weather-endpoints)
   - [Sync Monitoring Endpoints](#sync-monitoring-endpoints)
   - [Discovery Endpoints](#discovery-endpoints)
2. [Public Server API (Outbound)](#public-server-api-outbound)
   - [Overview](#overview)
   - [Authentication](#authentication)
   - [Register Thermostats](#register-thermostats)
   - [Upload Status Data](#upload-status-data)
   - [Upload Minute History](#upload-minute-history)
   - [Poll Commands](#poll-commands)
   - [Submit Command Results](#submit-command-results)
   - [Submit Discovery Progress](#submit-discovery-progress)
   - [Error Handling](#public-error-handling)
   - [Testing Public Server API](#testing)
   - [Communication Flow](#communication-flow-diagram)
3. [RadioThermostat Device API](#radiothermostat-device-api)
4. [Response Codes](#response-codes)
5. [Error Handling](#error-handling)

---

## Local REST API

All endpoints have been **verified against actual implementation** (no hallucinated endpoints).

### Thermostat Endpoints

#### List All Thermostats

```http
GET /api/thermostats
```

**Description**: Returns all discovered thermostats.

**Test Command**:
```bash
curl http://localhost:8000/api/thermostats | jq .
```

**Response**: 200 OK
```json
[
  {
    "thermostat_id": "5CDAD4123456",
    "name": "Living Room",
    "ip_address": "10.0.60.1",
    "model": "CT50",
    "api_version": 1,
    "active": true,
    "last_seen": "2024-12-25T10:30:00.000Z"
  }
]
```

**Fields**:
- `thermostat_id`: Unique device identifier (UUID from device)
- `name`: Human-readable name
- `ip_address`: Current IP address on local network
- `model`: Device model (CT50, CT80, 3M50)
- `api_version`: RadioThermostat API version
- `active`: Whether device is currently active
- `last_seen`: Last successful communication timestamp (UTC)

---

#### Get Thermostat Status

```http
GET /api/thermostats/{thermostat_id}/status
```

**Description**: Returns current status for a specific thermostat.

**Parameters**:
- `thermostat_id` (path): Thermostat ID

**Test Command**:
```bash
# Get thermostat ID first
TSTAT_ID=$(curl -s http://localhost:8000/api/thermostats | jq -r '.[0].thermostat_id')

# Get status
curl http://localhost:8000/api/thermostats/$TSTAT_ID/status | jq .
```

**Response**: 200 OK
```json
{
  "thermostat_id": "5CDAD4123456",
  "ts": "2024-12-25T10:30:00.000Z",
  "temp": 68.5,
  "t_heat": 70.0,
  "tmode": 1,
  "tstate": 0,
  "hold": 0,
  "override": 0,
  "ip_address": "10.0.60.1",
  "local_temp": 32.5,
  "last_error": null
}
```

**Fields**:
- `thermostat_id`: Device identifier
- `ts`: Timestamp of reading (UTC)
- `temp`: Current temperature (°F)
- `t_heat`: Heat setpoint (°F)
- `tmode`: Operating mode (0=OFF, 1=HEAT, 2=COOL, 3=AUTO)
- `tstate`: Current HVAC state (0=OFF, 1=HEATING, 2=COOLING)
- `hold`: Hold status (0=off, 1=on)
- `override`: Override status (0=off, 1=on)
- `ip_address`: Device IP
- `local_temp`: Outside temperature (°F, if weather service enabled)
- `last_error`: Last error message (null if none)

**Error Response**: 404 Not Found
```json
{
  "detail": "Thermostat not found"
}
```

---

#### Get Site Status

```http
GET /api/site/status
```

**Description**: Returns current status for all active thermostats.

**Test Command**:
```bash
curl http://localhost:8000/api/site/status | jq .
```

**Response**: 200 OK
```json
[
  {
    "thermostat_id": "5CDAD4123456",
    "ts": "2024-12-25T10:30:00.000Z",
    "temp": 68.5,
    "t_heat": 70.0,
    "tmode": 1,
    "tstate": 0,
    "hold": 0,
    "override": 0,
    "ip_address": "10.0.60.1",
    "local_temp": 32.5,
    "last_error": null
  }
]
```

---

#### Set Thermostat Temperature

```http
POST /api/thermostats/{thermostat_id}/temperature
Content-Type: application/json
```

**Description**: Sets the heating setpoint for a thermostat. Automatically sets mode to HEAT (tmode=1).

**Parameters**:
- `thermostat_id` (path): Thermostat ID

**Request Body**:
```json
{
  "t_heat": 72.0,
  "hold": true
}
```

**Fields**:
- `t_heat` (required): Heating setpoint in °F (float)
- `hold` (optional): Enable permanent hold (boolean, default: false)

**Test Command**:
```bash
# Get thermostat ID
TSTAT_ID=$(curl -s http://localhost:8000/api/thermostats | jq -r '.[0].thermostat_id')

# Set temperature to 72°F with hold
curl -X POST http://localhost:8000/api/thermostats/$TSTAT_ID/temperature \
  -H "Content-Type: application/json" \
  -d '{"t_heat": 72.0, "hold": true}' | jq .
```

**Response**: 200 OK
```json
{
  "thermostat_id": "5CDAD4123456",
  "name": "Living Room",
  "ip_address": "10.0.60.1",
  "status": "success",
  "response": {
    "success": 0
  }
}
```

**Response Fields**:
- `status`: "success" or "failed"
- `response`: Raw response from thermostat
  - `success: 0` indicates command accepted (this is success, not error!)
  - Other values indicate error

**Side Effects**:
- Sets thermostat to HEAT mode (tmode=1)
- Updates device_config table with applied settings
- State change will trigger immediate upload to public server

---

#### Set Thermostat Mode

```http
POST /api/thermostats/{thermostat_id}/mode
Content-Type: application/json
```

**Description**: Sets the operating mode for a thermostat.

**Parameters**:
- `thermostat_id` (path): Thermostat ID

**Request Body**:
```json
{
  "tmode": 1
}
```

**Fields**:
- `tmode` (required): Mode value (integer)
  - `0`: OFF
  - `1`: HEAT
  - `2`: COOL
  - `3`: AUTO

**Test Commands**:
```bash
# Get thermostat ID
TSTAT_ID=$(curl -s http://localhost:8000/api/thermostats | jq -r '.[0].thermostat_id')

# Set to HEAT mode
curl -X POST http://localhost:8000/api/thermostats/$TSTAT_ID/mode \
  -H "Content-Type: application/json" \
  -d '{"tmode": 1}' | jq .

# Set to OFF mode
curl -X POST http://localhost:8000/api/thermostats/$TSTAT_ID/mode \
  -H "Content-Type: application/json" \
  -d '{"tmode": 0}' | jq .
```

**Response**: 200 OK
```json
{
  "thermostat_id": "5CDAD4123456",
  "name": "Living Room",
  "ip_address": "10.0.60.1",
  "status": "success",
  "response": {
    "success": 0
  }
}
```

---

### System Health Endpoints

#### System Health Check

```http
GET /api/system/health
```

**Description**: Returns service health status, database connectivity, thermostat counts, and weather service status.

**Test Command**:
```bash
curl http://localhost:8000/api/system/health | jq .
```

**Response**: 200 OK (healthy)
```json
{
  "status": "healthy",
  "database": "connected",
  "thermostats": {
    "active_count": 5,
    "with_recent_status": 5
  },
  "weather_service": {
    "enabled": true,
    "current_temp": 32.5,
    "last_update": "2024-12-25T10:15:00Z",
    "error_count": 0,
    "last_error": null
  },
  "timestamp": "2024-12-25T10:30:00.000000Z"
}
```

**Response**: 200 OK (unhealthy)
```json
{
  "status": "unhealthy",
  "error": "Database connection failed",
  "timestamp": "2024-12-25T10:30:00.000000Z"
}
```

**Fields**:
- `status`: "healthy" or "unhealthy"
- `database`: Database connection status
- `thermostats.active_count`: Number of active thermostats
- `thermostats.with_recent_status`: Number with recent status data
- `weather_service`: Weather service health
- `timestamp`: Check timestamp (UTC)

---

### Weather Endpoints

#### Get Weather Status

```http
GET /api/weather/status
```

**Description**: Returns weather service status, configuration, and update history.

**Test Command**:
```bash
curl http://localhost:8000/api/weather/status | jq .
```

**Response**: 200 OK (enabled)
```json
{
  "enabled": true,
  "zip_code": "02632",
  "current_temp": 32.5,
  "last_update": "2024-12-25T10:15:00Z",
  "last_error": null,
  "update_count": 48,
  "error_count": 0,
  "next_update": "2024-12-25T10:30:00Z"
}
```

**Response**: 200 OK (disabled)
```json
{
  "enabled": false,
  "zip_code": null,
  "current_temp": null,
  "last_update": null,
  "last_error": "Weather service not initialized",
  "update_count": 0,
  "error_count": 0,
  "next_update": null
}
```

**Fields**:
- `enabled`: Whether weather service is active
- `zip_code`: Configured ZIP code
- `current_temp`: Current outdoor temperature (°F)
- `last_update`: Last successful update timestamp
- `last_error`: Last error message (null if none)
- `update_count`: Total successful updates
- `error_count`: Total failed updates
- `next_update`: Scheduled next update time

---

#### Get Current Weather

```http
GET /api/weather/current
```

**Description**: Returns current outdoor temperature only (quick lookup).

**Test Command**:
```bash
curl http://localhost:8000/api/weather/current | jq .
```

**Response**: 200 OK
```json
{
  "temperature": 32.5,
  "zip_code": "02632",
  "timestamp": "2024-12-25T10:30:00.000000",
  "enabled": true
}
```

**Error Response**: 503 Service Unavailable
```json
{
  "detail": "Weather service not available"
}
```

---

#### Force Weather Update

```http
POST /api/weather/update
```

**Description**: Immediately triggers weather data update (bypasses scheduled interval).

**Test Command**:
```bash
curl -X POST http://localhost:8000/api/weather/update | jq .
```

**Response**: 200 OK
```json
{
  "message": "Weather update completed",
  "current_temp": 32.5,
  "last_update": "2024-12-25T10:30:15Z",
  "last_error": null
}
```

**Error Response**: 503 Service Unavailable
```json
{
  "detail": "Weather service not available"
}
```

---

#### Get Temperature Comparison

```http
GET /api/site/status/comparison
```

**Description**: Returns indoor vs outdoor temperature comparison for all thermostats.

**Test Command**:
```bash
curl http://localhost:8000/api/site/status/comparison | jq .
```

**Response**: 200 OK
```json
{
  "comparisons": [
    {
      "thermostat_id": "5CDAD4123456",
      "indoor_temp": 68.5,
      "outdoor_temp": 32.5,
      "setpoint": 70.0,
      "ts": "2024-12-25T10:30:00.000Z",
      "indoor_outdoor_diff": 36.0,
      "setpoint_outdoor_diff": 37.5
    }
  ],
  "weather_enabled": true,
  "zip_code": "02632",
  "timestamp": "2024-12-25T10:30:00.000000"
}
```

**Fields**:
- `comparisons`: Array of temperature comparisons
  - `indoor_temp`: Current indoor temperature
  - `outdoor_temp`: Current outdoor temperature
  - `setpoint`: Current heating setpoint
  - `indoor_outdoor_diff`: Indoor - Outdoor difference
  - `setpoint_outdoor_diff`: Setpoint - Outdoor difference
- `weather_enabled`: Weather service status
- `zip_code`: Configured ZIP code
- `timestamp`: Comparison timestamp

---

### Sync Monitoring Endpoints

#### Get Sync Status

```http
GET /api/system/sync/status
```

**Description**: Returns public server sync status and health.

**Test Command**:
```bash
curl http://localhost:8000/api/system/sync/status | jq .
```

**Response**: 200 OK (enabled & healthy)
```json
{
  "enabled": true,
  "server_url": "https://your-server.com:8001",
  "status_last_upload": "2024-12-25T10:29:45.000Z",
  "minute_last_upload": "2024-12-25T10:29:30.000Z",
  "command_last_poll": "2024-12-25T10:29:50.000Z",
  "health_status": "healthy",
  "error_message": null
}
```

**Response**: 200 OK (disabled)
```json
{
  "enabled": false,
  "server_url": null,
  "status_last_upload": null,
  "minute_last_upload": null,
  "command_last_poll": null,
  "health_status": "disabled",
  "error_message": null
}
```

**Fields**:
- `enabled`: Whether sync is active
- `server_url`: Public server URL
- `status_last_upload`: Last status upload timestamp
- `minute_last_upload`: Last minute data upload timestamp
- `command_last_poll`: Last command poll timestamp
- `health_status`: "healthy", "degraded", "disabled", or "error"
- `error_message`: Error description if health_status is "degraded" or "error"

---

#### Get Sync Checkpoints

```http
GET /api/system/sync/checkpoints
```

**Description**: Returns detailed sync checkpoint information with elapsed times.

**Test Command**:
```bash
curl http://localhost:8000/api/system/sync/checkpoints | jq .
```

**Response**: 200 OK
```json
{
  "checkpoints": {
    "status_upload": {
      "last_timestamp": "2024-12-25T10:29:45.000Z",
      "minutes_ago": 0.25
    },
    "minute_upload": {
      "last_timestamp": "2024-12-25T10:29:30.000Z",
      "minutes_ago": 0.5
    },
    "command_poll": {
      "last_timestamp": "2024-12-25T10:29:50.000Z",
      "minutes_ago": 0.17
    }
  },
  "timestamp": "2024-12-25T10:30:00.000000"
}
```

**Fields**:
- `checkpoints`: Dictionary of checkpoint data
  - `last_timestamp`: Last checkpoint time (UTC)
  - `minutes_ago`: Minutes elapsed since last checkpoint
- `timestamp`: Current timestamp

---

#### Get Sync Statistics

```http
GET /api/system/sync/stats
```

**Description**: Returns database statistics for thermostats, raw readings, and minute aggregations.

**Test Command**:
```bash
curl http://localhost:8000/api/system/sync/stats | jq .
```

**Response**: 200 OK
```json
{
  "thermostats": {
    "active_count": 5
  },
  "raw_readings": {
    "total_count": 156789,
    "earliest": "2024-12-11T00:00:00.000Z",
    "latest": "2024-12-25T10:30:00.000Z",
    "with_weather_data": 156789
  },
  "minute_readings": {
    "total_count": 20160,
    "earliest": "2024-11-11T00:00:00.000Z",
    "latest": "2024-12-25T10:29:00.000Z",
    "with_weather_data": 20160
  },
  "timestamp": "2024-12-25T10:30:00.000000"
}
```

**Fields**:
- `thermostats.active_count`: Number of active thermostats
- `raw_readings`: Statistics for raw 5-second readings
  - `total_count`: Total raw readings (14 days retention)
  - `earliest`: Oldest reading timestamp
  - `latest`: Newest reading timestamp
  - `with_weather_data`: Readings with outdoor temperature
- `minute_readings`: Statistics for minute aggregations
  - `total_count`: Total minute records (365 days retention)
  - `earliest`: Oldest minute timestamp
  - `latest`: Newest minute timestamp
  - `with_weather_data`: Minutes with outdoor temperature

---

### Discovery Endpoints

#### Trigger Discovery Scan

```http
POST /api/discovery/scan
```

**Description**: Manually triggers network discovery for new thermostats. Discovery runs asynchronously.

**Test Command**:
```bash
curl -X POST http://localhost:8000/api/discovery/scan | jq .
```

**Response**: 200 OK
```json
{
  "message": "Discovery scan initiated"
}
```

**Note**: Check logs or list thermostats after 30-60 seconds to see results. Discovery includes:
- Database device testing (known devices)
- UDP multicast discovery
- Optional TCP IP range scanning (if configured)

---

## Public Server API (Outbound)

**ThermostatLocalServer → ThermostatPublicServer Communication**

**Version**: 2.0  
**Last Updated**: December 29, 2024  
**Verified Against**: ThermostatPublicServer source code and live testing

### Overview

**Base URL**: Configured in local server `config.yaml`
```yaml
public_server:
  base_url: "https://your-server.com:8001"
  site_token: "your_site_token"
```

**Protocol**: HTTPS (SSL/TLS recommended for production)

**Retry Logic**: All requests include automatic retry (default: 3 attempts) with exponential backoff

---

### Authentication

All requests use **Site Token Authentication** via header:

```http
X-Site-Token: {your_site_token}
Content-Type: application/json
```

The site token is configured in the public server's `config.yaml` and must match for authentication to succeed.

---

### Register Thermostats

**Purpose:** Register newly discovered thermostats with the public server

**Endpoint:**
```http
POST /api/v1/sites/{site_id}/thermostats/register
```

**Headers:**
```http
X-Site-Token: {site_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "site_id": "cape_home",
  "thermostats": [
    {
      "thermostat_id": "2002af72cd92",
      "name": "Living Room",
      "model": "CT50 V1.94",
      "ip_address": "10.0.60.1",
      "api_version": 113,
      "fw_version": "1.04.84",
      "discovery_method": "udp",
      "capabilities": {
        "heating": true,
        "cooling": true,
        "fan": true
      },
      "away_temp": 50.0
    }
  ]
}
```

**Request Fields:**
- `site_id` - Site identifier (must match URL)
- `thermostats[]` - Array of thermostat objects
  - `thermostat_id` - Unique device identifier (MAC address)
  - `name` - User-friendly name
  - `model` - Device model (e.g., "CT50 V1.94")
  - `ip_address` - Local IP address
  - `api_version` - Device API version
  - `fw_version` - Firmware version
  - `discovery_method` - How device was found ("udp", "tcp", "database")
  - `capabilities` - Device capabilities object
  - `away_temp` - Away mode temperature setting

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Registered 1 thermostats (0 skipped)",
  "data": {
    "registered_count": 1,
    "skipped_count": 0
  }
}
```

**Triggered:**
- After discovery completes
- When new devices are found
- On initial startup

---

### Upload Status Data

**Purpose:** Upload current thermostat status (real-time monitoring)

**Endpoint:**
```http
POST /api/v1/sites/{site_id}/status
```

**Headers:**
```http
X-Site-Token: {site_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "site_id": "cape_home",
  "timestamp": "2024-12-29T15:30:00.000Z",
  "thermostats": [
    {
      "thermostat_id": "2002af72cd92",
      "temp": 68.5,
      "t_heat": 70.0,
      "tmode": 1,
      "tstate": 0,
      "fmode": 0,
      "fstate": 0,
      "override": false,
      "hold": 0,
      "local_temp": 32.5,
      "ip_address": "10.0.60.1",
      "last_poll_success": true,
      "last_error": null
    }
  ]
}
```

**Request Fields:**
- `site_id` - Site identifier
- `timestamp` - ISO 8601 timestamp (UTC)
- `thermostats[]` - Array of status objects
  - `thermostat_id` - Device identifier
  - `temp` - Current temperature (°F)
  - `t_heat` - Heat setpoint (°F)
  - `tmode` - Operating mode (0=OFF, 1=HEAT, 2=COOL, 3=AUTO)
  - `tstate` - HVAC state (0=OFF, 1=HEATING, 2=COOLING)
  - `fmode` - Fan mode (0=AUTO, 1=AUTO/CIRCULATE, 2=ON)
  - `fstate` - Fan state (0=OFF, 1=ON)
  - `override` - Schedule override active (boolean)
  - `hold` - Hold mode (0=OFF, 1=ON)
  - `local_temp` - Outside temperature (°F)
  - `ip_address` - Device IP address
  - `last_poll_success` - Whether last poll succeeded (boolean)
  - `last_error` - Error message if poll failed (string or null)

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Status updated for 1 thermostats",
  "data": {
    "received_count": 1,
    "updated_count": 1
  }
}
```

**Triggered:**
- Every 30 seconds (periodic polling)
- Immediately on state change detection
- Batched for multiple thermostats

**Notes:**
- Public server converts `tmode` (int) → `mode` (string)
- Public server converts `tstate` (int) → `hvac_state` (string)
- Public server converts `hold` (int) → `hold_status` (boolean)
- Updates `status_cache` table
- Broadcasts to WebSocket clients in real-time

---

### Upload Minute History

**Purpose:** Upload minute-level aggregated data for historical analysis

**Endpoint:**
```http
POST /api/v1/sites/{site_id}/minute
```

**Headers:**
```http
X-Site-Token: {site_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "site_id": "cape_home",
  "minute_readings": [
    {
      "thermostat_id": "2002af72cd92",
      "minute_ts": "2024-12-29T15:30:00.000Z",
      "temp_avg": 68.3,
      "t_heat_last": 70.0,
      "tmode_last": 1,
      "hvac_runtime_percent": 35.2,
      "poll_count": 2,
      "poll_failures": 0,
      "local_temp_avg": 32.5
    }
  ]
}
```

**Request Fields:**
- `site_id` - Site identifier
- `minute_readings[]` - Array of minute aggregation objects
  - `thermostat_id` - Device identifier
  - `minute_ts` - Minute timestamp (start of minute, ISO 8601 UTC)
  - `temp_avg` - Average temperature over the minute (°F)
  - `t_heat_last` - Last setpoint value in the minute (°F)
  - `tmode_last` - Last operating mode in the minute (0/1/2/3)
  - `hvac_runtime_percent` - Percentage of minute HVAC was active (0.0-100.0)
  - `poll_count` - Number of successful polls during minute
  - `poll_failures` - Number of failed polls during minute
  - `local_temp_avg` - Average outside temperature (°F)

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Minute data processed: 1 records",
  "data": {
    "received_count": 1,
    "inserted_count": 1,
    "average_runtime_percent": 35.2,
    "active_records": 1
  }
}
```

**Triggered:**
- Every 60 seconds
- Batched (up to 100 readings per request)

**Notes:**
- ⚠️ **IMPORTANT:** Field name is `minute_readings`, not `readings`
- Public server converts `t_heat_last` → `setpoint_last`
- Public server converts `tmode_last` (int) → `mode_last` (string)
- Inserts into `minute_history` table (idempotent upsert)
- Updates runtime state for fast queries

---

### Poll Commands

**Purpose:** Poll for pending commands from public server

**Endpoint:**
```http
GET /api/v1/sites/{site_id}/commands/pending
```

**Headers:**
```http
X-Site-Token: {site_token}
```

**Response:** `200 OK` (with commands)
```json
{
  "commands": [
    {
      "cmd_id": "5a77730d-dacb-43cc-8077-56cb5e42945f",
      "thermostat_id": "2002af72cd92",
      "command": "set_state",
      "params": {
        "tmode": 1,
        "hold": 0,
        "t_heat": 72.0
      },
      "created_at": "2024-12-29T15:30:00.000Z",
      "timeout_seconds": 300
    }
  ]
}
```

**Response:** `200 OK` (no commands)
```json
{
  "commands": []
}
```

**Response Fields:**
- `commands[]` - Array of command objects
  - `cmd_id` - Unique command identifier (UUID)
  - `thermostat_id` - Target device identifier (or null for site-wide)
  - `command` - Command type (see below)
  - `params` - Command-specific parameters (object)
  - `created_at` - Command creation timestamp (ISO 8601)
  - `timeout_seconds` - Execution timeout

**Supported Commands:**

1. **set_state** - Set thermostat state
   ```json
   {
     "command": "set_state",
     "params": {
       "tmode": 1,
       "hold": 0,
       "t_heat": 72.0
     }
   }
   ```
   - `tmode`: 0 (OFF) or 1 (HEAT)
   - `hold`: 0 (OFF) or 1 (ON)
   - `t_heat`: Temperature setpoint (required when tmode=1, omit when tmode=0)

2. **set_away_temp** - Set away temperature
   ```json
   {
     "command": "set_away_temp",
     "params": {
       "away_temp": 50.0
     }
   }
   ```
   - `away_temp`: Away mode temperature (41.0-76.0°F)

3. **discover_devices** - Trigger device discovery
   ```json
   {
     "command": "discover_devices",
     "params": {
       "phases_to_run": ["database", "udp_discovery", "tcp_discovery"],
       "apply_initial_config": true,
       "progress_updates": true
     }
   }
   ```

**Triggered:**
- Every 10 seconds (automatic polling)

**Notes:**
- Commands are marked as "pending" in database
- After retrieval, local server should execute and report results

---

### Submit Command Results

**Purpose:** Send command execution acknowledgments back to public server

**Endpoint:**
```http
POST /api/v1/sites/{site_id}/commands/results
```

**Headers:**
```http
X-Site-Token: {site_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "site_id": "cape_home",
  "results": [
    {
      "cmd_id": "5a77730d-dacb-43cc-8077-56cb5e42945f",
      "success": true,
      "executed_at": "2024-12-29T15:30:15.000Z",
      "error_message": null,
      "response_data": {
        "tmode": 1,
        "t_heat": 72.0,
        "hold": 0
      }
    }
  ]
}
```

**Request Fields:**
- `site_id` - Site identifier
- `results[]` - Array of result objects
  - `cmd_id` - Command identifier (from pending commands)
  - `success` - Whether command succeeded (boolean)
  - `executed_at` - Execution timestamp (ISO 8601 UTC)
  - `error_message` - Error description if failed (string or null)
  - `response_data` - Response from device (object, optional)

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Processed 1 command results",
  "data": {
    "received_count": 1,
    "processed_count": 1
  }
}
```

**Triggered:**
- Immediately after command execution
- Batched (every 2 seconds for multiple results)

**Notes:**
- Updates command status in database
- Sets `acknowledged_at` timestamp
- Logs security events for audit trail

---

### Submit Discovery Progress

**Purpose:** Send real-time discovery progress updates to public server

**Endpoint:**
```http
POST /api/v1/sites/{site_id}/commands/progress
```

**Headers:**
```http
X-Site-Token: {site_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "command_id": "discovery-5a77730d-dacb-43cc-8077-56cb5e42945f",
  "site_id": "cape_home",
  "status": "in_progress",
  "phase_history": [
    {
      "phase": "database",
      "status": "completed",
      "elapsed_time": 2.5,
      "device_ids": ["2002af72cd92", "2002af7368bb"],
      "devices_found": 2,
      "current_action": "Loaded 2 devices from database",
      "ips_scanned": null,
      "ips_to_scan": null
    },
    {
      "phase": "udp_discovery",
      "status": "in_progress",
      "elapsed_time": 8.2,
      "device_ids": [],
      "devices_found": 0,
      "current_action": "Listening for UDP broadcasts...",
      "ips_scanned": null,
      "ips_to_scan": null
    }
  ]
}
```

**Request Fields:**
- `command_id` - Discovery command identifier
- `site_id` - Site identifier
- `status` - Overall discovery status (see below)
- `phase_history[]` - Array of phase objects (in execution order)
  - `phase` - Phase name (see below)
  - `status` - Phase status ("pending", "in_progress", "completed", "failed")
  - `elapsed_time` - Phase execution time in seconds
  - `device_ids` - Devices found in this phase (array)
  - `devices_found` - Count of devices found
  - `current_action` - Human-readable status message
  - `ips_scanned` - For TCP phase, IPs already scanned (optional)
  - `ips_to_scan` - For TCP phase, total IPs to scan (optional)

**Status Values:**
- `pending` - Discovery queued but not started
- `in_progress` - Discovery is running
- `completed` - Discovery finished successfully
- `failed` - Discovery failed with error

**Phase Values:**
- `database` - Testing known devices from database
- `udp_discovery` - UDP multicast discovery
- `tcp_discovery` - TCP IP range scanning

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Progress updated successfully",
  "data": null
}
```

**Triggered:**
- At start of each discovery phase
- During phase progress (especially for long TCP scans)
- At completion of each phase
- On discovery completion or failure

**Notes:**
- ⚠️ **IMPORTANT:** Status value is `in_progress` (with underscore), not `inprogress`
- Public server adds `known_device_ids` from database
- Progress is stored in memory (not in database)
- Broadcasts to WebSocket clients for real-time UI updates
- Available via polling endpoints for web dashboard

---

### Public Error Handling

#### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid request data or site_id mismatch |
| 401 | Unauthorized | Invalid or missing X-Site-Token |
| 404 | Not Found | Site not found |
| 500 | Internal Server Error | Server error |

#### Error Response Format

```json
{
  "detail": "Error description"
}
```

#### Common Errors

**Invalid Site Token:**
```json
{
  "detail": "Invalid site token",
  "status_code": 401
}
```

**Site ID Mismatch:**
```json
{
  "detail": "Site ID in URL does not match request data",
  "status_code": 400
}
```

**Validation Error:**
```json
{
  "detail": [
    {
      "loc": ["body", "minute_readings"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

#### Retry Strategy

Local servers should implement retry logic with exponential backoff:

1. **First attempt:** Immediate
2. **Second attempt:** Wait 1 second
3. **Third attempt:** Wait 2 seconds
4. **After 3 failures:** Log error and continue

**Do not retry on:**
- 400 Bad Request (fix the request data)
- 401 Unauthorized (check site token)

---

### Testing

#### PowerShell Test Example

```powershell
# Configuration
$PUBLIC_SERVER = "https://${PUBLIC_SERVER_IP}:8001"
$SITE_ID = "cape_home"
$SITE_TOKEN = "your_site_token"

# Headers
$headers = @{
    "X-Site-Token" = $SITE_TOKEN
    "Content-Type" = "application/json"
}

# Test Status Upload
$statusData = @{
    site_id = $SITE_ID
    timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    thermostats = @(
        @{
            thermostat_id = "2002af72cd92"
            temp = 68.5
            t_heat = 70.0
            tmode = 1
            tstate = 0
            fmode = 0
            fstate = 0
            override = $false
            hold = 0
            local_temp = 32.0
            ip_address = "10.0.60.5"
            last_poll_success = $true
            last_error = $null
        }
    )
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "$PUBLIC_SERVER/api/v1/sites/$SITE_ID/status" `
        -Method Post -Headers $headers -Body $statusData
    Write-Host "Success:" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "Error:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
```

---

### Communication Flow Diagram

```
┌─────────────────┐                    ┌──────────────────┐
│  Local Server   │                    │  Public Server   │
│  (cape_home)    │                    │  (AWS Cloud)     │
└────────┬────────┘                    └────────┬─────────┘
         │                                      │
         │ 1. Register Thermostats              │
         │ POST /thermostats/register           │
         ├─────────────────────────────────────>│
         │                                      │ Store in DB
         │<─────────────────────────────────────┤
         │ {"registered_count": 4}              │
         │                                      │
         │ 2. Upload Status (every 30s)         │
         │ POST /status                         │
         ├─────────────────────────────────────>│
         │                                      │ Update cache
         │                                      │ Broadcast WS
         │<─────────────────────────────────────┤
         │ {"updated_count": 4}                 │
         │                                      │
         │ 3. Upload Minute (every 60s)         │
         │ POST /minute                         │
         ├─────────────────────────────────────>│
         │                                      │ Insert history
         │                                      │ Update runtime
         │<─────────────────────────────────────┤
         │ {"inserted_count": 4}                │
         │                                      │
         │ 4. Poll Commands (every 10s)         │
         │ GET /commands/pending                │
         ├─────────────────────────────────────>│
         │<─────────────────────────────────────┤ Check DB
         │ {"commands": [...]}                  │
         │                                      │
         │ 5. Execute Command                   │
         │ (to thermostat device)               │
         │                                      │
         │ 6. Report Result                     │
         │ POST /commands/results               │
         ├─────────────────────────────────────>│
         │                                      │ Update DB
         │<─────────────────────────────────────┤ Broadcast WS
         │ {"processed_count": 1}               │
         │                                      │
         │ 7. Discovery Progress (optional)     │
         │ POST /commands/progress              │
         ├─────────────────────────────────────>│
         │                                      │ Store memory
         │                                      │ Broadcast WS
         │<─────────────────────────────────────┤
         │ {"success": true}                    │
         │                                      │
```

### Timing and Frequency

| Operation | Frequency | Notes |
|-----------|-----------|-------|
| Register Thermostats | On discovery | Only when new devices found |
| Upload Status | Every 30 seconds | Real-time monitoring |
| Upload Minute History | Every 60 seconds | Historical data |
| Poll Commands | Every 10 seconds | Command retrieval |
| Submit Command Results | Immediate | After execution |
| Submit Discovery Progress | During discovery | Real-time updates |

### Notes for Developers

1. **Field Names Matter:**
   - Use `minute_readings` (not `readings`) for minute uploads
   - Use `in_progress` (not `inprogress`) for discovery status

2. **Response Structure:**
   - All responses use `ApiResponse` format with `success`, `message`, and `data`
   - Access data via `response.data.field_name`

3. **Authentication:**
   - Site token must match public server configuration
   - Token is sent in `X-Site-Token` header (not `Authorization`)

4. **Timestamps:**
   - Always use ISO 8601 format
   - Always use UTC timezone
   - Format: `YYYY-MM-DDTHH:mm:ss.sssZ`

5. **Batching:**
   - Status uploads can batch multiple thermostats
   - Minute uploads can batch up to 100 readings
   - Command results can be batched

6. **Error Handling:**
   - Implement retry logic with exponential backoff
   - Don't retry 400/401 errors
   - Log all errors for debugging

---

## RadioThermostat Device API

**Base URL**: `http://{device_ip}`

**Format**: JSON

**Authentication**: None

**Reference**: See `docs/RadioThermostat_CT50_Honeywell_Wifi_API_V1.3.pdf`

### Common Device Endpoints

#### Get System Information

```http
GET /sys
```

**Response**:
```json
{
  "uuid": "5CDAD4123456",
  "api_version": 1,
  "fw_version": "1.94",
  "wlan_fw_version": "4.0.3"
}
```

---

#### Get Device Name

```http
GET /sys/name
```

**Response**:
```json
{
  "name": "Living Room"
}
```

---

#### Get Model

```http
GET /tstat/model
```

**Response**:
```json
{
  "model": "CT50"
}
```

---

#### Get Status

```http
GET /tstat
```

**Response**:
```json
{
  "temp": 68.5,
  "tmode": 1,
  "fmode": 0,
  "override": 0,
  "hold": 0,
  "t_heat": 70.0,
  "t_cool": 75.0,
  "tstate": 0,
  "fstate": 0,
  "time": {
    "day": 3,
    "hour": 14,
    "minute": 30
  },
  "t_type_post": 0
}
```

**Key Fields**:
- `temp`: Current temperature
- `tmode`: Operating mode (0=OFF, 1=HEAT, 2=COOL, 3=AUTO)
- `t_heat`: Heat setpoint
- `t_cool`: Cool setpoint
- `tstate`: Current HVAC state (0=OFF, 1=HEATING, 2=COOLING)
- `hold`: Hold status (0=off, 1=on)
- `override`: Override status (0=off, 1=on)

---

#### Set State

```http
POST /tstat
Content-Type: application/json

{
  "tmode": 1,
  "t_heat": 72.0,
  "hold": 1
}
```

**Response**:
```json
{
  "success": 0
}
```

**Note**: `success: 0` indicates command accepted (NOT an error - zero means success!).

---

## Response Codes

### HTTP Status Codes

**Local API**:
- `200 OK`: Request successful
- `404 Not Found`: Resource not found (thermostat not found)
- `422 Unprocessable Entity`: Invalid request data (validation error)
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service unavailable (weather service disabled)

**Public Server API**:
- `200 OK`: Request successful
- `201 Created`: Resource created
- `400 Bad Request`: Invalid request data or site_id mismatch
- `401 Unauthorized`: Invalid or missing X-Site-Token
- `404 Not Found`: Site not found / No pending commands
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limited
- `500 Internal Server Error`: Server error

**RadioThermostat Device API**:
- `200 OK`: Request successful
- `404 Not Found`: Endpoint not found
- `500 Internal Server Error`: Device error

### Success Values

RadioThermostat API uses `success` field in response:
- `success: 0`: ✅ Command accepted (SUCCESSFUL)
- `success: 1` or other non-zero: ❌ Command rejected/failed

**Important**: Zero (0) means success, not failure!

---

## Error Handling

### Request Errors

**Invalid Thermostat ID**:
```json
{
  "detail": "Thermostat not found"
}
```

**Invalid Request Data**:
```json
{
  "detail": [
    {
      "loc": ["body", "t_heat"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Network Errors

**Connection Timeout**:
```json
{
  "thermostat_id": "5CDAD4123456",
  "status": "failed",
  "error": "Connection timeout"
}
```

**Device Unreachable**:
```json
{
  "thermostat_id": "5CDAD4123456",
  "status": "failed",
  "error": "HTTP 500"
}
```

### Retry Behavior

**Local API**: No automatic retry (client should retry)

**Public Server API**: 
- Automatic retry: 3 attempts
- Delay: Exponential backoff (1s, 2s)
- Rate limiting: Backs off on 429 errors

**Device API**:
- Timeout: 5 seconds
- Retry: 3 attempts (configurable)
- Fallback: Mark device offline

---

## API Documentation

**Interactive Documentation**: 
```bash
# Swagger UI
http://localhost:8000/docs

# ReDoc
http://localhost:8000/redoc

# OpenAPI JSON Schema
curl http://localhost:8000/openapi.json | jq .
```

**List all endpoints**:
```bash
curl -s http://localhost:8000/openapi.json | jq -r '.paths | keys[]'
```

---

*API Reference v2.1.0 - Updated December 29, 2024*  
*Local API verified against implementation*  
*Public Server API verified against ThermostatPublicServer v2.0*
