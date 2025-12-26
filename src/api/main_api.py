"""
Main FastAPI application setup
"""

"""
Local HTTP API for RadioThermostat CT50 Server (Stage 2) - WITH WEATHER INTEGRATION
Provides REST endpoints for direct thermostat control, sync monitoring, and weather data
UPDATED: Added weather endpoints and local temperature in status responses
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import asyncio
import logging
from datetime import datetime, timezone
import json

# Import HTTP helper function
from http_helper import create_thermostat_session

# Import modular route factories
from .system_routes import create_system_routes
from .thermostat_routes import create_thermostat_routes




logger = logging.getLogger(__name__)


class SyncStatusResponse(BaseModel):
    enabled: bool
    server_url: Optional[str]
    status_last_upload: Optional[datetime]
    minute_last_upload: Optional[datetime]
    command_last_poll: Optional[datetime]
    health_status: str
    error_message: Optional[str] = None

# # NEW: Weather response models
class WeatherStatusResponse(BaseModel):
    enabled: bool
    zip_code: Optional[str]
    current_temp: Optional[float]
    last_update: Optional[datetime]
    last_error: Optional[str]
    update_count: int
    error_count: int
    next_update: Optional[datetime]

class ThermostatAPI:
    """Local HTTP API for thermostat control, sync monitoring, and weather data"""
    
    def __init__(self, database_manager, config: Dict, weather_service=None):
        self.db = database_manager
        self.config = config
        self.weather = weather_service  # NEW: Weather service reference
        self.app = FastAPI(
            title="RadioThermostat CT50 Local Server with Weather Integration",
            description="Local API for thermostat control, monitoring, sync status, and weather data",
            version="2.1.0"
        )
        self._setup_routes()
    

    def _setup_routes(self):
        """Setup FastAPI routes using modular approach"""
        
        # Use modular route factories
        system_router = create_system_routes(self.db, self.config, self.weather)
        thermostat_router = create_thermostat_routes(self.db, self.weather)
        
        self.app.include_router(system_router)
        self.app.include_router(thermostat_router)
        
        # Keep only sync-specific endpoints in main class
        self._setup_sync_routes()

    def _setup_sync_routes(self):
        """Setup sync-specific routes that are unique to main API"""
        
        # === STAGE 2 ENDPOINTS (Public Server Sync) ===
        
        @self.app.get("/api/system/sync/status", response_model=SyncStatusResponse)
        async def get_sync_status():
            """Get public server sync status and health"""
            try:
                sync_config = self.config.get('public_server', {})
                enabled = sync_config.get('enabled', False)
                
                if not enabled:
                    return SyncStatusResponse(
                        enabled=False,
                        health_status="disabled",
                        server_url=None,
                        status_last_upload=None,
                        minute_last_upload=None,
                        command_last_poll=None
                    )
                
                # Get sync checkpoints
                status_checkpoint = await self.db.get_sync_checkpoint('status_upload')
                minute_checkpoint = await self.db.get_sync_checkpoint('minute_upload')
                command_checkpoint = await self.db.get_sync_checkpoint('command_poll')
                
                # Determine health status
                now = datetime.now(timezone.utc)
                health_status = "healthy"
                error_message = None
                
                # Check if uploads are recent (within expected intervals + buffer)
                status_interval = sync_config.get('status_upload_seconds', 30)
                minute_interval = sync_config.get('minute_upload_seconds', 60)
                
                if status_checkpoint and (now - status_checkpoint).total_seconds() > status_interval * 3:
                    health_status = "degraded"
                    error_message = "Status uploads are behind schedule"
                
                if minute_checkpoint and (now - minute_checkpoint).total_seconds() > minute_interval * 3:
                    health_status = "degraded"  
                    error_message = "Minute uploads are behind schedule"
                
                return SyncStatusResponse(
                    enabled=True,
                    server_url=sync_config.get('base_url'),
                    status_last_upload=status_checkpoint,
                    minute_last_upload=minute_checkpoint,
                    command_last_poll=command_checkpoint,
                    health_status=health_status,
                    error_message=error_message
                )
                
            except Exception as e:
                logger.error(f"Error getting sync status: {e}")
                return SyncStatusResponse(
                    enabled=False,
                    health_status="error",
                    error_message=str(e),
                    server_url=None,
                    status_last_upload=None,
                    minute_last_upload=None,
                    command_last_poll=None
                )
        
        @self.app.get("/api/system/sync/checkpoints")
        async def get_sync_checkpoints():
            """Get detailed sync checkpoint information"""
            try:
                checkpoints = {}
                checkpoint_names = ['status_upload', 'minute_upload', 'command_poll']
                
                for name in checkpoint_names:
                    checkpoint = await self.db.get_sync_checkpoint(name)
                    checkpoints[name] = {
                        "last_timestamp": checkpoint,
                        "minutes_ago": (datetime.now(timezone.utc) - checkpoint).total_seconds() / 60 if checkpoint else None
                    }
                
                return {
                    "checkpoints": checkpoints,
                    "timestamp": datetime.now(timezone.utc)
                }
                
            except Exception as e:
                logger.error(f"Error getting sync checkpoints: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/system/sync/stats")
        async def get_sync_stats():
            """Get synchronization statistics"""
            try:
                # Get minute data statistics
                minute_stats = await self.db.pool.fetchrow("""
                    SELECT 
                        COUNT(*) as total_minutes,
                        MIN(minute_ts) as earliest_minute,
                        MAX(minute_ts) as latest_minute,
                        COUNT(CASE WHEN local_temp_avg IS NOT NULL THEN 1 END) as with_weather
                    FROM minute_readings
                """)
                
                # Get raw data statistics
                raw_stats = await self.db.pool.fetchrow("""
                    SELECT 
                        COUNT(*) as total_readings,
                        MIN(ts) as earliest_reading,
                        MAX(ts) as latest_reading,
                        COUNT(CASE WHEN local_temp IS NOT NULL THEN 1 END) as with_weather
                    FROM raw_readings
                """)
                
                # Get thermostat count
                thermostat_count = await self.db.pool.fetchval("""
                    SELECT COUNT(*) FROM thermostats WHERE active = true
                """)
                
                return {
                    "thermostats": {
                        "active_count": thermostat_count
                    },
                    "raw_readings": {
                        "total_count": raw_stats['total_readings'],
                        "earliest": raw_stats['earliest_reading'],
                        "latest": raw_stats['latest_reading'],
                        "with_weather_data": raw_stats['with_weather']
                    },
                    "minute_readings": {
                        "total_count": minute_stats['total_minutes'],
                        "earliest": minute_stats['earliest_minute'],
                        "latest": minute_stats['latest_minute'],
                        "with_weather_data": minute_stats['with_weather']
                    },
                    "timestamp": datetime.now(timezone.utc)
                }
                
            except Exception as e:
                logger.error(f"Error getting sync stats: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Keep the _execute_thermostat_command and _update_config_tracking methods in main class
        # since they're used by sync-specific functionality if needed  
       
    