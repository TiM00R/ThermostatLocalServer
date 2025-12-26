"""
Thermostat Server - Main orchestrator for all services
"""

import asyncio
import signal
import sys
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import uvicorn
from contextlib import asynccontextmanager

# Local imports 
from config_loader import load_config, setup_logging
from database.manager import DatabaseManager
from database.models import ThermostatRecord, StatusRecord
from discovery.manager import ThermostatDiscovery
from api.main_api import ThermostatAPI
from public_sync.sync_manager import EnhancedPublicServerSync
from weather_service import WeatherService
from http_helper import create_thermostat_session
from apply_initial_config import DeviceConfigManager

logger = logging.getLogger(__name__)

class ThermostatServer:
    """Main server orchestrating all thermostat services with enhanced progressive discovery + remote commands + state change detection"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        setup_logging(self.config)
        
        self.db = DatabaseManager(self.config)
        # Pass database manager to discovery for progressive discovery
        self.discovery = ThermostatDiscovery(self.config['network'], self.db)
        # REMOVED: ThermostatPoller - functionality moved to _polling_service method
        
        # Weather service for local temperature
        self.weather = WeatherService(self.config)
        
        # Device configuration manager
        self.device_config_manager = DeviceConfigManager(self.db, self.config)

        # Updated API with weather service reference
        self.api = ThermostatAPI(self.db, self.config, self.weather)
        
        # Enhanced public server sync with discovery command support
        self.public_sync = EnhancedPublicServerSync(self.config, self.db, self.discovery)
        
        self.running = False
        self.tasks = []
        
        # State change detection cache
        self._last_states = {}
        self._state_change_stats = {
            'total_polls': 0,
            'state_changes_detected': 0,
            'immediate_uploads': 0
        }
        
    async def start(self):
        """Start all server services with enhanced progressive discovery + remote commands + state change detection"""
        logger.info("Starting RadioThermostat CT50 Local Server with State Change Detection...")
        
        try:
            # Initialize database
            await self.db.initialize()
            logger.info("Database initialized successfully")
            
            # Start weather service
            await self.weather.start()
            logger.info("Weather service initialized")
            
            # Start public server sync service (includes discovery command handler)
            await self.public_sync.start()
            logger.info("Enhanced public server sync with discovery commands initialized")
            
            # NEW: Enhanced progressive discovery AND REGISTRATION
            await self._enhanced_discovery_and_registration()
            
            self.running = True
            
            # Start background services (including weather updates)
            self.tasks = [
                asyncio.create_task(self._discovery_service()),
                asyncio.create_task(self._polling_service()),
                asyncio.create_task(self._rollup_service()),
                asyncio.create_task(self._monitoring_service()),
                asyncio.create_task(self._weather_service())
            ]
            
            # Add public server sync tasks (includes discovery progress reporting)
            sync_tasks = await self.public_sync.get_sync_tasks()
            self.tasks.extend(sync_tasks)
            
            logger.info(f"All services started successfully ({len(self.tasks)} background tasks)")
            logger.info("[SEARCH] Remote discovery commands now available via public server")
            logger.info("State change detection enabled - manual changes will be detected within 5 seconds")
            
            # Start HTTP API server
            await self._start_api_server()
            
        except Exception as e:
            logger.error(f"Server startup failed: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop all server services gracefully"""
        logger.info("Stopping server...")
        self.running = False
        
        # Log state change statistics
        stats = self._state_change_stats
        if stats['total_polls'] > 0:
            change_rate = (stats['state_changes_detected'] / stats['total_polls']) * 100
            logger.info(f"State change detection stats: {stats['state_changes_detected']} changes detected "
                       f"in {stats['total_polls']} polls ({change_rate:.1f}% change rate), "
                       f"{stats['immediate_uploads']} immediate uploads")
        
        # Stop services in order
        await self.weather.stop()
        await self.public_sync.stop()
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Close database connections
        await self.db.close()
        logger.info("Server stopped")
    
    # ================== NEW ENHANCED PROGRESSIVE DISCOVERY (UNCHANGED) ==================
    
    async def _enhanced_discovery_and_registration(self):
        """
        NEW: Enhanced progressive discovery with fast startup and intelligent fallback
        """
        logger.info("[LAUNCH] Starting enhanced progressive discovery...")
        overall_start = datetime.now()
        
        # Phase 1: Fast startup discovery (DB + UDP)
        devices, should_continue_to_tcp = await self.discovery.discover_combined_startup()
        
        # Register all devices found in Phase 1 if any
        if devices:
            await self._register_and_configure_devices(devices, "startup_phase")
            
            # Start background TCP discovery for additional devices
            # DEBUG: Enable background TCP discovery only if configured
            value = (
            self.config.get('network', {})
                .get('progressive_discovery', {})
                .get('tcp_discovery', {})
                .get('enable_background_tcp_discovery', True)
            )
            if value:
                tcp_task = asyncio.create_task(self._background_tcp_discovery())
                self.tasks.append(tcp_task)
                logger.info("Background TCP discovery started for additional devices")
        
        # Phase 2: Blocking TCP discovery (only if zero devices found)
        elif should_continue_to_tcp:
            logger.warning("No devices found in startup phase - running blocking TCP discovery...")
            await self._blocking_tcp_discovery()
        
        # Report overall timing
        startup_duration = (datetime.now() - overall_start).total_seconds()
        device_count = len(await self.db.get_active_thermostats())
        logger.info(f"[SUCCESS] Enhanced discovery complete: {device_count} devices ready in {startup_duration:.1f}s")
        
        if device_count > 0:
            logger.info("[FEATURE] Remote discovery commands are now available via public server")
    
    async def _register_and_configure_devices(self, devices: List, phase_name: str = "discovery"):
        """
        Register devices and apply INTELLIGENT CONFIGURATION with debug outputs
        UPDATED: Read thermostat settings first, then apply intelligent hold-based logic
        """
        if not devices:
            return
        
        logger.info(f"[LOG] Registering {len(devices)} devices from {phase_name} with intelligent configuration...")
        
        # Map phase names to discovery types for configuration logic
        discovery_type_map = {
            "startup_phase": "startup",
            "tcp_first_batch": "startup", 
            "periodic_discovery": "periodic",
            "background_tcp": "periodic",
            "tcp_additional": "periodic",
            "discovery": "startup"  # Default
        }
        discovery_type = discovery_type_map.get(phase_name, "startup")
        
        # Register devices in LOCAL database
        registered_thermostats = []
        for device in devices:
            try:
                logger.info(f"[DEVICE] Processing {device.name} ({device.ip}) - discovery_type: {discovery_type}")
                
                # Step 1: Check for existing device to preserve away_temp
                existing_device = await self.db.get_thermostat_by_id(device.uuid)
                
                # Preserve existing away_temp or use default for new devices
                away_temp = 50.0  # Default for new devices
                if existing_device and existing_device.away_temp is not None:
                    away_temp = existing_device.away_temp
                    logger.debug(f"[AWAY_TEMP] Preserving away_temp {away_temp}°F for existing device {device.name}")
                else:
                    logger.debug(f"[AWAY_TEMP] Using default away_temp {away_temp}°F for {'new' if not existing_device else 'existing null'} device {device.name}")
                
                # Step 2: Create database record
                db_record = ThermostatRecord(
                    thermostat_id=device.uuid,
                    ip_address=device.ip,
                    name=device.name,
                    model=device.model,
                    api_version=device.api_version,
                    fw_version=device.fw_version,
                    capabilities={},
                    discovery_method=device.discovery_method,
                    active=True,
                    away_temp=away_temp,
                    last_seen=datetime.now(timezone.utc)
                )
                
                # Step 3: Register in database
                success = await self.db.upsert_thermostat(db_record)
                if success:
                    logger.info(f"[DB] Registered locally: {device.name} ({device.ip}) via {device.discovery_method}")
                    registered_thermostats.append(db_record)
                    
                    # Step 4: NEW INTELLIGENT CONFIGURATION APPROACH
                    logger.info(f"[CONFIG] Starting intelligent configuration for {device.name}...")
                    
                    # Read thermostat current settings FIRST
                    current_settings = await self.device_config_manager.read_thermostat_current_settings(device.ip)
                    
                    if current_settings:
                        logger.info(f"[READ] Current thermostat settings for {device.name}: {current_settings}")
                        
                        # Apply intelligent configuration based on hold status and discovery type
                        await self.device_config_manager.apply_intelligent_config(
                            device, current_settings, discovery_type
                        )
                        
                    else:
                        logger.warning(f"[READ] Failed to read settings from {device.name} - using fallback config")
                        # Fallback to legacy method if can't read settings
                        await self.device_config_manager.apply_intelligent_config(
                            device, None, discovery_type
                        )
                        
                    logger.info(f"[CONFIG] Completed intelligent configuration for {device.name}")
                    
                else:
                    logger.error(f"[ERROR] Failed to register locally: {device.name}")
                    
            except Exception as e:
                logger.error(f"[ERROR] Failed to process device {device.name}: {e}")
                continue
        
        # Register devices with PUBLIC SERVER in one batch
        if registered_thermostats and self.public_sync and self.config['public_server'].get('enabled', False):
            logger.info(f"[NETWORK] Registering {len(registered_thermostats)} devices with public server...")
            registration_success = await self.public_sync.register_thermostats(registered_thermostats)
            
            if registration_success:
                logger.info(f"[PASS] Public server registration successful for {len(registered_thermostats)} devices")
                logger.info("[SEARCH] Devices are now available for remote discovery commands")
            else:
                logger.warning(f"[WARNING] Public server registration failed for {len(registered_thermostats)} devices")
        elif not self.config['public_server'].get('enabled', False):
            logger.info("[LOCAL] Local-only mode - skipping public server registration")
        
        logger.info(f"[COMPLETE] Finished processing {len(devices)} devices from {phase_name}")
    
    async def _background_tcp_discovery(self):
        """
        Background TCP discovery to find additional devices after startup
        """
        logger.info("[SEARCH] Starting background TCP discovery...")
        
        try:
            async def tcp_batch_callback(batch_devices):
                """Callback to register each TCP batch as it's found"""
                await self._register_and_configure_devices(batch_devices, "background_tcp")
            
            # Run TCP discovery with batch registration
            batch_results = await self.discovery.discover_tcp_batched(callback=tcp_batch_callback)
            
            total_tcp_devices = sum(len(result.devices) for result in batch_results)
            if total_tcp_devices > 0:
                logger.info(f"[TARGET] Background TCP discovery complete: {total_tcp_devices} additional devices found")
            else:
                logger.info("Background TCP discovery complete: no additional devices found")
                
        except Exception as e:
            logger.error(f"Background TCP discovery failed: {e}")
    
    async def _blocking_tcp_discovery(self):
        """
        Blocking TCP discovery when no devices found in startup phase
        """
        logger.info("[SEARCH] Running blocking TCP discovery (no devices found in startup)...")
        
        try:
            first_batch_found = False
            
            async def blocking_tcp_callback(batch_devices):
                """Callback to register first batch and switch to background mode"""
                nonlocal first_batch_found
                
                if not first_batch_found:
                    # Register first batch and start normal operations
                    await self._register_and_configure_devices(batch_devices, "tcp_first_batch")
                    first_batch_found = True
                    logger.info(f"[SUCCESS] First TCP batch found: {len(batch_devices)} devices - starting normal operations")
                else:
                    # Register additional batches in background
                    await self._register_and_configure_devices(batch_devices, "tcp_additional")
            
            # Run TCP discovery - this will be blocking until first batch found
            batch_results = await self.discovery.discover_tcp_batched(callback=blocking_tcp_callback)
            
            if not first_batch_found:
                logger.warning("[WARNING] TCP discovery completed but no devices found")
            else:
                total_devices = sum(len(result.devices) for result in batch_results)
                logger.info(f"[PASS] Blocking TCP discovery complete: {total_devices} total devices found")
                
        except Exception as e:
            logger.error(f"Blocking TCP discovery failed: {e}")
    
    # ================== UPDATED PERIODIC DISCOVERY (UNCHANGED) ==================
    
    async def _discovery_service(self):
        """
        Background service for periodic device discovery - UPDATED for progressive discovery
        """
        scan_interval = self.config['network']['scan_interval_minutes'] * 60
        
        logger.info(f"Discovery service started (every {scan_interval/60} minutes)")
        
        while self.running:
            try:
                await asyncio.sleep(scan_interval)
                if not self.running:
                    break
                
                logger.info("[REFRESH] Running periodic discovery...")
                
                # Use progressive discovery for periodic scans too
                devices, should_continue = await self.discovery.discover_combined_startup()
                
                if devices:
                    # Track new devices
                    new_devices = []
                    updated_devices = 0
                    
                    for device in devices:
                        # Check if this is a new device
                        existing = await self.db.get_thermostat_by_id(device.uuid)
                        if existing is None:
                            new_devices.append(device)
                        else:
                            updated_devices += 1
                    
                    # Register only NEW devices
                    if new_devices:
                        await self._register_and_configure_devices(new_devices, "periodic_discovery")
                    
                    if updated_devices > 0:
                        logger.debug(f"Updated {updated_devices} existing devices")
                
                # Background TCP scan for additional devices (if enabled)
                if should_continue and self.config['network'].get('enable_periodic_tcp', False):
                    logger.info("Running background TCP scan for additional devices...")
                    await self._background_tcp_discovery()
                
            except Exception as e:
                logger.error(f"Discovery service error: {e}")
    
    # ================== WEATHER SERVICE (UNCHANGED) ==================
   
    async def _weather_service(self):
        """Background service for periodic weather updates"""
        if not self.weather.enabled:
            logger.info("Weather service disabled")
            return
        
        update_interval = self.weather.update_interval
        logger.info(f"Weather service started (every {update_interval//60} minutes)")
        
        while self.running:
            try:
                await asyncio.sleep(update_interval)
                if not self.running:
                    break
                
                # Update weather data
                await self.weather.update_temperature()
                
                # Log weather status periodically (every hour)
                current_hour = datetime.now().hour
                if current_hour % 1 == 0:  # Every hour
                    weather_status = self.weather.get_status()
                    if weather_status['current_temp']:
                        logger.info(f"Weather service: {weather_status['current_temp']:.1f}°F outside (zip: {weather_status['zip_code']})")
                
            except Exception as e:
                logger.error(f"Weather service error: {e}")
    
    # ================== ENHANCED POLLING SERVICE WITH STATE CHANGE DETECTION ==================
    
    async def _polling_service(self):
        """Background service for continuous status polling - ENHANCED: With state change detection"""
        import time
        
        poll_interval = self.config['polling']['status_interval_seconds']  # 5 seconds
        max_work_time_warning = poll_interval * 0.8  # Warn if work takes >80% of interval
        
        logger.info(f"Status polling service started with state change detection (true {poll_interval}s intervals)")
        
        while self.running:
            cycle_start_time = time.time()
            
            try:
                # Get active thermostats from database
                thermostats = await self.db.get_active_thermostats()
                
                if not thermostats:
                    logger.warning("No active thermostats found")
                    # Still respect timing even when no work to do
                    elapsed_time = time.time() - cycle_start_time
                    remaining_time = max(0, poll_interval - elapsed_time)
                    await asyncio.sleep(remaining_time)
                    continue
                
                # Get current local weather temperature
                local_temp = await self.weather.get_current_temperature()
                
                # Poll all thermostats
                ip_list = [t.ip_address for t in thermostats]
                
                # Create device lookup for IP -> thermostat_id mapping
                device_map = {t.ip_address: t.thermostat_id for t in thermostats}
                
                # Do the actual polling work with state change detection
                await self._poll_and_store(ip_list, device_map, local_temp)
                
                # Calculate timing for next cycle
                elapsed_time = time.time() - cycle_start_time
                remaining_time = poll_interval - elapsed_time
                
                # PILE-UP PREVENTION: Check if work took too long
                if elapsed_time > poll_interval:
                    logger.warning(
                        f"Polling cycle took {elapsed_time:.1f}s (>{poll_interval}s configured) - "
                        f"skipping sleep to prevent pile-up. Consider increasing poll_interval."
                    )
                    # Don't sleep - start next cycle immediately to prevent pile-up
                    continue
                
                # PERFORMANCE WARNING: Check if work is taking too long
                elif elapsed_time > max_work_time_warning:
                    logger.warning(
                        f"Polling cycle took {elapsed_time:.1f}s (>{max_work_time_warning:.1f}s recommended) - "
                        f"only {remaining_time:.1f}s remaining for {poll_interval}s interval"
                    )
                
                # DEBUG: Log timing and state change stats occasionally (every 60 cycles = ~5 minutes)
                cycle_count = getattr(self, '_polling_cycle_count', 0) + 1
                self._polling_cycle_count = cycle_count
                
                if cycle_count % 60 == 0:
                    stats = self._state_change_stats
                    change_rate = (stats['state_changes_detected'] / max(stats['total_polls'], 1)) * 100
                    logger.debug(
                        f"Polling performance: work={elapsed_time:.1f}s, sleep={remaining_time:.1f}s, "
                        f"total={poll_interval}s (cycle #{cycle_count}) | "
                        f"State changes: {stats['state_changes_detected']}/{stats['total_polls']} ({change_rate:.1f}%)"
                    )
                
                # Sleep for remaining time to maintain exact interval
                await asyncio.sleep(remaining_time)
                
            except Exception as e:
                elapsed_time = time.time() - cycle_start_time
                remaining_time = max(0, poll_interval - elapsed_time)
                
                logger.error(f"Polling service error: {e}")
                logger.debug(f"Error occurred after {elapsed_time:.1f}s, sleeping {remaining_time:.1f}s")
                
                # Even on error, respect timing to prevent rapid error loops
                await asyncio.sleep(remaining_time)
    
    async def _poll_and_store(self, ip_list: List[str], device_map: Dict[str, str], local_temp: Optional[float]):
        """Poll thermostats and store results in database - includes local weather and state change detection"""
        tasks = []
        
        for ip in ip_list:
            task = self._poll_single_and_store(ip, device_map[ip], local_temp)
            tasks.append(task)
        
        # Execute all polls concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # ================== ENHANCED POLLING WITH STATE CHANGE DETECTION ==================
    
    async def _poll_single_and_store(self, ip: str, thermostat_id: str, local_temp: Optional[float]):
        """
        Poll single thermostat and store in database. With state change detection and immediate uploads
        Updates last_seen after successful poll
        Detects state changes and triggers immediate upload to public server
        """
        try:
            async with create_thermostat_session(5) as session:
                async with session.get(f"http://{ip}/tstat") as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Create status record with local weather temperature
                        current_status = StatusRecord(
                            thermostat_id=thermostat_id,
                            ts=datetime.now(timezone.utc),
                            temp=float(data.get('temp', -1)),
                            t_heat=float(data.get('t_heat', -1)),
                            tmode=int(data.get('tmode', -1)),
                            tstate=int(data.get('tstate', -1)),
                            hold=int(data.get('hold', 0)),
                            override=int(data.get('override', 0)),
                            ip_address=ip,
                            local_temp=local_temp,
                            last_error=None
                        )
                        
                        # Update statistics
                        self._state_change_stats['total_polls'] += 1
                        
                        # NEW: Check for state changes compared to previous reading
                        state_changed, change_type, changed_fields = self._detect_state_change(thermostat_id, current_status)
                        
                        # Always save to local database
                        await self.db.save_status_reading(current_status)
                        
                        # Always update last_seen timestamp after successful poll
                        await self.db.update_thermostat_last_seen(thermostat_id)
                        
                        # NEW: If state changed, immediately upload to public server
                        if state_changed:
                            self._state_change_stats['state_changes_detected'] += 1
                            self._state_change_stats['immediate_uploads'] += 1
                            
                            logger.info(f"State change detected on {thermostat_id}: {change_type}")
                            if changed_fields:
                                field_changes = ", ".join([f"{field}: {info['from']}→{info['to']}" 
                                                         for field, info in changed_fields.items()])
                                logger.debug(f"   Changed fields: {field_changes}")
                            
                            # Create upload data for immediate transmission
                            upload_data = self._create_upload_data(current_status, ip, local_temp)
                            
                            # Queue immediate upload to public server
                            if self.public_sync and self.config['public_server'].get('enabled', False):
                                await self.public_sync.queue_immediate_update([upload_data])
                                logger.debug(f"   Immediate upload queued for {thermostat_id}")
                        
                        # Update our state cache for next comparison
                        self._update_state_cache(thermostat_id, current_status)
                        
                        # Print enhanced status with weather comparison (existing functionality)
                        time_data = data.get('time', {})
                        time_str = f"{time_data.get('day', -1)}:{time_data.get('hour', -1):02d}:{time_data.get('minute', -1):02d}"
                        tmode_desc = {0: "OFF", 1: "HEAT", 2: "COOL", 3: "AUTO"}.get(current_status.tmode, f"UNK({current_status.tmode})")
                        tstate_desc = {0: "OFF", 1: "HEAT", 2: "COOL"}.get(current_status.tstate, f"UNK({current_status.tstate})")
                        
                        # Enhanced output with weather comparison
                        weather_info = ""
                        if local_temp is not None:
                            temp_diff = current_status.temp - local_temp
                            weather_info = f" | outside={local_temp:.1f}°F (Δ{temp_diff:+.1f}°F)"
                        
                        # Add state change indicator to output
                        # Debug T.S.: Show change type if state changed
                        change_indicator = f" |  {change_type}" if state_changed else ""
                        
                        print(f"{ip} | temp={current_status.temp}°F t_heat={current_status.t_heat}°F  hold={'on' if current_status.hold else 'off'} " + 
                              f"tmode={tmode_desc} tstate={tstate_desc} time={time_str}{weather_info}{change_indicator}")

        except Exception as e:
            logger.debug(f"Poll failed for {ip}: {e}")
    
    def _detect_state_change(self, thermostat_id: str, current_status: StatusRecord) -> tuple[bool, str, Optional[Dict]]:
        """
        Detect state changes by comparing current reading with previous reading
        Returns: (state_changed: bool, change_type: str, changed_fields: Dict)
        """
        previous_status = self._last_states.get(thermostat_id)
        
        # First reading for this thermostat - don't trigger immediate upload
        if previous_status is None:
            return False, "first_reading", None
        
        # Check for significant changes
        changed_fields = {}
        significant_change = False
        
        # Temperature change >= 0.5°F (to avoid minor fluctuations)
        if abs(current_status.temp - previous_status.temp) >= 0.5:
            changed_fields['temp'] = {
                'from': previous_status.temp, 
                'to': current_status.temp
            }
            significant_change = True
        
        # Setpoint (t_heat) change
        if current_status.t_heat != previous_status.t_heat:
            changed_fields['t_heat'] = {
                'from': previous_status.t_heat, 
                'to': current_status.t_heat
            }
            significant_change = True
        
        # Mode (tmode) change
        if current_status.tmode != previous_status.tmode:
            changed_fields['tmode'] = {
                'from': previous_status.tmode, 
                'to': current_status.tmode
            }
            significant_change = True
        
        # HVAC state (tstate) change
        if current_status.tstate != previous_status.tstate:
            changed_fields['tstate'] = {
                'from': previous_status.tstate, 
                'to': current_status.tstate
            }
            significant_change = True
        
        # Hold status change
        if current_status.hold != previous_status.hold:
            changed_fields['hold'] = {
                'from': previous_status.hold, 
                'to': current_status.hold
            }
            significant_change = True
        
        # Override status change
        if current_status.override != previous_status.override:
            changed_fields['override'] = {
                'from': previous_status.override, 
                'to': current_status.override
            }
            significant_change = True
        
        if not significant_change:
            return False, "no_change", None
        
        # Classify the type of change for better logging
        change_type = self._classify_change_type(changed_fields)
        
        return True, change_type, changed_fields
    
    def _classify_change_type(self, changed_fields: Dict) -> str:
        """Classify the type of state change for logging purposes"""
        if 'tmode' in changed_fields or 't_heat' in changed_fields or 'hold' in changed_fields:
            return "manual_adjustment"
        elif 'tstate' in changed_fields:
            return "hvac_state_change"
        elif 'temp' in changed_fields:
            return "temperature_change"
        elif 'override' in changed_fields:
            return "override_change"
        else:
            return "other_change"
    
    def _update_state_cache(self, thermostat_id: str, status: StatusRecord):
        """Update our local cache with the current status for future comparisons"""
        self._last_states[thermostat_id] = status
    
    def _create_upload_data(self, status: StatusRecord, ip: str, local_temp: Optional[float]) -> Dict:
        """Create upload data dictionary for public server transmission"""
        return {
            "thermostat_id": status.thermostat_id,
            "ip_address": ip,
            "temp": status.temp,
            "t_heat": status.t_heat,
            "tmode": status.tmode,
            "tstate": status.tstate,
            "hold": status.hold,
            "override": status.override,
            "last_poll_success": True,
            "last_error": None,
            "local_temp": local_temp
        }
    
    # ================== REMAINING SERVICES (UNCHANGED) ==================
    
    async def _rollup_service(self):
        """Background service for minute aggregations"""
        logger.info("Rollup service started")
        
        while self.running:
            try:
                # Wait until the next minute boundary
                now = datetime.now(timezone.utc)
                next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                wait_seconds = (next_minute - now).total_seconds()
                
                await asyncio.sleep(wait_seconds)
                
                if not self.running:
                    break
                
                # Create aggregation for the previous minute
                end_time = now.replace(second=0, microsecond=0)
                start_time = end_time - timedelta(minutes=1)
                
                await self.db.create_minute_aggregation(start_time, end_time)
                logger.info(
                    "minute aggregation | start_time=%s | end_time=%s | duration=%s",
                    start_time.strftime('%H:%M:%S'),
                    end_time.strftime('%H:%M:%S'),
                    str(end_time - start_time).split('.')[0],  # strip microseconds
                )
                logger.debug(f"Created minute aggregation for {start_time.strftime('%H:%M')}")
                
                # Cleanup old data (daily at 2 AM)
                if now.hour == 2 and now.minute == 0:
                    await self.db.cleanup_old_data()
                
            except Exception as e:
                logger.error(f"Rollup service error: {e}")
    
    async def _monitoring_service(self):
        """Background service for system health monitoring - includes weather status and state change stats"""
        check_interval = self.config['monitoring']['health_check_interval_minutes'] * 60
        
        logger.info(f"Monitoring service started (every {check_interval/60} minutes)")
        
        while self.running:
            try:
                await asyncio.sleep(check_interval)
                
                if not self.running:
                    break
                
                # Check device health
                thermostats = await self.db.get_active_thermostats()
                current_status = await self.db.get_current_status()
                
                # Check weather service health
                weather_status = self.weather.get_status()
                weather_health = "OK" if weather_status['current_temp'] is not None else "ERROR"
                
                # NEW: Check discovery command handler health
                discovery_health = "N/A"
                if self.public_sync and self.public_sync.discovery_handler:
                    discovery_health = "ACTIVE" if self.public_sync.discovery_handler.is_discovery_active() else "READY"
                
                # NEW: Report state change detection statistics
                stats = self._state_change_stats
                change_rate = (stats['state_changes_detected'] / max(stats['total_polls'], 1)) * 100
                
                logger.info(f"Health check: {len(thermostats)} devices, {len(current_status)} with recent status, "
                           f"weather: {weather_health}, discovery: {discovery_health} | "
                           f"State changes: {stats['state_changes_detected']}/{stats['total_polls']} ({change_rate:.1f}%)")
                
                # Check for thermostats that haven't been seen recently
                cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=10)
                offline_count = 0
                
                for thermostat in thermostats:
                    if thermostat.last_seen and thermostat.last_seen < cutoff_time:
                        offline_count += 1
                        logger.warning(f"Thermostat {thermostat.name} hasn't been seen since {thermostat.last_seen}")
                
                if offline_count > 0:
                    logger.warning(f"{offline_count} thermostat(s) appear to be offline")
                
                # Report weather service issues
                if weather_status['error_count'] > 0:
                    logger.warning(f"Weather service has {weather_status['error_count']} errors, last: {weather_status['last_error']}")
                
            except Exception as e:
                logger.error(f"Monitoring service error: {e}")
    
    async def _start_api_server(self):
        """Start the FastAPI server"""
        config = uvicorn.Config(
            self.api.app,
            host=self.config['api']['host'],
            port=self.config['api']['port'],
            log_level="info",
            access_log=False  # We handle our own logging
        )
        
        server = uvicorn.Server(config)
        
        logger.info(f"Starting API server on {self.config['api']['host']}:{self.config['api']['port']}")
        logger.info(f"API documentation: http://localhost:{self.config['api']['port']}/docs")
        
        # Log weather service status
        if self.weather.enabled:
            logger.info(f"Weather integration enabled for zip code {self.weather.zip_code}")
        else:
            logger.info("Weather integration disabled")
        
        if self.config['public_server']['enabled']:
            logger.info("Public server sync enabled - uploading data to cloud")
            logger.info("Thermostats will be automatically registered with public server")
            logger.info("[SEARCH] Remote discovery commands available via public server API")
        else:
            logger.info("Local-only mode - public server sync disabled")
        
        await server.serve()
