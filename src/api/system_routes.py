"""
System health and monitoring API routes
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Response models
class SyncStatusResponse(BaseModel):
    enabled: bool
    server_url: Optional[str]
    status_last_upload: Optional[datetime]
    minute_last_upload: Optional[datetime]
    command_last_poll: Optional[datetime]
    health_status: str
    error_message: Optional[str] = None

class WeatherStatusResponse(BaseModel):
    enabled: bool
    zip_code: Optional[str]
    current_temp: Optional[float]
    last_update: Optional[datetime]
    last_error: Optional[str]
    update_count: int
    error_count: int
    next_update: Optional[datetime]

def create_system_routes(db_manager, config, weather_service=None):
    """Create system monitoring routes"""
    router = APIRouter(prefix="/api", tags=["system"])
    
    @router.get("/weather/status", response_model=WeatherStatusResponse)
    async def get_weather_status():
        """Get weather service status and current conditions"""
        try:
            if not weather_service:
                return WeatherStatusResponse(
                    enabled=False,
                    zip_code=None,
                    current_temp=None,
                    last_update=None,
                    last_error="Weather service not initialized",
                    update_count=0,
                    error_count=0,
                    next_update=None
                )
            
            status = weather_service.get_status()
            return WeatherStatusResponse(
                enabled=status['enabled'],
                zip_code=status['zip_code'],
                current_temp=status['current_temp'],
                last_update=datetime.fromisoformat(status['last_update']) if status['last_update'] else None,
                last_error=status['last_error'],
                update_count=status['update_count'],
                error_count=status['error_count'],
                next_update=datetime.fromisoformat(status['next_update']) if status['next_update'] else None
            )
            
        except Exception as e:
            logger.error(f"Error getting weather status: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/system/health")
    async def system_health():
        """System health check"""
        try:
            thermostats = await db_manager.get_active_thermostats()
            current_status = await db_manager.get_current_status()
            
            weather_health = None
            if weather_service:
                weather_status = weather_service.get_status()
                weather_health = {
                    "enabled": weather_status['enabled'],
                    "current_temp": weather_status['current_temp'],
                    "last_update": weather_status['last_update'],
                    "error_count": weather_status['error_count'],
                    "last_error": weather_status['last_error']
                }
            else:
                weather_health = {"enabled": False, "error": "Weather service not initialized"}
            
            return {
                "status": "healthy",
                "database": "connected",
                "thermostats": {
                    "active_count": len(thermostats),
                    "with_recent_status": len(current_status)
                },
                "weather_service": weather_health,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy", 
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    # Add to src/api/system_routes.py:
        
    @router.get("/weather/current")
    async def get_current_weather():
        """Get current weather temperature"""
        try:
            if not weather_service:
                raise HTTPException(status_code=503, detail="Weather service not available")
            
            temp = await weather_service.get_current_temperature()
            return {
                "temperature": temp,
                "zip_code": weather_service.zip_code if weather_service.enabled else None,
                "timestamp": datetime.now(timezone.utc),
                "enabled": weather_service.enabled
            }
        except Exception as e:
            logger.error(f"Error getting current weather: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/weather/update") 
    async def force_weather_update():
        """Force immediate weather data update"""
        try:
            if not weather_service or not weather_service.enabled:
                raise HTTPException(status_code=503, detail="Weather service not available")
            
            await weather_service.update_temperature()
            status = weather_service.get_status()
            
            return {
                "message": "Weather update completed",
                "current_temp": status['current_temp'],
                "last_update": status['last_update'],
                "last_error": status['last_error']
            }
        except Exception as e:
            logger.error(f"Error forcing weather update: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/site/status/comparison")
    async def get_temperature_comparison():
        """Get indoor vs outdoor temperature comparison"""
        try:
            status_records = await db_manager.get_current_status()
            current_weather = await weather_service.get_current_temperature() if weather_service else None
            
            comparisons = []
            for s in status_records:
                comparison = {
                    "thermostat_id": s.thermostat_id,
                    "indoor_temp": s.temp,
                    "outdoor_temp": s.local_temp or current_weather,
                    "setpoint": s.t_heat,
                    "ts": s.ts
                }
                
                if comparison["outdoor_temp"] is not None:
                    comparison["indoor_outdoor_diff"] = comparison["indoor_temp"] - comparison["outdoor_temp"]
                    comparison["setpoint_outdoor_diff"] = comparison["setpoint"] - comparison["outdoor_temp"]
                
                comparisons.append(comparison)
            
            return {
                "comparisons": comparisons,
                "weather_enabled": weather_service.enabled if weather_service else False,
                "zip_code": weather_service.zip_code if weather_service and weather_service.enabled else None,
                "timestamp": datetime.now(timezone.utc)
            }
        except Exception as e:
            logger.error(f"Error getting temperature comparison: {e}")
            raise HTTPException(status_code=500, detail=str(e))
            
    return router
