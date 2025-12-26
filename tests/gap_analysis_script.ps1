# Database Gap Analysis from Last Discovery Time
# Uses most recent last_seen from thermostats table as starting point

Write-Host "=== Thermostat Data Analysis from Last Discovery ==="
Write-Host "Times shown in EDT (Eastern Daylight Time)"
Write-Host ""

# STEP 1: Find the most recent discovery time
Write-Host "=== STEP 1: Finding Most Recent Discovery Time ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "SELECT MAX(last_seen) AT TIME ZONE 'America/New_York' as latest_discovery_edt, MAX(last_seen) as latest_discovery_utc, COUNT(*) as total_thermostats, COUNT(CASE WHEN active = true THEN 1 END) as active_thermostats FROM thermostats;"

Write-Host ""

# STEP 2: Show all thermostats with their discovery times
Write-Host "=== STEP 2: All Thermostats Discovery Times ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
SELECT 
  thermostat_id,
  name,
  ip_address,
  active,
  last_seen AT TIME ZONE 'America/New_York' as last_seen_edt,
  CASE 
    WHEN last_seen = (SELECT MAX(last_seen) FROM thermostats) THEN '🟢 LATEST'
    WHEN last_seen > (SELECT MAX(last_seen) FROM thermostats) - INTERVAL '1 minute' THEN '🟡 RECENT'
    ELSE '🔴 OLD'
  END as discovery_status
FROM thermostats 
ORDER BY last_seen DESC, thermostat_id;
"

Write-Host ""
Write-Host "=== STEP 3: Analysis from Latest Discovery Time ==="

# STEP 3: Current state analysis from discovery time
Write-Host "--- Current State Since Discovery ---"
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
)
SELECT 
  c.thermostat_id,
  c.ts AT TIME ZONE 'America/New_York' as latest_update_edt,
  c.temp,
  c.t_heat,
  c.tmode,
  EXTRACT(EPOCH FROM (NOW() - c.ts)) / 60 as minutes_since_update
FROM current_state c
CROSS JOIN discovery_time d
WHERE c.ts >= d.start_time
ORDER BY c.thermostat_id;
"

Write-Host ""
Write-Host "=== STEP 4: Raw Readings Count from Discovery ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
)
SELECT 
  r.thermostat_id,
  COUNT(*) as reading_count,
  MIN(r.ts) AT TIME ZONE 'America/New_York' as first_reading_edt,
  MAX(r.ts) AT TIME ZONE 'America/New_York' as last_reading_edt,
  ROUND(EXTRACT(EPOCH FROM (MAX(r.ts) - MIN(r.ts))) / 60, 1) as minutes_span,
  ROUND(EXTRACT(EPOCH FROM (NOW() - d.start_time)) / 60, 1) as total_minutes_since_discovery
FROM raw_readings r
CROSS JOIN discovery_time d
WHERE r.ts >= d.start_time
GROUP BY r.thermostat_id, d.start_time
ORDER BY r.thermostat_id;
"

Write-Host ""
Write-Host "=== STEP 5: GAP ANALYSIS from Discovery Time ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
),
gaps AS (
  SELECT 
    r.thermostat_id,
    r.ts,
    LAG(r.ts) OVER (PARTITION BY r.thermostat_id ORDER BY r.ts) as prev_ts,
    EXTRACT(EPOCH FROM (r.ts - LAG(r.ts) OVER (PARTITION BY r.thermostat_id ORDER BY r.ts))) as gap_seconds
  FROM raw_readings r
  CROSS JOIN discovery_time d
  WHERE r.ts >= d.start_time
),
largest_gaps AS (
  SELECT 
    thermostat_id,
    prev_ts AT TIME ZONE 'America/New_York' as gap_start_edt,
    ts AT TIME ZONE 'America/New_York' as gap_end_edt,
    ROUND(gap_seconds::NUMERIC, 1) as gap_seconds,
    ROUND((gap_seconds / 60)::NUMERIC, 1) as gap_minutes
  FROM gaps 
  WHERE gap_seconds > 10  -- Only show gaps > 10 seconds
)
SELECT 
  thermostat_id,
  gap_start_edt,
  gap_end_edt,
  gap_seconds,
  gap_minutes,
  CASE 
    WHEN gap_seconds > 300 THEN '🔴 MAJOR GAP (>5min)'
    WHEN gap_seconds > 60 THEN '🟡 LARGE GAP (>1min)' 
    WHEN gap_seconds > 15 THEN '🟢 SMALL GAP (>15s)'
    ELSE '✅ MINOR GAP'
  END as severity
FROM largest_gaps
ORDER BY gap_seconds DESC, thermostat_id
LIMIT 20;
"

Write-Host ""
Write-Host "=== STEP 6: Missing Thermostats (No Data Since Discovery) ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
)
SELECT 
  t.thermostat_id,
  t.name,
  t.active,
  t.last_seen AT TIME ZONE 'America/New_York' as discovery_time_edt,
  CASE 
    WHEN r.thermostat_id IS NULL THEN '❌ NO READINGS SINCE DISCOVERY'
    ELSE '✅ HAS READINGS SINCE DISCOVERY'
  END as status,
  COALESCE(r.reading_count, 0) as reading_count_since_discovery
FROM thermostats t
CROSS JOIN discovery_time d
LEFT JOIN (
  SELECT 
    thermostat_id,
    COUNT(*) as reading_count
  FROM raw_readings r2
  CROSS JOIN discovery_time d2
  WHERE r2.ts >= d2.start_time
  GROUP BY thermostat_id
) r ON t.thermostat_id = r.thermostat_id
WHERE t.active = true
ORDER BY t.thermostat_id;
"

Write-Host ""
Write-Host "=== STEP 7: Expected vs Actual Reading Count Since Discovery ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
),
time_analysis AS (
  SELECT 
    start_time,
    EXTRACT(EPOCH FROM (NOW() - start_time)) / 60 as total_minutes,
    FLOOR(EXTRACT(EPOCH FROM (NOW() - start_time)) / 5) as expected_readings
  FROM discovery_time
)
SELECT 
  r.thermostat_id,
  r.actual_count,
  t.expected_readings,
  ROUND((r.actual_count::NUMERIC / t.expected_readings * 100), 1) as success_rate_percent,
  (t.expected_readings - r.actual_count) as missing_readings,
  ROUND(t.total_minutes::NUMERIC, 1) as total_minutes_since_discovery,
  CASE 
    WHEN r.actual_count < t.expected_readings * 0.5 THEN '🔴 <50% DATA'
    WHEN r.actual_count < t.expected_readings * 0.8 THEN '🟡 <80% DATA'
    ELSE '🟢 >80% DATA'
  END as health_status
FROM (
  SELECT 
    thermostat_id,
    COUNT(*) as actual_count
  FROM raw_readings r2
  CROSS JOIN discovery_time d
  WHERE r2.ts >= d.start_time
  GROUP BY thermostat_id
) r
CROSS JOIN time_analysis t
ORDER BY success_rate_percent ASC;
"

Write-Host ""
Write-Host "=== ANALYSIS COMPLETE ==="
Write-Host "Note: Expected readings calculated as (minutes since discovery) / 5 seconds"