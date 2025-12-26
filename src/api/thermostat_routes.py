"""
Thermostat control API routes
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
from datetime import datetime, timezone
import aiohttp
from http_helper import create_thermostat_session
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Request models
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


async def _execute_thermostat_command(db_manager, thermostat_id: str, command: dict):
    """Execute command on specific thermostat"""
    try:
        thermostat = await db_manager.get_thermostat_by_id(thermostat_id)
        if not thermostat:
            return {
                "thermostat_id": thermostat_id,
                "name": "Unknown",
                "ip_address": "Unknown", 
                "status": "failed",
                "error": "Thermostat not found"
            }
        
        url = f"http://{thermostat.ip_address}/tstat"
        
        async with create_thermostat_session(5) as session:
            async with session.post(url, json=command) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("success") == 0:
                        await _update_config_tracking(db_manager, thermostat_id, command)
                    
                    return {
                        "thermostat_id": thermostat_id,
                        "name": thermostat.name,
                        "ip_address": thermostat.ip_address,
                        "status": "success" if result.get("success") == 0 else "failed",
                        "response": result
                    }
                else:
                    return {
                        "thermostat_id": thermostat_id,
                        "name": thermostat.name,
                        "ip_address": thermostat.ip_address,
                        "status": "failed",
                        "error": f"HTTP {response.status}"
                    }
    except Exception as e:
        return {
            "thermostat_id": thermostat_id,
            "name": "Unknown",
            "ip_address": "Unknown",
            "status": "failed", 
            "error": str(e)
        }

async def _update_config_tracking(db_manager, thermostat_id: str, command: dict):
    """Update device_config table when commands are applied"""
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
    
    if config_updates:
        await db_manager.update_device_config(thermostat_id, config_updates)




def create_thermostat_routes(db_manager, weather_service=None):
    """Create thermostat control routes"""
    router = APIRouter(prefix="/api", tags=["thermostats"])
    
    @router.get("/thermostats")
    async def list_thermostats():
        """List all discovered thermostats"""
        thermostats = await db_manager.get_active_thermostats()
        return [{
            "thermostat_id": t.thermostat_id,
            "name": t.name,
            "ip_address": t.ip_address,
            "model": t.model,
            "api_version": t.api_version,
            "active": t.active,
            "last_seen": t.last_seen
        } for t in thermostats]
    
    @router.get("/thermostats/{thermostat_id}/status")
    async def get_thermostat_status(thermostat_id: str):
        """Get current status for specific thermostat"""
        status = await db_manager.get_current_status(thermostat_id)
        if not status:
            raise HTTPException(status_code=404, detail="Thermostat not found")
        
        status_record = status[0]
        return {
            "thermostat_id": status_record.thermostat_id,
            "ts": status_record.ts,
            "temp": status_record.temp,
            "t_heat": status_record.t_heat,
            "tmode": status_record.tmode,
            "tstate": status_record.tstate,
            "hold": status_record.hold,
            "override": status_record.override,
            "ip_address": status_record.ip_address,
            "local_temp": status_record.local_temp,
            "last_error": status_record.last_error
        }
    
    @router.get("/site/status")
    async def get_site_status():
        """Get current status for all thermostats"""
        status_records = await db_manager.get_current_status()
        return [{
            "thermostat_id": s.thermostat_id,
            "ts": s.ts,
            "temp": s.temp,
            "t_heat": s.t_heat,
            "tmode": s.tmode,
            "tstate": s.tstate,
            "hold": s.hold,
            "override": s.override,
            "ip_address": s.ip_address,
            "local_temp": s.local_temp,
            "last_error": s.last_error
        } for s in status_records]
    
    @router.post("/thermostats/{thermostat_id}/temperature")
    async def set_thermostat_temperature(thermostat_id: str, request: TemperatureRequest):
        """Set temperature for specific thermostat"""
        command = {"tmode": 1, "t_heat": request.t_heat, "hold": 1 if request.hold else 0}
        result = await _execute_thermostat_command(db_manager, thermostat_id, command)
        return result

    @router.post("/thermostats/{thermostat_id}/mode")
    async def set_thermostat_mode(thermostat_id: str, request: ModeRequest):
        """Set operating mode for specific thermostat"""
        command = {"tmode": request.tmode}
        result = await _execute_thermostat_command(db_manager, thermostat_id, command)
        return result
    
    
    
    @router.post("/discovery/scan")
    async def trigger_discovery():
        """Trigger manual device discovery"""
        return {"message": "Discovery scan initiated"}
    
    return router
