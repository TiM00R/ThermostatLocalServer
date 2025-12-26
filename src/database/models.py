"""
Database models and data structures
"""

import json
import ipaddress
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime

def _convert_ip_address(ip_addr) -> str:
    """Convert IPv4Address or other IP types to string for JSON serialization"""
    if isinstance(ip_addr, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return str(ip_addr)
    return str(ip_addr) if ip_addr else "0.0.0.0"

@dataclass
class ThermostatRecord:
    """Database record for thermostat device - UPDATED: Added away_temp"""
    thermostat_id: str
    ip_address: str
    name: str
    model: str
    api_version: int
    fw_version: str
    capabilities: Dict[str, Any]
    discovery_method: str
    active: bool = True
    away_temp: Optional[float] = 50.0  # NEW: Away temperature setting (Fahrenheit)
    last_seen: Optional[datetime] = None

@dataclass
class StatusRecord:
    """Database record for thermostat status"""
    thermostat_id: str
    ts: datetime
    temp: float
    t_heat: float
    tmode: int
    tstate: int
    hold: int
    override: int
    ip_address: str
    local_temp: Optional[float] = None  # NEW: Local weather temperature
    last_error: Optional[str] = None

@dataclass
class MinuteReading:
    """Database record for minute aggregations - UPDATED: uses hvac_runtime_percent"""
    thermostat_id: str
    minute_ts: datetime
    temp_avg: float
    t_heat_last: float
    tmode_last: int
    hvac_runtime_percent: float  # Now stores actual runtime percentage (0.0-100.0)
    poll_count: int
    poll_failures: int
    local_temp_avg: Optional[float] = None  # Average local temperature for this minute
