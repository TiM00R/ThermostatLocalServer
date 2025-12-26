"""
Discovery Command Handler for Local Server
Implements remote discovery command execution with progress tracking
UPDATED: Protocol v2.0 - phase_history array format with execution time tracking
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum

from database import DatabaseManager, ThermostatRecord
from discovery.manager import ThermostatDiscovery
from discovery.models import ThermostatDevice, DiscoveryResult

logger = logging.getLogger(__name__)

class DiscoveryStatus(Enum):
    """Discovery command status"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class DiscoveryProgress:
    """Discovery progress information"""
    command_id: str
    status: DiscoveryStatus
    execution_time_seconds: float  # Total time since discovery started
    phase_history: List[Dict]  # Array of all phases with their state
    timestamp: datetime

@dataclass
class DiscoveryCommandResult:
    """Final discovery command result"""
    command_id: str
    status: DiscoveryStatus
    execution_time_seconds: float
    discovery_results: Dict[str, Any]
    error: Optional[Dict[str, Any]] = None

class DiscoveryCommandHandler:
    """Handles discovery command execution with progress tracking"""
    
    def __init__(self, db: DatabaseManager, discovery: ThermostatDiscovery, public_sync=None):
        self.db = db
        self.discovery = discovery
        self.public_sync = public_sync
        
        # Track active discovery
        self.active_discovery: Optional[Dict] = None
        self.progress_callbacks: List[Callable] = []
        
        # Progress tracking
        self.last_progress = None
        
        # NEW: Two separate timers
        self.discovery_start_time = None  # Total discovery time (never reset)
        self.phase_start_time = None      # Per-phase timing (reset each phase)
        
        # NEW: Phase history tracking
        self.phase_history: List[Dict] = []
        
    def add_progress_callback(self, callback: Callable[[DiscoveryProgress], None]):
        """Add callback for progress updates"""
        self.progress_callbacks.append(callback)
    
    def _start_discovery_timer(self):
        """Start the overall discovery timer (called once at start)"""
        self.discovery_start_time = time.time()
    
    def _start_phase_timer(self):
        """Start timing for a new discovery phase"""
        self.phase_start_time = time.time()
    
    def _get_total_execution_time(self) -> float:
        """Get total execution time since discovery started"""
        if self.discovery_start_time is None:
            return 0.0
        return time.time() - self.discovery_start_time
    
    def _get_phase_elapsed_time(self) -> float:
        """Get elapsed time for current phase in seconds"""
        if self.phase_start_time is None:
            return 0.0
        return time.time() - self.phase_start_time
    
    def _initialize_phase_history(self, phases_to_run: List[str]):
        """Initialize phase history with all phases in waiting state"""
        all_phases = ["database", "udp_discovery", "tcp_discovery"]
        self.phase_history = []
        
        for phase in all_phases:
            if phase in phases_to_run:
                status = "waiting"
                action = "Waiting"
            else:
                status = "skipped"
                action = "Skipped"
            
            phase_obj = {
                "phase": phase,
                "status": status,
                "elapsed_time": 0.0,
                "device_ids": [],
                "devices_found": 0,
                "current_action": action
            }
            
            # Add TCP-specific fields
            if phase == "tcp_discovery":
                phase_obj["ips_scanned"] = 0
                phase_obj["ips_to_scan"] = 0
            
            self.phase_history.append(phase_obj)
    
    def _update_phase_in_history(self, phase: str, status: str, device_ids: List[str], 
                                  current_action: str, **kwargs):
        """Update a specific phase in the phase_history array"""
        for p in self.phase_history:
            if p["phase"] == phase:
                p["status"] = status
                p["device_ids"] = device_ids
                p["devices_found"] = len(device_ids)
                p["current_action"] = current_action
                
                # Update elapsed_time based on status
                if status == "inprogress":
                    # For in-progress phase, update time continuously
                    p["elapsed_time"] = self._get_phase_elapsed_time()
                elif status == "completed":
                    # For completed phase, freeze the time
                    p["elapsed_time"] = self._get_phase_elapsed_time()
                elif status in ["waiting", "skipped"]:
                    # For waiting/skipped phases, keep at 0
                    p["elapsed_time"] = 0.0
                
                # Add optional fields (ips_scanned, ips_to_scan for TCP)
                for key, value in kwargs.items():
                    p[key] = value
                
                break
    
    async def execute_discovery_command(self, command: Dict) -> DiscoveryCommandResult:
        """Execute discovery command with full progress tracking"""
        command_id = command.get('cmd_id', f"discover_{int(time.time())}")
        parameters = command.get('params', {})
        
        # Validate command parameters
        validation_error = self._validate_command(parameters)
        if validation_error:
            return DiscoveryCommandResult(
                command_id=command_id,
                status=DiscoveryStatus.FAILED,
                execution_time_seconds=0,
                discovery_results={},
                error=validation_error
            )
        
        # Check if discovery already in progress
        if self.active_discovery:
            return DiscoveryCommandResult(
                command_id=command_id,
                status=DiscoveryStatus.FAILED,
                execution_time_seconds=0,
                discovery_results={},
                error={
                    "code": "DISCOVERY_IN_PROGRESS",
                    "message": "Discovery already in progress, cannot start new discovery",
                    "details": {
                        "current_discovery_id": self.active_discovery['command_id']
                    }
                }
            )
        
        # Initialize discovery tracking
        self.active_discovery = {
            "command_id": command_id,
            "start_time": time.time(),
            "parameters": parameters
        }
        
        # Start total discovery timer
        self._start_discovery_timer()
        
        # Get phases to run
        phases_to_run = parameters.get('phases_to_run', [])
        
        # Initialize phase history
        self._initialize_phase_history(phases_to_run)
        
        try:
            logger.info(f"[LAUNCH] Starting discovery command {command_id} with phases: {phases_to_run}")
            
            # Send initial progress
            await self._update_progress(
                command_id=command_id,
                status=DiscoveryStatus.ACCEPTED
            )
            
            # Execute discovery phases
            result = await self._execute_discovery_phases(command_id, phases_to_run, parameters)
            
            # Handle device registration if requested
            if parameters.get('apply_initial_config', False) and result.discovery_results.get('total_devices_found', 0) > 0:
                await self._handle_device_registration(command_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Discovery command {command_id} failed: {e}")
            return DiscoveryCommandResult(
                command_id=command_id,
                status=DiscoveryStatus.FAILED,
                execution_time_seconds=self._get_total_execution_time(),
                discovery_results={},
                error={
                    "code": "DISCOVERY_EXECUTION_ERROR",
                    "message": str(e),
                    "details": {}
                }
            )
        finally:
            self.active_discovery = None
    
    def _validate_command(self, parameters: Dict) -> Optional[Dict]:
        """Validate discovery command parameters"""
        phases_to_run = parameters.get('phases_to_run')
        if not phases_to_run:
            return {
                "code": "MISSING_PHASES_TO_RUN",
                "message": "phases_to_run parameter is required"
            }
        
        if not isinstance(phases_to_run, list):
            return {
                "code": "INVALID_PHASES_TO_RUN",
                "message": "phases_to_run must be a list"
            }
        
        valid_phases = ['database', 'udp_discovery', 'tcp_discovery']
        for phase in phases_to_run:
            if phase not in valid_phases:
                return {
                    "code": "INVALID_PHASE",
                    "message": f"Invalid phase '{phase}'. Must be one of: {valid_phases}"
                }
        
        return None
    
    async def _execute_discovery_phases(self, command_id: str, phases_to_run: List[str], 
                                        parameters: Dict) -> DiscoveryCommandResult:
        """Execute discovery phases based on phases_to_run list"""
        all_found_ids: set[str] = set()
        all_devices: List[ThermostatDevice] = []
        
        try:
            # Execute each phase if it's in phases_to_run
            if "database" in phases_to_run:
                db_devices = await self._execute_database_phase(command_id)
                all_devices.extend(db_devices)
                all_found_ids.update([d.uuid for d in db_devices if d.uuid])
            
            if "udp_discovery" in phases_to_run:
                udp_devices = await self._execute_udp_phase(command_id)
                all_devices.extend(udp_devices)
                all_found_ids.update([d.uuid for d in udp_devices if d.uuid])
            
            if "tcp_discovery" in phases_to_run:
                tcp_devices = await self._execute_tcp_phase(command_id)
                all_devices.extend(tcp_devices)
                all_found_ids.update([d.uuid for d in tcp_devices if d.uuid])
            
            # Deduplicate devices
            unique_devices: List[ThermostatDevice] = []
            seen_ids: set[str] = set()
            for d in all_devices:
                if d.uuid and d.uuid not in seen_ids:
                    unique_devices.append(d)
                    seen_ids.add(d.uuid)
            
            # Build result
            result = {
                "phases_executed": phases_to_run,
                "total_devices_found": len(all_found_ids),
                "devices_found": [
                    {
                        "thermostat_id": d.uuid,
                        "name": d.name,
                        "ip": d.ip,
                        "discovery_method": d.discovery_method
                    }
                    for d in unique_devices
                ]
            }
            
            # Send final completion progress
            await self._update_progress(
                command_id=command_id,
                status=DiscoveryStatus.COMPLETED
            )
            
            return DiscoveryCommandResult(
                command_id=command_id,
                status=DiscoveryStatus.COMPLETED,
                execution_time_seconds=self._get_total_execution_time(),
                discovery_results=result
            )
            
        except Exception as e:
            logger.error(f"Discovery execution failed: {e}")
            return DiscoveryCommandResult(
                command_id=command_id,
                status=DiscoveryStatus.FAILED,
                execution_time_seconds=self._get_total_execution_time(),
                discovery_results={},
                error={
                    "code": "DISCOVERY_EXECUTION_ERROR",
                    "message": str(e)
                }
            )
    
    async def _execute_database_phase(self, command_id: str) -> List[ThermostatDevice]:
        """Execute database discovery phase"""
        # Start phase timer
        self._start_phase_timer()
        
        # Update to inprogress
        self._update_phase_in_history(
            phase="database",
            status="inprogress",
            device_ids=[],
            current_action="Checking database for known devices"
        )
        await self._update_progress(command_id=command_id, status=DiscoveryStatus.IN_PROGRESS)
        
        # Execute discovery
        db_result = await self.discovery.discover_from_database()
        db_devices = db_result.devices
        
        # Deduplicate device IDs
        seen: set[str] = set()
        db_device_ids = [
            d.uuid for d in db_devices
            if d.uuid and d.uuid not in seen and not seen.add(d.uuid)
        ]
        
        # Update to completed
        self._update_phase_in_history(
            phase="database",
            status="completed",
            device_ids=db_device_ids,
            current_action="Database discovery complete"
        )
        await self._update_progress(command_id=command_id, status=DiscoveryStatus.IN_PROGRESS)
        
        return db_devices
    
    async def _execute_udp_phase(self, command_id: str) -> List[ThermostatDevice]:
        """Execute UDP discovery phase"""
        # Start phase timer
        self._start_phase_timer()
        
        # Update to inprogress - broadcasting
        self._update_phase_in_history(
            phase="udp_discovery",
            status="inprogress",
            device_ids=[],
            current_action="Broadcasting UDP multicast discovery"
        )
        await self._update_progress(command_id=command_id, status=DiscoveryStatus.IN_PROGRESS)
        
        await asyncio.sleep(2.0)
        
        # Update to inprogress - listening
        self._update_phase_in_history(
            phase="udp_discovery",
            status="inprogress",
            device_ids=[],
            current_action="Listening for UDP responses"
        )
        await self._update_progress(command_id=command_id, status=DiscoveryStatus.IN_PROGRESS)
        
        # Execute discovery
        udp_result = await self.discovery.discover_udp_only()
        udp_devices = udp_result.devices
        
        # Deduplicate device IDs
        seen: set[str] = set()
        udp_device_ids = [
            d.uuid for d in udp_devices
            if d.uuid and d.uuid not in seen and not seen.add(d.uuid)
        ]
        
        # Update to completed
        self._update_phase_in_history(
            phase="udp_discovery",
            status="completed",
            device_ids=udp_device_ids,
            current_action="UDP discovery complete"
        )
        await self._update_progress(command_id=command_id, status=DiscoveryStatus.IN_PROGRESS)
        
        return udp_devices
    
    async def _execute_tcp_phase(self, command_id: str) -> List[ThermostatDevice]:
        """Execute TCP discovery phase"""
        tcp_devices: List[ThermostatDevice] = []
        tcp_device_ids: List[str] = []
        
        # Start phase timer
        self._start_phase_timer()
        
        all_ips = self.discovery._generate_scan_ips()
        ips_to_scan = len(all_ips)
        
        # Update to inprogress - starting scan
        self._update_phase_in_history(
            phase="tcp_discovery",
            status="inprogress",
            device_ids=[],
            current_action=f"Scanning IP range {self.discovery.ip_ranges[0]}",
            ips_scanned=0,
            ips_to_scan=ips_to_scan
        )
        await self._update_progress(command_id=command_id, status=DiscoveryStatus.IN_PROGRESS)
        
        # TCP progress callback
        async def tcp_progress_callback(new_devices_since_checkpoint, ips_scanned, ips_total):
            nonlocal tcp_devices, tcp_device_ids
            
            for device in new_devices_since_checkpoint:
                tcp_devices.append(device)
                if device.uuid and device.uuid not in tcp_device_ids:
                    tcp_device_ids.append(device.uuid)
            
            # Update phase with progress
            self._update_phase_in_history(
                phase="tcp_discovery",
                status="inprogress",
                device_ids=tcp_device_ids,
                current_action=f"Scanning IP range {self.discovery.ip_ranges[0]}",
                ips_scanned=ips_scanned,
                ips_to_scan=ips_total
            )
            await self._update_progress(command_id=command_id, status=DiscoveryStatus.IN_PROGRESS)
        
        # Execute TCP scan
        tcp_scan_result = await self.discovery.discover_tcp_progressive(callback=tcp_progress_callback)
        
        # Update to completed
        self._update_phase_in_history(
            phase="tcp_discovery",
            status="completed",
            device_ids=tcp_device_ids,
            current_action="IP scan complete",
            ips_scanned=ips_to_scan,
            ips_to_scan=ips_to_scan
        )
        await self._update_progress(command_id=command_id, status=DiscoveryStatus.IN_PROGRESS)
        
        return tcp_devices
    
    async def _handle_device_registration(self, command_id: str, result: DiscoveryCommandResult):
        """Handle device registration after discovery"""
        try:
            devices_data = result.discovery_results.get('devices_found', [])
            if not devices_data:
                return
            
            logger.info(f"Registering {len(devices_data)} devices")
            
            # Convert to ThermostatRecord format for registration
            thermostats_to_register = []
            for device_data in devices_data:
                # Check if device is already in database
                existing = await self.db.get_thermostat_by_id(device_data['thermostat_id'])
                if existing is None:
                    away_temp = 50.0
                    
                    record = ThermostatRecord(
                        thermostat_id=device_data['thermostat_id'],
                        ip_address=device_data['ip'],
                        name=device_data['name'],
                        model="Unknown",
                        api_version=0,
                        fw_version="Unknown",
                        capabilities={},
                        discovery_method=device_data['discovery_method'],
                        active=True,
                        away_temp=away_temp,
                        last_seen=datetime.now(timezone.utc)
                    )
                    thermostats_to_register.append(record)
                    logger.debug(f"New device {device_data['name']} will get default away_temp {away_temp}F")
                else:
                    logger.debug(f"Existing device {device_data['name']} found - skipping registration")
            
            if thermostats_to_register and self.public_sync:
                registration_success = await self.public_sync.register_thermostats(thermostats_to_register)
                
                result.discovery_results['registration_results'] = {
                    "local_registration_success": True,
                    "public_server_registration_success": registration_success,
                    "devices_registered": len(thermostats_to_register),
                    "registration_errors": [] if registration_success else ["Public server registration failed"]
                }
            else:
                result.discovery_results['registration_results'] = {
                    "local_registration_success": True,
                    "public_server_registration_success": False,
                    "devices_registered": 0,
                    "registration_errors": ["No new devices to register"]
                }
                
        except Exception as e:
            logger.error(f"Device registration failed: {e}")
            result.discovery_results['registration_results'] = {
                "local_registration_success": False,
                "public_server_registration_success": False,
                "devices_registered": 0,
                "registration_errors": [str(e)]
            }
    
    async def _update_progress(self, command_id: str, status: DiscoveryStatus):
        """Update and broadcast discovery progress with phase_history"""
        
        # Create progress object with phase_history
        progress = DiscoveryProgress(
            command_id=command_id,
            status=status,
            execution_time_seconds=self._get_total_execution_time(),
            phase_history=self.phase_history.copy(),  # Send complete phase history
            timestamp=datetime.now(timezone.utc)
        )
        
        self.last_progress = progress
        
        # Call all progress callbacks
        for callback in self.progress_callbacks:
            try:
                await callback(progress)
            except Exception as e:
                logger.error(f"Progress callback failed: {e}")
        
        # Log summary
        current_phase = next((p for p in self.phase_history if p["status"] == "inprogress"), None)
        if current_phase:
            logger.debug(
                f"Discovery progress - {current_phase['phase']}: "
                f"{current_phase['devices_found']} devices - "
                f"{current_phase['current_action']} "
                f"(phase: {current_phase['elapsed_time']:.1f}s, total: {self._get_total_execution_time():.1f}s)"
            )
    
    def get_current_progress(self) -> Optional[DiscoveryProgress]:
        """Get current discovery progress"""
        return self.last_progress
    
    def is_discovery_active(self) -> bool:
        """Check if discovery is currently active"""
        return self.active_discovery is not None
    
    async def cancel_discovery(self, command_id: str) -> bool:
        """Cancel active discovery (if supported)"""
        if not self.active_discovery or self.active_discovery['command_id'] != command_id:
            return False
        
        # Mark all waiting phases as skipped
        for phase in self.phase_history:
            if phase["status"] == "waiting":
                phase["status"] = "skipped"
        
        await self._update_progress(
            command_id=command_id,
            status=DiscoveryStatus.CANCELLED
        )
        
        self.active_discovery = None
        return True
