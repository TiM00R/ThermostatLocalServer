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

**Base URL**: Configured in `config.yaml` (`public_server.base_url`)

**Authentication**: Header-based
```http
X-Site-Token: {site_token}
Content-Type: application/json
```

**SSL/TLS**: Configurable (HTTPS recommended)

All requests include retry logic (default: 3 attempts) with exponential backoff.

### Register Thermostats

```http
POST /api/v1/sites/{site_id}/thermostats/register
X-Site-Token: {token}
Content-Type: application/json
```

**Description**: Register discovered thermostats with public server.

**Request Body**:
```json
{
  "site_id": "cape_home",
  "thermostats": [
    {
      "thermostat_id": "5CDAD4123456",
      "name": "Living Room",
      "model": "CT50",
      "ip_address": "10.0.60.1",
      "api_version": 1,
      "fw_version": "1.94",
      "capabilities": {},
      "discovery_method": "udp_multicast",
      "away_temp": 50.0
    }
  ]
}
```

**Response**: 200 OK
```json
{
  "registered": 1,
  "updated": 0,
  "errors": []
}
```

**Triggered**: 
- After discovery completes
- When new devices found

---

### Upload Status

```http
POST /api/v1/sites/{site_id}/status
X-Site-Token: {token}
Content-Type: application/json
```

**Description**: Upload current thermostat status.

**Request Body**:
```json
{
  "site_id": "cape_home",
  "timestamp": "2024-12-25T10:30:00.000Z",
  "thermostats": [
    {
      "thermostat_id": "5CDAD4123456",
      "ip_address": "10.0.60.1",
      "temp": 68.5,
      "t_heat": 70.0,
      "tmode": 1,
      "tstate": 0,
      "hold": 0,
      "override": 0,
      "local_temp": 32.5,
      "last_poll_success": true,
      "last_error": null
    }
  ]
}
```

**Response**: 200 OK
```json
{
  "received": 1,
  "processed": 1
}
```

**Triggered**:
- Every 30 seconds (periodic)
- Immediately on state change detection
- Batched for multiple thermostats

---

### Upload Minute Aggregations

```http
POST /api/v1/sites/{site_id}/minute
X-Site-Token: {token}
Content-Type: application/json
```

**Description**: Upload minute-level aggregated data.

**Request Body**:
```json
{
  "site_id": "cape_home",
  "readings": [
    {
      "thermostat_id": "5CDAD4123456",
      "minute_ts": "2024-12-25T10:30:00.000Z",
      "temp_avg": 68.5,
      "t_heat_last": 70.0,
      "tmode_last": 1,
      "hvac_runtime_percent": 35.2,
      "poll_count": 12,
      "poll_failures": 0,
      "local_temp_avg": 32.5
    }
  ]
}
```

**Fields**:
- `minute_ts`: Minute timestamp (start of minute)
- `temp_avg`: Average temperature over the minute
- `t_heat_last`: Last setpoint in the minute
- `tmode_last`: Last mode in the minute
- `hvac_runtime_percent`: Percentage of time HVAC was active (0-100)
- `poll_count`: Number of successful polls in the minute
- `poll_failures`: Number of failed polls
- `local_temp_avg`: Average outside temperature

**Response**: 200 OK
```json
{
  "received": 1,
  "processed": 1
}
```

**Triggered**:
- Every 60 seconds
- Batched (up to 100 readings per request)

---

### Poll Commands

```http
GET /api/v1/sites/{site_id}/commands/pending
X-Site-Token: {token}
```

**Description**: Poll for pending commands from public server.

**Response**: 200 OK
```json
{
  "commands": [
    {
      "cmd_id": "cmd-123456",
      "command": "set_state",
      "thermostat_id": "5CDAD4123456",
      "params": {
        "tmode": 1,
        "t_heat": 72.0,
        "hold": 1
      },
      "timeout_seconds": 30
    }
  ]
}
```

**Response**: 200 OK (no pending commands)
```json
{
  "commands": []
}
```

**Command Types**:

1. **set_state**: Set thermostat state
   ```json
   {
     "cmd_id": "...",
     "command": "set_state",
     "thermostat_id": "...",
     "params": {
       "tmode": 1,
       "t_heat": 72.0,
       "hold": 1
     }
   }
   ```

2. **set_away_temp**: Set away temperature
   ```json
   {
     "cmd_id": "...",
     "command": "set_away_temp",
     "thermostat_id": "...",
     "params": {
       "away_temp": 50.0
     }
   }
   ```

3. **discover_devices**: Trigger discovery
   ```json
   {
     "cmd_id": "...",
     "command": "discover_devices",
     "params": {
       "discovery_type": "full"
     }
   }
   ```

**Triggered**: Every 10 seconds

---

### Send Command Results

```http
POST /api/v1/sites/{site_id}/commands/results
X-Site-Token: {token}
Content-Type: application/json
```

**Description**: Send command execution acknowledgments.

**Request Body**:
```json
{
  "site_id": "cape_home",
  "results": [
    {
      "cmd_id": "cmd-123456",
      "success": true,
      "executed_at": "2024-12-25T10:30:00.000Z",
      "error_message": null,
      "response_data": {
        "thermostats": [
          {
            "thermostat_id": "5CDAD4123456",
            "success": true,
            "response": {"success": 0}
          }
        ]
      }
    }
  ]
}
```

**Response**: 200 OK
```json
{
  "processed": 1
}
```

**Triggered**: Every 2 seconds (batched)

---

### Send Discovery Progress

```http
POST /api/v1/sites/{site_id}/commands/progress
X-Site-Token: {token}
Content-Type: application/json
```

**Description**: Send real-time discovery progress updates (Protocol v2.0).

**Request Body**:
```json
{
  "command_id": "cmd-789012",
  "site_id": "cape_home",
  "status": "inprogress",
  "execution_time_seconds": 15.3,
  "phase_history": [
    {
      "phase": "database",
      "status": "completed",
      "start_time": "2024-12-25T10:30:00.000Z",
      "elapsed_time": 2.1,
      "devices_found": 3,
      "current_action": "Testing known devices"
    },
    {
      "phase": "udp",
      "status": "inprogress",
      "start_time": "2024-12-25T10:30:02.123Z",
      "elapsed_time": 13.2,
      "devices_found": 2,
      "current_action": "Waiting for UDP responses"
    }
  ]
}
```

**Status Values**:
- `pending`: Discovery queued
- `inprogress`: Discovery running
- `completed`: Discovery finished successfully
- `failed`: Discovery failed

**Phase Values**:
- `database`: Testing known devices from DB
- `udp`: UDP multicast discovery
- `tcp`: TCP IP range scanning

**Response**: 200 OK
```json
{
  "received": true
}
```

**Triggered**: 
- At start of each phase
- During phase progress
- At completion

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
- `404 Not Found`: No pending commands
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
- Delay: 2 seconds (exponential backoff)
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

*API Reference v2.1.0 - Verified against actual implementation (December 2024)*
*No hallucinated endpoints - all endpoints tested and confirmed*
