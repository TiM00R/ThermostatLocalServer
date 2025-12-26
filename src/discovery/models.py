"""
Discovery data structures and models
"""

import time
from typing import List
from dataclasses import dataclass

@dataclass
class ThermostatDevice:
    """Represents a discovered thermostat device"""
    ip: str
    uuid: str
    name: str
    model: str
    api_version: int
    fw_version: str
    base_url: str
    discovery_method: str  # "database", "udp_multicast", "tcp_scan"
    last_seen: float

@dataclass
class DiscoveryResult:
    """Results from discovery operations"""
    devices: List[ThermostatDevice]
    method: str
    duration_seconds: float
    devices_tested: int
    success_count: int
