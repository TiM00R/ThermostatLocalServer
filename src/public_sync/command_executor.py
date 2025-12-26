"""
Command execution for public sync operations
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Tuple
import aiohttp
import json

logger = logging.getLogger(__name__)

class LocalDBAdapter:
    async def fetch_all(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError
    async def fetch_one(self, query: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

class LocalCommandExecutor:
    """Executes the unified `set_state` command against individual thermostats.

    Validation rules:
      - tmode must be 0 (OFF) or 1 (HEAT)
      - hold must be 0 or 1
      - if tmode == 1 then t_heat is required
      - if tmode == 0 then t_heat must be omitted

    After POSTing to /tstat, verifies the state by reading /tstat back and
    checking fields. Allows a small tolerance on t_heat when in HEAT mode.
    
    UPDATED: No longer processes "all" commands - only individual thermostat IDs.
    NEW: Added set_away_temp command support.
    """
    def __init__(self, db: LocalDBAdapter, session: Optional[aiohttp.ClientSession] = None):
        self.db = db
        self._own_session = session is None
        self.session = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def close(self):
        if self._own_session and not self.session.closed:
            await self.session.close()

    async def execute_command(
        self,
        site_id: str,
        thermostat_id: str,
        cmd: str,
        params: Dict[str, Any],
        timeout_seconds: int = 300,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        if cmd == "set_state":
            return await self._execute_set_state(site_id, thermostat_id, params, timeout_seconds)
        elif cmd == "set_away_temp":
            return await self._execute_set_away_temp(site_id, thermostat_id, params)
        else:
            return False, f"Unsupported command: {cmd}", None

    async def _execute_set_state(self, site_id: str, thermostat_id: str, params: Dict[str, Any], timeout_seconds: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Execute set_state command for individual thermostat"""
        # Process individual thermostat commands only (no "all" support)
        target_ids = [thermostat_id]

        # Validate params
        tmode = params.get("tmode", None)
        hold = params.get("hold", None)
        t_heat = params.get("t_heat", None)

        if tmode not in (0, 1):
            return False, "Invalid or missing tmode (expected 0 or 1)", None
        if hold not in (0, 1):
            return False, "Invalid or missing hold (expected 0 or 1)", None
        
        #  DEFENSIVE FILTERING: Remove t_heat if tmode=0 (instead of rejecting)
        
        if tmode == 0 and "t_heat" in params:
            logger.warning(f"Command for {thermostat_id} contained t_heat with tmode=0 - removing t_heat for safety")
            params = params.copy()  # Make a copy
            del params["t_heat"]    # Remove the key
            t_heat = None
                
        
        if tmode == 1 and t_heat is None:
            return False, "Missing t_heat for HEAT mode", None
        if tmode == 0 and ("t_heat" in params):
            return False, "t_heat must be omitted when tmode == 0", None

        async def do_one(tid: str) -> Tuple[str, bool, Optional[str]]:
            ip = await self._resolve_thermostat_ip(site_id, tid)
            if not ip:
                return tid, False, "IP not found"
            payload = {"tmode": tmode, "hold": hold}
            if tmode == 1:
                payload["t_heat"] = float(t_heat)

            ok, err = await self._post_tstat(ip, payload, timeout_seconds)
            if not ok:
                return tid, False, err

            verified = await self._verify_set_state(ip, expected=payload)
            if not verified:
                return tid, False, "Verification failed"
            
            # UPDATE device_config table with applied settings (same as local API)
            try:
                config_updates = {}
                now = datetime.now(timezone.utc)
                
                if "tmode" in payload:
                    config_updates["tmode_set"] = payload["tmode"]
                    config_updates["tmode_applied_at"] = now
                    
                if "t_heat" in payload:
                    config_updates["t_heat_set"] = payload["t_heat"]
                    config_updates["t_heat_applied_at"] = now
                    
                if "hold" in payload:
                    config_updates["hold_set"] = payload["hold"]
                    config_updates["hold_applied_at"] = now
                
                if config_updates:
                    await self.db.db.update_device_config(tid, config_updates)
                    logger.debug(f"Updated device config for {tid}: {config_updates}")
                    
            except Exception as e:
                logger.warning(f"Failed to update device config for {tid}: {e}")
                # Don't fail the command execution due to config tracking failure
            return tid, True, None

        results = await asyncio.gather(*(do_one(tid) for tid in target_ids))

        all_ok = all(ok for _, ok, _ in results)
        first_err = next((err for _, ok, err in results if not ok), None)
        extra = {
            "per_thermostat": [
                {"thermostat_id": tid, "success": ok, "error": err}
                for tid, ok, err in results
            ]
        }
        return all_ok, first_err, extra

    async def _execute_set_away_temp(self, site_id: str, thermostat_id: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Execute set_away_temp command"""
        try:
            away_temp = params.get("away_temp")
            
            # Validate parameters
            if away_temp is None:
                return False, "Missing away_temp parameter", None
            
            try:
                temp_value = float(away_temp)
                if temp_value < 41.0 or temp_value > 76.0:
                    return False, "away_temp must be between 41.0 and 76.0 degrees Fahrenheit", None
            except (ValueError, TypeError):
                return False, "away_temp must be a valid number", None
            
            # Update local database
            success = await self.db.update_thermostat_away_temp(thermostat_id, temp_value)
            
            if success:
                logger.info(f"Updated away_temp for {thermostat_id}: {temp_value}°F")
                return True, None, {"away_temp": temp_value, "thermostat_id": thermostat_id}
            else:
                return False, f"Failed to update database for thermostat {thermostat_id}", None
                
        except Exception as e:
            logger.error(f"Error executing set_away_temp: {e}")
            return False, str(e), None

    async def _get_all_thermostat_ids_for_site(self, site_id: str) -> List[str]:
        """UNUSED: Method kept for compatibility but no longer called"""
        rows = await self.db.fetch_all(
            "SELECT thermostat_id FROM thermostats WHERE site_id = :site_id AND is_active = 1",
            {"site_id": site_id},
        )
        return [r.get("thermostat_id") for r in rows]

    async def _resolve_thermostat_ip(self, site_id: str, thermostat_id: str) -> Optional[str]:
        row = await self.db.fetch_one(
            "SELECT ip_address FROM thermostats WHERE site_id = :site_id AND thermostat_id = :tid",
            {"site_id": site_id, "tid": thermostat_id},
        )
        return row.get("ip_address") if row else None

    async def _post_tstat(self, ip: str, payload: Dict[str, Any], timeout_seconds: int) -> Tuple[bool, Optional[str]]:
        url = f"http://{ip}/tstat"
        logger.info("Command sent to Thermostat %s Payload=%s", url, payload)
        try:
            async with self.session.post(url, json=payload, timeout=timeout_seconds) as resp:
                if 200 <= resp.status < 300:
                    return True, None
                txt = await resp.text()
                return False, f"Device HTTP {resp.status}: {txt[:200]}"
        except Exception as e:
            logger.exception("POST /tstat failed")
            return False, str(e)

    async def _get_tstat_readback(self, ip: str) -> Dict[str, Any]:
        url = f"http://{ip}/tstat"
        try:
            async with self.session.get(url) as resp:
                if 200 <= resp.status < 300:
                    return await resp.json(content_type=None)
                return {}
        except Exception:
            logger.exception("GET /tstat failed")
            return {}

    async def _verify_set_state(self, ip: str, expected: Dict[str, Any]) -> bool:
        current = await self._get_tstat_readback(ip)
        if not current:
            return False

        exp_mode = expected.get("tmode")
        exp_hold = expected.get("hold")
        exp_heat = expected.get("t_heat", None)

        act_mode = current.get("tmode")
        act_hold = current.get("hold")
        act_heat = current.get("t_heat")

        if exp_mode == 0:
            return (act_mode == 0) and (act_hold == exp_hold)
        else:
            return (act_mode == 1) and (act_hold == exp_hold) and (abs(act_heat - exp_heat) < 0.1)

class DatabaseAdapter(LocalDBAdapter):
    """Adapter to make local database work with LocalCommandExecutor"""
    def __init__(self, db):
        self.db = db

    async def fetch_all(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            logger.debug(f"DatabaseAdapter fetch_all: query='{query}', params={params}")
            if "thermostat_id" in query and "is_active" in query:
                thermostats = await self.db.get_active_thermostats()
                result = [{"thermostat_id": t.thermostat_id} for t in thermostats]
                logger.debug(f"Found {len(result)} active thermostats")
                return result
            logger.warning(f"Unhandled fetch_all query: {query}")
            return []
        except Exception as e:
            logger.error(f"Database fetch_all error: {e}")
            return []

    async def fetch_one(self, query: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            logger.info(f"DatabaseAdapter fetch_one: query='{query}', params={params}")
            if "ip_address" in query and "thermostat_id" in query:
                thermostat_id = params.get("tid")
                site_id = params.get("site_id")

                logger.info(f"Looking up IP for thermostat_id='{thermostat_id}', site_id='{site_id}'")

                # Method 1: Check active thermostats
                logger.info("Method 1: Checking active thermostats...")
                active_thermostats = await self.db.get_active_thermostats()
                logger.info(f"Found {len(active_thermostats)} active thermostats:")
                for t in active_thermostats:
                    logger.info(
                        f"  - ID: '{t.thermostat_id}' (len={len(t.thermostat_id)}), IP: {t.ip_address}, Name: {t.name}, Active: {getattr(t, 'active', 'N/A')}"
                    )
                    if t.thermostat_id == thermostat_id:
                        logger.info(f"FOUND MATCH in active thermostats: {thermostat_id} -> {t.ip_address}")
                        return {"ip_address": str(t.ip_address)}

                # Method 2: Direct lookup by ID
                logger.info("Method 2: Trying direct lookup by ID...")
                try:
                    if hasattr(self.db, 'get_thermostat_by_id'):
                        direct_result = await self.db.get_thermostat_by_id(thermostat_id)
                        if direct_result:
                            logger.info(f"FOUND via direct lookup: {thermostat_id} -> {direct_result.ip_address}")
                            return {"ip_address": str(direct_result.ip_address)}
                        else:
                            logger.warning(f"Direct lookup returned None for {thermostat_id}")
                except Exception as e:
                    logger.warning(f"Direct lookup failed: {e}")

                # Method 3: All thermostats (including inactive)
                logger.info("Method 3: Checking all thermostats (including inactive)...")
                try:
                    all_thermostats = []
                    if hasattr(self.db, 'get_all_thermostats'):
                        all_thermostats = await self.db.get_all_thermostats()
                    elif hasattr(self.db, 'get_thermostats'):
                        all_thermostats = await self.db.get_thermostats()

                    if all_thermostats:
                        logger.info(f"Found {len(all_thermostats)} total thermostats:")
                        for t in all_thermostats:
                            active_status = getattr(t, 'active', 'Unknown')
                            logger.info(
                                f"  - ID: '{t.thermostat_id}', IP: {t.ip_address}, Name: {t.name}, Active: {active_status}"
                            )
                            if t.thermostat_id == thermostat_id:
                                logger.info(
                                    f"FOUND MATCH in all thermostats: {thermostat_id} -> {t.ip_address} (Active: {active_status})"
                                )
                                return {"ip_address": str(t.ip_address)}
                    else:
                        logger.warning("No method found to get all thermostats")

                except Exception as e:
                    logger.warning(f"Error checking all thermostats: {e}")

                # Method 4: Case-insensitive match
                logger.info("Method 4: Checking case-insensitive matches...")
                for t in active_thermostats:
                    if t.thermostat_id.lower() == thermostat_id.lower():
                        logger.info(f"FOUND CASE-INSENSITIVE MATCH: '{t.thermostat_id}' matches '{thermostat_id}'")
                        return {"ip_address": str(t.ip_address)}

                # Method 5: Whitespace/partial matches
                logger.info("Method 5: Checking for whitespace/partial matches...")
                for t in active_thermostats:
                    if t.thermostat_id.strip() == thermostat_id.strip():
                        logger.info(f"FOUND WHITESPACE MATCH: '{t.thermostat_id}' matches '{thermostat_id}' after strip")
                        return {"ip_address": str(t.ip_address)}

                logger.error(f"Thermostat ID '{thermostat_id}' not found in database after all methods!")
                logger.error(f"Searched ID: '{thermostat_id}' (length: {len(thermostat_id)})")
                available_ids = [f"'{t.thermostat_id}'" for t in active_thermostats]
                logger.error(f"Available active IDs: {available_ids}")
                logger.info("Checking for substring matches...")
                for t in active_thermostats:
                    if thermostat_id in t.thermostat_id or t.thermostat_id in thermostat_id:
                        logger.warning(f"Substring match found: '{thermostat_id}' and '{t.thermostat_id}'")
                return None

            logger.warning(f"Unhandled fetch_one query: {query}")
            return None
        except Exception as e:
            logger.error(f"Database fetch_one error: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def update_thermostat_away_temp(self, thermostat_id: str, away_temp: float) -> bool:
        """Update away temperature for a thermostat"""
        return await self.db.update_thermostat_away_temp(thermostat_id, away_temp)



