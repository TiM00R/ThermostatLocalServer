"""
Database manager for PostgreSQL operations
"""

import asyncio
import asyncpg
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone, timedelta
import json

from .models import ThermostatRecord, StatusRecord, MinuteReading, _convert_ip_address

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages PostgreSQL database operations for thermostat data"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.pool = None
        self.db_host = config['database']['host']
        self.db_port = config['database']['port'] 
        self.db_name = config['database']['database']
        self.db_user = config['database']['username']
        self.db_password = config['database']['password']
        
    async def initialize(self):
        """Initialize database connection pool and schema"""
        try:
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                min_size=5,
                max_size=20,
                command_timeout=10
            )
            
            logger.info("Database connection pool created")
            
            # Create schema if not exists
            await self.create_schema()
            logger.info("Database schema initialized")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
            
    async def create_schema(self):
        """Create database tables if they don't exist - UPDATED SCHEMA"""
        schema_sql = """
        -- Thermostat devices table - UPDATED: Added away_temp column
        CREATE TABLE IF NOT EXISTS thermostats (
            thermostat_id TEXT PRIMARY KEY,
            ip_address INET NOT NULL,
            name TEXT NOT NULL,
            model TEXT,
            api_version INTEGER,
            fw_version TEXT,
            capabilities JSONB,
            discovery_method TEXT,
            active BOOLEAN DEFAULT true,
            away_temp REAL DEFAULT 50.0,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMPTZ
        );
        
        -- Current thermostat status - UPDATED: added local_temp
        CREATE TABLE IF NOT EXISTS current_state (
            thermostat_id TEXT PRIMARY KEY REFERENCES thermostats(thermostat_id),
            ts TIMESTAMPTZ NOT NULL,
            temp REAL NOT NULL,
            t_heat REAL NOT NULL,
            tmode INTEGER NOT NULL,
            tstate INTEGER NOT NULL,
            hold INTEGER DEFAULT 0,
            override INTEGER DEFAULT 0,
            ip_address INET NOT NULL,
            local_temp REAL,
            last_error TEXT
        );
        
        -- Raw readings (5-second polling data) - UPDATED: added local_temp
        CREATE TABLE IF NOT EXISTS raw_readings (
            thermostat_id TEXT NOT NULL REFERENCES thermostats(thermostat_id),
            ts TIMESTAMPTZ NOT NULL,
            temp REAL NOT NULL,
            t_heat REAL NOT NULL,
            tmode INTEGER NOT NULL,
            tstate INTEGER NOT NULL,
            hold INTEGER DEFAULT 0,
            override INTEGER DEFAULT 0,
            local_temp REAL,
            PRIMARY KEY (thermostat_id, ts)
        );
        
        -- Minute aggregations - UPDATED: uses hvac_runtime_percent for accurate HVAC analysis
        CREATE TABLE IF NOT EXISTS minute_readings (
            thermostat_id TEXT NOT NULL REFERENCES thermostats(thermostat_id),
            minute_ts TIMESTAMPTZ NOT NULL,
            temp_avg REAL NOT NULL,
            t_heat_last REAL NOT NULL,
            tmode_last INTEGER NOT NULL,
            hvac_runtime_percent REAL NOT NULL,
            poll_count INTEGER DEFAULT 0,
            poll_failures INTEGER DEFAULT 0,
            local_temp_avg REAL,
            PRIMARY KEY (thermostat_id, minute_ts)
        );
        
        -- Device configuration tracking
        CREATE TABLE IF NOT EXISTS device_config (
            thermostat_id TEXT PRIMARY KEY REFERENCES thermostats(thermostat_id),
            tmode_set INTEGER,
            tmode_applied_at TIMESTAMPTZ,
            t_heat_set REAL,
            t_heat_applied_at TIMESTAMPTZ,
            t_cool_set REAL,
            t_cool_applied_at TIMESTAMPTZ,
            hold_set INTEGER,
            hold_applied_at TIMESTAMPTZ,
            time_last_synced TIMESTAMPTZ,
            time_format_set INTEGER,
            time_format_applied_at TIMESTAMPTZ,
            night_light_set INTEGER,
            night_light_applied_at TIMESTAMPTZ,
            lock_mode_set INTEGER,
            lock_applied_at TIMESTAMPTZ,
            simple_mode_set INTEGER,
            simple_mode_applied_at TIMESTAMPTZ,
            save_energy_mode_set INTEGER,
            save_energy_applied_at TIMESTAMPTZ,
            stage_delay_set INTEGER,
            stage_delay_applied_at TIMESTAMPTZ,
            temp_differential_set REAL,
            temp_diff_applied_at TIMESTAMPTZ,
            config_version INTEGER DEFAULT 1,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Sync checkpoints
        CREATE TABLE IF NOT EXISTS sync_checkpoint (
            name TEXT PRIMARY KEY,
            last_ts TIMESTAMPTZ NOT NULL
        );
        
        -- Create indexes for performance
        CREATE INDEX IF NOT EXISTS idx_raw_readings_device_ts 
        ON raw_readings(thermostat_id, ts DESC);
        
        CREATE INDEX IF NOT EXISTS idx_minute_readings_device_ts 
        ON minute_readings(thermostat_id, minute_ts DESC);
        
        CREATE INDEX IF NOT EXISTS idx_current_state_ts 
        ON current_state(ts DESC);
        
        -- Add columns to existing tables if they don't have them
        DO $$
        BEGIN
            -- Add local_temp to current_state if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'current_state' AND column_name = 'local_temp'
            ) THEN
                ALTER TABLE current_state ADD COLUMN local_temp REAL;
            END IF;
            
            -- Add local_temp to raw_readings if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'raw_readings' AND column_name = 'local_temp'
            ) THEN
                ALTER TABLE raw_readings ADD COLUMN local_temp REAL;
            END IF;
            
            -- Add local_temp_avg to minute_readings if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'minute_readings' AND column_name = 'local_temp_avg'
            ) THEN
                ALTER TABLE minute_readings ADD COLUMN local_temp_avg REAL;
            END IF;
            
            -- Add away_temp to thermostats if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'thermostats' AND column_name = 'away_temp'
            ) THEN
                ALTER TABLE thermostats ADD COLUMN away_temp REAL DEFAULT 50.0;
            END IF;
            
            -- Add hvac_runtime_percent to minute_readings if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'minute_readings' AND column_name = 'hvac_runtime_percent'
            ) THEN
                ALTER TABLE minute_readings ADD COLUMN hvac_runtime_percent REAL;
            END IF;
        END $$;
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(schema_sql)
    
    async def upsert_thermostat(self, device: 'ThermostatRecord') -> bool:
        """
        Insert or update thermostat device record
        FIXED: Preserve existing away_temp values unless they are NULL
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO thermostats (
                        thermostat_id, ip_address, name, model, api_version,
                        fw_version, capabilities, discovery_method, active, away_temp, last_seen
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (thermostat_id) DO UPDATE SET
                        ip_address = $2,
                        name = $3,
                        model = $4,
                        api_version = $5,
                        fw_version = $6,
                        capabilities = $7,
                        discovery_method = $8,
                        active = $9,
                        away_temp = COALESCE(thermostats.away_temp, $10),
                        last_seen = $11
                """, 
                device.thermostat_id, device.ip_address, device.name,
                device.model, device.api_version, device.fw_version,
                json.dumps(device.capabilities), device.discovery_method,
                device.active, device.away_temp, device.last_seen or datetime.now(timezone.utc)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to upsert thermostat {device.thermostat_id}: {e}")
            return False
    
    async def save_status_reading(self, status: 'StatusRecord') -> bool:
        """Save current status and raw reading - UPDATED: includes local_temp"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Update current_state
                    await conn.execute("""
                        INSERT INTO current_state (
                            thermostat_id, ts, temp, t_heat, tmode, tstate,
                            hold, override, ip_address, local_temp, last_error
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        ON CONFLICT (thermostat_id) DO UPDATE SET
                            ts = $2, temp = $3, t_heat = $4, tmode = $5,
                            tstate = $6, hold = $7, override = $8,
                            ip_address = $9, local_temp = $10, last_error = $11
                    """,
                    status.thermostat_id, status.ts, status.temp, status.t_heat,
                    status.tmode, status.tstate, status.hold, status.override,
                    status.ip_address, status.local_temp, status.last_error
                    )
                    
                    # Insert raw reading
                    await conn.execute("""
                        INSERT INTO raw_readings (
                            thermostat_id, ts, temp, t_heat, tmode, tstate, hold, override, local_temp
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (thermostat_id, ts) DO NOTHING
                    """,
                    status.thermostat_id, status.ts, status.temp, status.t_heat,
                    status.tmode, status.tstate, status.hold, status.override, status.local_temp
                    )
            return True
        except Exception as e:
            logger.error(f"Failed to save status for {status.thermostat_id}: {e}")
            return False
    
    async def get_active_thermostats(self) -> List[ThermostatRecord]:
        """Get all active thermostats - UPDATED: includes away_temp"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT thermostat_id, ip_address, name, model, api_version,
                           fw_version, capabilities, discovery_method, active, away_temp, last_seen
                    FROM thermostats 
                    WHERE active = true
                """)
                
                return [ThermostatRecord(
                    thermostat_id=row['thermostat_id'],
                    ip_address=_convert_ip_address(row['ip_address']),  # FIXED: Convert to string
                    name=row['name'],
                    model=row['model'],
                    api_version=row['api_version'],
                    fw_version=row['fw_version'],
                    capabilities=json.loads(row['capabilities']) if row['capabilities'] else {},
                    discovery_method=row['discovery_method'],
                    active=row['active'],
                    away_temp=row.get('away_temp', 50.0),  # NEW: Include away_temp
                    last_seen=row['last_seen']
                ) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get active thermostats: {e}")
            return []
    
    async def get_current_status(self, thermostat_id: Optional[str] = None) -> List[StatusRecord]:
        """Get current status for one or all thermostats - FIXED: IPv4Address conversion"""
        try:
            async with self.pool.acquire() as conn:
                if thermostat_id:
                    rows = await conn.fetch("""
                        SELECT cs.*, t.name, t.model
                        FROM current_state cs
                        JOIN thermostats t ON cs.thermostat_id = t.thermostat_id
                        WHERE cs.thermostat_id = $1
                    """, thermostat_id)
                else:
                    rows = await conn.fetch("""
                        SELECT cs.*
                        FROM current_state cs  
                        JOIN thermostats t ON cs.thermostat_id = t.thermostat_id
                        WHERE t.active = true
                        ORDER BY cs.thermostat_id
                    """)
                
                return [StatusRecord(
                    thermostat_id=row['thermostat_id'],
                    ts=row['ts'],
                    temp=row['temp'],
                    t_heat=row['t_heat'],
                    tmode=row['tmode'],
                    tstate=row['tstate'],
                    hold=row['hold'],
                    override=row['override'],
                    ip_address=_convert_ip_address(row['ip_address']),  # FIXED: Convert to string
                    local_temp=row.get('local_temp'),
                    last_error=row['last_error']
                ) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get current status: {e}")
            return []
    
    async def create_minute_aggregation(self, start_time: datetime, end_time: datetime):
        """Create minute aggregations from raw readings - UPDATED: calculates hvac_runtime_percent"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO minute_readings (
                        thermostat_id, minute_ts, temp_avg, t_heat_last, tmode_last, 
                        hvac_runtime_percent, poll_count, poll_failures, local_temp_avg
                    )
                    SELECT 
                        thermostat_id,
                        date_trunc('minute', $1::TIMESTAMPTZ) as minute_ts,
                        AVG(temp) as temp_avg,
                        (array_agg(t_heat ORDER BY ts DESC))[1] as t_heat_last,
                        (array_agg(tmode ORDER BY ts DESC))[1] as tmode_last,
                        ROUND(
                            (COUNT(CASE WHEN tstate > 0 THEN 1 END) * 100.0 / COUNT(*))::NUMERIC, 
                            1
                        ) as hvac_runtime_percent,
                        COUNT(*) as poll_count,
                        0 as poll_failures,
                        AVG(local_temp) as local_temp_avg
                    FROM raw_readings
                    WHERE ts >= $1::TIMESTAMPTZ AND ts < $2::TIMESTAMPTZ
                    GROUP BY thermostat_id
                    ON CONFLICT (thermostat_id, minute_ts) DO NOTHING
                """, start_time, end_time)
                
            logger.info(f"Created minute aggregations for {start_time.strftime('%H:%M')}")
        except Exception as e:
            logger.error(f"Failed to create minute aggregation: {e}")
    
    async def cleanup_old_data(self, raw_retention_days: int = 14, minute_retention_days: int = 365):
        """Clean up old data based on retention policies"""
        try:
            async with self.pool.acquire() as conn:
                cutoff_raw = datetime.now(timezone.utc) - timedelta(days=raw_retention_days)
                cutoff_minute = datetime.now(timezone.utc) - timedelta(days=minute_retention_days)
                
                # Clean raw readings
                raw_deleted = await conn.fetchval("""
                    DELETE FROM raw_readings WHERE ts < $1::TIMESTAMPTZ
                    RETURNING COUNT(*)
                """, cutoff_raw)
                
                # Clean minute readings  
                minute_deleted = await conn.fetchval("""
                    DELETE FROM minute_readings WHERE minute_ts < $1::TIMESTAMPTZ
                    RETURNING COUNT(*)
                """, cutoff_minute)
                
                logger.info(f"Cleanup: {raw_deleted} raw readings, {minute_deleted} minute readings")
                
        except Exception as e:
            logger.error(f"Data cleanup failed: {e}")
    
    async def mark_device_inactive(self, thermostat_id: str):
        """Mark a thermostat as inactive"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE thermostats 
                    SET active = false, last_seen = CURRENT_TIMESTAMP
                    WHERE thermostat_id = $1
                """, thermostat_id)
        except Exception as e:
            logger.error(f"Failed to mark device inactive {thermostat_id}: {e}")
    
    async def get_device_config(self, thermostat_id: str) -> Optional[Dict]:
        """Get device configuration settings"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM device_config WHERE thermostat_id = $1
                """, thermostat_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get device config for {thermostat_id}: {e}")
            return None
    
    async def update_device_config(self, thermostat_id: str, config_updates: Dict):
        """Update device configuration settings"""
        try:
            # Build dynamic update query based on provided fields
            set_clauses = []
            values = [thermostat_id]
            param_idx = 2
            
            for key, value in config_updates.items():
                set_clauses.append(f"{key} = ${param_idx}")
                values.append(value)
                param_idx += 1
            
            set_clauses.append(f"updated_at = ${param_idx}")
            values.append(datetime.now(timezone.utc))
            
            query = f"""
                INSERT INTO device_config (thermostat_id, {', '.join(config_updates.keys())}, updated_at)
                VALUES ($1, {', '.join(f'${i}' for i in range(2, param_idx + 1))})
                ON CONFLICT (thermostat_id) DO UPDATE SET
                {', '.join(set_clauses)}
            """
            
            async with self.pool.acquire() as conn:
                await conn.execute(query, *values)
                
        except Exception as e:
            logger.error(f"Failed to update device config for {thermostat_id}: {e}")
    
    # === STAGE 2: SYNC-RELATED METHODS ===
    
    async def get_sync_checkpoint(self, name: str) -> Optional[datetime]:
        """Get sync checkpoint timestamp"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT last_ts FROM sync_checkpoint WHERE name = $1
                """, name)
                return row['last_ts'] if row else None
        except Exception as e:
            logger.error(f"Failed to get sync checkpoint {name}: {e}")
            return None
    
    async def update_sync_checkpoint(self, name: str, timestamp: datetime):
        """Update sync checkpoint timestamp"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO sync_checkpoint (name, last_ts)
                    VALUES ($1, $2)
                    ON CONFLICT (name) DO UPDATE SET last_ts = $2
                """, name, timestamp)
        except Exception as e:
            logger.error(f"Failed to update sync checkpoint {name}: {e}")
    
    async def get_minute_readings_since(self, since_timestamp: datetime) -> List[MinuteReading]:
        """Get minute readings since specified timestamp - UPDATED: uses hvac_runtime_percent"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT thermostat_id, minute_ts, temp_avg, t_heat_last, tmode_last, 
                           hvac_runtime_percent, poll_count, poll_failures, local_temp_avg
                    FROM minute_readings 
                    WHERE minute_ts > $1
                    ORDER BY thermostat_id, minute_ts
                """, since_timestamp)
                
                return [MinuteReading(
                    thermostat_id=row['thermostat_id'],
                    minute_ts=row['minute_ts'],
                    temp_avg=row['temp_avg'],
                    t_heat_last=row['t_heat_last'],
                    tmode_last=row['tmode_last'],
                    hvac_runtime_percent=row['hvac_runtime_percent'],
                    poll_count=row['poll_count'],
                    poll_failures=row['poll_failures'],
                    local_temp_avg=row.get('local_temp_avg')
                ) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get minute readings since {since_timestamp}: {e}")
            return []
    
    async def get_thermostat_by_id(self, thermostat_id: str) -> Optional[ThermostatRecord]:
        """Get thermostat record by ID - UPDATED: includes away_temp"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT thermostat_id, ip_address, name, model, api_version,
                           fw_version, capabilities, discovery_method, active, away_temp, last_seen
                    FROM thermostats 
                    WHERE thermostat_id = $1
                """, thermostat_id)
                
                if row:
                    return ThermostatRecord(
                        thermostat_id=row['thermostat_id'],
                        ip_address=_convert_ip_address(row['ip_address']),  # FIXED: Convert to string
                        name=row['name'],
                        model=row['model'],
                        api_version=row['api_version'],
                        fw_version=row['fw_version'],
                        capabilities=json.loads(row['capabilities']) if row['capabilities'] else {},
                        discovery_method=row['discovery_method'],
                        active=row['active'],
                        away_temp=row.get('away_temp', 50.0),  # NEW: Include away_temp
                        last_seen=row['last_seen']
                    )
                return None
                
        except Exception as e:
            logger.error(f"Failed to get thermostat {thermostat_id}: {e}")
            return None

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def update_thermostat_away_temp(self, thermostat_id: str, away_temp: float) -> bool:
        """Update away temperature for a thermostat"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE thermostats 
                    SET away_temp = $1 
                    WHERE thermostat_id = $2 AND active = true
                """, away_temp, thermostat_id)
                
                # Check if any rows were updated
                rows_affected = int(result.split()[-1]) if result and result.split() else 0
                success = rows_affected > 0
                
                if success:
                    logger.info(f"Updated away_temp for {thermostat_id}: {away_temp}°F")
                else:
                    logger.warning(f"No active thermostat found with ID: {thermostat_id}")
                
                return success
                
        except Exception as e:
            logger.error(f"Failed to update away_temp for {thermostat_id}: {e}")
            return False

    async def update_thermostat_last_seen(self, thermostat_id: str) -> bool:
        """Update last_seen timestamp for a thermostat after successful communication"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE thermostats 
                    SET last_seen = $1 
                    WHERE thermostat_id = $2 AND active = true
                """, datetime.now(timezone.utc), thermostat_id)
                
                # Check if any rows were updated
                rows_affected = int(result.split()[-1]) if result and result.split() else 0
                success = rows_affected > 0
                
                if success:
                    logger.debug(f"Updated last_seen for thermostat {thermostat_id}")
                else:
                    logger.warning(f"No active thermostat found with ID: {thermostat_id}")
                
                return success
                
        except Exception as e:
            logger.error(f"Failed to update last_seen for {thermostat_id}: {e}")
            return False
