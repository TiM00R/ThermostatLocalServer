"""
Device Initial Configuration Manager - UPDATED WITH INTELLIGENT DISCOVERY STRATEGY
Implements read-first discovery with hold-based decision logic and debug outputs
"""

import logging
from datetime import datetime, timezone, date
from typing import Dict, Optional
from http_helper import create_thermostat_session

logger = logging.getLogger(__name__)

class DeviceConfigManager:
    """Manages thermostat intelligent configuration with hold-based logic"""
    
    def __init__(self, database_manager, config: Dict):
        self.db = database_manager
        self.config = config

    # ================== NEW INTELLIGENT DISCOVERY STRATEGY ==================
        
    async def read_thermostat_current_settings(self, device_ip: str) -> Optional[Dict]:
        """Read current thermostat settings before applying any configuration"""
        try:
            async with create_thermostat_session(10) as session:
                response = await session.get(f"http://{device_ip}/tstat")
                if response.status == 200:
                    data = await response.json()
                    current_settings = {
                        'tmode': data.get('tmode'),
                        't_heat': data.get('t_heat'), 
                        't_cool': data.get('t_cool'),  # Read but never set
                        'hold': data.get('hold')
                    }
                    logger.info(f"[READ] Current thermostat settings from {device_ip}: {current_settings}")
                    return current_settings
                else:
                    logger.warning(f"Failed to read settings from {device_ip}: HTTP {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error reading thermostat settings from {device_ip}: {e}")
            return None

    async def apply_initial_settings(self, device_ip: str) -> bool:
        """Apply settings we always maintain regardless of other logic"""
        initial_settings = {
            'fmode': 0  # Always keep fan OFF
            # Future: Add other settings we want to maintain always
        }
        
        try:
            async with create_thermostat_session(10) as session:
                response = await session.post(f"http://{device_ip}/tstat", json=initial_settings)
                if response.status == 200:
                    logger.info(f"[INITIAL] Applied initial settings to {device_ip}: {initial_settings}")
                    return True
                else:
                    logger.warning(f"Failed to apply initial settings to {device_ip}: HTTP {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Error applying initial settings to {device_ip}: {e}")
            return False

    async def apply_intelligent_config(self, device, current_settings: Optional[Dict] = None, discovery_type: str = "startup"):
        """
        MAIN ENTRY POINT: Apply configuration based on hold status and discovery context
        """
        try:
            logger.info(f"[DISCOVERY] Starting intelligent config for {device.name} (type: {discovery_type})")
            
            # Step 1: Always apply initial settings first (fmode=0, etc.)
            await self.apply_initial_settings(device.ip)
            
            # Step 2: Read current settings if not provided
            if current_settings is None:
                current_settings = await self.read_thermostat_current_settings(device.ip)
            
            # Step 3: Fallback if can't read thermostat
            if current_settings is None:
                logger.warning(f"[FALLBACK] Cannot read thermostat {device.name} - applying seasonal defaults")
                await self._apply_seasonal_safety_config(device)
                return
            
            # Step 4: Intelligent decision based on hold status
            if current_settings.get('hold') == 0:
                # Hold disabled: Apply seasonal defaults AND set hold=1
                logger.info(f"[HOLD=0] {device.name} hold disabled - applying seasonal defaults with hold=1")
                await self._apply_seasonal_defaults_with_hold(device, current_settings)
            else:
                # Hold enabled: Always preserve thermostat settings, update DB
                if discovery_type == "startup" and self._is_unsafe_setting(current_settings):
                    logger.warning(f"[UNSAFE] {device.name} has unsafe setting but respecting hold=1: {current_settings}")
                
                logger.info(f"[HOLD=1] {device.name} hold enabled - preserving thermostat settings")
                await self._update_db_from_thermostat(device.uuid, current_settings)
                
        except Exception as e:
            logger.error(f"Intelligent config failed for {device.name}: {e}")

    async def _apply_seasonal_defaults_with_hold(self, device, current_settings: Dict):
        """Apply seasonal defaults AND set hold=1"""
        try:
            season_config = self._determine_seasonal_config()
            config = season_config['config'].copy()
            config['hold'] = 1  # ALWAYS set hold=1 when applying seasonal defaults
            
            # Validate only OFF/HEAT modes allowed
            if config.get('tmode') not in [0, 1]:
                logger.warning(f"Invalid tmode {config.get('tmode')} - defaulting to OFF")
                config['tmode'] = 0
            
            # Build safe command (no t_cool, validate modes)
            command = self._build_safe_thermostat_command(config)
            
            logger.info(f"[SEASONAL] Applying {season_config['season']} defaults with hold=1 to {device.name}")
            
            # Debug: Show what's changing
            changes = self._detect_setting_changes(current_settings, config)
            if changes:
                logger.info(f"[CHANGE] Thermostat settings changing on {device.name}: {changes}")
            
            async with create_thermostat_session(10) as session:
                response = await session.post(f"http://{device.ip}/tstat", json=command)
                if response.status == 200:
                    logger.info(f"[SUCCESS] Applied seasonal config to {device.name}: {command}")
                    
                    # Update database
                    await self._save_config_to_database(device.uuid, config)
                    logger.info(f"[DB] Updated database with seasonal config for {device.name}")
                else:
                    logger.error(f"[ERROR] Failed to apply seasonal config to {device.name}: HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"Failed to apply seasonal defaults to {device.name}: {e}")

    async def _update_db_from_thermostat(self, thermostat_id: str, current_settings: Dict):
        """Update database with current thermostat settings (preserve thermostat authority)"""
        try:
            # Get current DB settings for comparison
            stored_config = await self._get_stored_device_config(thermostat_id)
            
            # Build config updates for database
            config_updates = {}
            now = datetime.now(timezone.utc)
            
            # Only update fields that are valid and different
            if current_settings.get('tmode') is not None:
                config_updates['tmode_set'] = current_settings['tmode']
                config_updates['tmode_applied_at'] = now
                
            if current_settings.get('t_heat') is not None:
                config_updates['t_heat_set'] = current_settings['t_heat']
                config_updates['t_heat_applied_at'] = now
                
            if current_settings.get('t_cool') is not None:
                config_updates['t_cool_set'] = current_settings['t_cool']
                config_updates['t_cool_applied_at'] = now
                
            if current_settings.get('hold') is not None:
                config_updates['hold_set'] = current_settings['hold']
                config_updates['hold_applied_at'] = now
            
            # Debug: Show what's changing in DB
            if stored_config:
                db_changes = self._detect_db_changes(stored_config, current_settings)
                if db_changes:
                    logger.info(f"[DB CHANGE] Database values changing for {thermostat_id}: {db_changes}")
                else:
                    logger.debug(f"[DB] No database changes needed for {thermostat_id}")
            else:
                logger.info(f"[DB] Creating new database config for {thermostat_id}: {current_settings}")
            
            # Update database
            if config_updates:
                await self.db.update_device_config(thermostat_id, config_updates)
                logger.info(f"[DB] Preserved thermostat settings to database for {thermostat_id}")
            
        except Exception as e:
            logger.error(f"Failed to update DB from thermostat {thermostat_id}: {e}")

    def _detect_setting_changes(self, current_settings: Dict, new_config: Dict) -> Dict:
        """Detect what thermostat settings are changing"""
        changes = {}
        
        for key in ['tmode', 't_heat', 'hold']:
            current_val = current_settings.get(key)
            new_val = new_config.get(key)
            
            if current_val != new_val and new_val is not None:
                changes[key] = {'from': current_val, 'to': new_val}
        
        return changes

    def _detect_db_changes(self, stored_config: Dict, current_settings: Dict) -> Dict:
        """Detect what database values are changing"""
        changes = {}
        
        # Map DB field names to thermostat field names
        field_mapping = {
            'tmode_set': 'tmode',
            't_heat_set': 't_heat',
            't_cool_set': 't_cool',
            'hold_set': 'hold'
        }
        
        for db_field, tstat_field in field_mapping.items():
            stored_val = stored_config.get(tstat_field)  # stored_config uses tstat field names
            current_val = current_settings.get(tstat_field)
            
            if stored_val != current_val and current_val is not None:
                changes[db_field] = {'from': stored_val, 'to': current_val}
        
        return changes

    def _is_unsafe_setting(self, settings: Dict) -> bool:
        """Check if thermostat settings seem unsafe (heating in summer)"""
        try:
            # Only check during startup for warning purposes
            if settings.get('tmode') == 1:  # HEAT mode
                season_config = self._determine_seasonal_config()
                if season_config['season'] == 'cooling':
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking unsafe settings: {e}")
            return False

    # ================== LEGACY COMPATIBILITY METHOD ==================
    
    async def apply_initial_config(self, device):
        """Legacy method - redirects to intelligent config for backward compatibility"""
        logger.info(f"[LEGACY] Redirecting to intelligent config for {device.name}")
        await self.apply_intelligent_config(device, discovery_type="startup")

    # ================== EXISTING METHODS (UPDATED FOR NEW STRATEGY) ==================

    async def _get_stored_device_config(self, thermostat_id: str) -> Optional[Dict]:
        """Get stored device configuration from database"""
        try:
            config_row = await self.db.pool.fetchrow("""
                SELECT tmode_set, t_heat_set, t_cool_set, hold_set
                FROM device_config 
                WHERE thermostat_id = $1 
                AND tmode_set IS NOT NULL
            """, thermostat_id)
            
            if config_row:
                return {
                    'tmode': config_row['tmode_set'],
                    't_heat': config_row['t_heat_set'],
                    't_cool': config_row['t_cool_set'], 
                    'hold': config_row['hold_set']                    
                }
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get stored config for {thermostat_id}: {e}")
            return None

    async def _apply_seasonal_safety_config(self, device):
        """Apply seasonal safety defaults based on current date (fallback method)"""
        try:
            season_config = self._determine_seasonal_config()
            season = season_config['season']
            safety_config = season_config['config'].copy()
            safety_config['hold'] = 1  # Always set hold=1 for safety configs
            
            logger.info(f"[FALLBACK] Applying {season} season safety config to {device.name}: {safety_config}")
            
            # Build safe command
            command = self._build_safe_thermostat_command(safety_config)
            
            async with create_thermostat_session(10) as session:
                response = await session.post(f"http://{device.ip}/tstat", json=command)
                
                if response.status == 200:
                    logger.info(f"[SUCCESS] Applied {season} safety config to {device.name}")
                    await self._save_config_to_database(device.uuid, safety_config)
                else:
                    logger.warning(f"[ERROR] Failed to apply safety config to {device.name}: HTTP {response.status}")
                
                # Always sync time
                await self._sync_thermostat_time(device, session)
                
        except Exception as e:
            logger.error(f"Failed to apply seasonal safety config to {device.name}: {e}")

    def _determine_seasonal_config(self) -> Dict:
        """Determine seasonal configuration - ONLY OFF/HEAT modes allowed"""
        today = date.today()
        current_year = today.year
        
        # Define seasonal boundaries
        heating_season_start = date(current_year, 11, 16)  # Nov 16
        cooling_season_start = date(current_year, 4, 15)   # Apr 15
        
        # Handle year boundary for heating season
        if today >= heating_season_start or today <= date(current_year, 4, 14):
            # Heating season (Nov 16 - Apr 14)
            return {
                'season': 'heating',
                'config': {
                    'tmode': 1,    # HEAT mode
                    't_heat': 50,  # 50°F safety temperature
                    'fmode': 0     # Fan OFF
                }
            }
        else:
            # Cooling season (Apr 15 - Nov 15) - NEVER SET COOL MODE
            return {
                'season': 'cooling',
                'config': {
                    'tmode': 0,    # OFF mode only
                    'fmode': 0     # Fan OFF  
                }
            }

    def _build_safe_thermostat_command(self, config: Dict) -> Dict:
        """Build safe thermostat command - ONLY OFF/HEAT modes, never set t_cool"""
        command = {}
        
        # Validate and include tmode (only OFF/HEAT allowed)
        if 'tmode' in config and config['tmode'] is not None:
            if config['tmode'] in [0, 1]:  # Only OFF or HEAT allowed
                command['tmode'] = config['tmode']
            else:
                logger.warning(f"Invalid tmode {config['tmode']} - using OFF mode")
                command['tmode'] = 0
        
        # CRITICAL: Only include t_heat if in HEAT mode
        if command.get('tmode') == 1 and 't_heat' in config and config['t_heat'] is not None:
            command['t_heat'] = config['t_heat']
        
        # NEVER SET t_cool (would trigger COOL mode)
        
        # These are always safe to include
        for key in ['hold', 'fmode']:
            if key in config and config[key] is not None:
                command[key] = config[key]
        
        return command

    async def _save_config_to_database(self, thermostat_id: str, config: Dict):
        """Save applied configuration to database"""
        try:
            config_updates = {}
            now = datetime.now(timezone.utc)
            
            # Build config updates one by one
            if 'tmode' in config and config['tmode'] is not None:
                config_updates['tmode_set'] = config['tmode']
                config_updates['tmode_applied_at'] = now
                
            if 't_heat' in config and config['t_heat'] is not None:
                config_updates['t_heat_set'] = config['t_heat']
                config_updates['t_heat_applied_at'] = now
                
            # Note: We read t_cool but never save it from our configs
            # (it's only saved when preserving existing thermostat settings)
                
            if 'hold' in config and config['hold'] is not None:
                config_updates['hold_set'] = config['hold']
                config_updates['hold_applied_at'] = now
            
            # Update database
            if config_updates:
                await self.db.update_device_config(thermostat_id, config_updates)
                logger.debug(f"[DB] Saved config to database for {thermostat_id}: {config_updates}")
            
        except Exception as e:
            logger.error(f"Failed to save config to database for {thermostat_id}: {e}")

    async def _sync_thermostat_time(self, device, session):
        """Sync thermostat time to current time"""
        try:
            now_edt = datetime.now()
            thermostat_time = {
                "day": now_edt.weekday(),  # 0=Monday in thermostat API
                "hour": now_edt.hour,
                "minute": now_edt.minute
            }
            
            time_response = await session.post(f"http://{device.ip}/tstat",
                                             json={"time": thermostat_time})
            if time_response.status == 200:
                logger.info(f"[TIME] Synced time for {device.name}")
            
        except Exception as e:
            logger.warning(f"Time sync failed for {device.name}: {e}")
