# Comprehensive database diagnostic - check all tables for missing data

# STEP 1: Check all thermostats registered
Write-Host "=== STEP 1: All Registered Thermostats ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
SELECT 
  thermostat_id,
  name,
  ip_address,
  active,
  last_seen
FROM thermostats 
ORDER BY thermostat_id;
"

Write-Host "`n=== STEP 2: Current State - Count Per Thermostat ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
SELECT 
  thermostat_id,
  ts as latest_update,
  temp,
  t_heat,
  tmode
FROM current_state 
ORDER BY thermostat_id;
"

Write-Host "`n=== STEP 3: Raw Readings - Count Per Thermostat (Last 24 Hours) ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
SELECT 
  thermostat_id,
  COUNT(*) as reading_count,
  MIN(ts) as first_reading,
  MAX(ts) as last_reading,
  EXTRACT(EPOCH FROM (MAX(ts) - MIN(ts))) / 3600 as hours_span
FROM raw_readings 
WHERE ts > NOW() - INTERVAL '24 hours'
GROUP BY thermostat_id 
ORDER BY thermostat_id;
"

Write-Host "`n=== STEP 4: Raw Readings - Last 20 Records Sorted by ID then Time ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
SELECT 
  thermostat_id,
  ts,
  temp,
  t_heat,
  tmode
FROM raw_readings 
WHERE ts > NOW() - INTERVAL '2 hours'
ORDER BY thermostat_id, ts DESC
LIMIT 20;
"

Write-Host "`n=== STEP 5: Check for Missing Thermostats in Raw Readings ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
SELECT 
  t.thermostat_id,
  t.name,
  t.active,
  CASE 
    WHEN r.thermostat_id IS NULL THEN 'NO RAW READINGS'
    ELSE 'HAS RAW READINGS'
  END as status
FROM thermostats t
LEFT JOIN (
  SELECT DISTINCT thermostat_id 
  FROM raw_readings 
  WHERE ts > NOW() - INTERVAL '1 hour'
) r ON t.thermostat_id = r.thermostat_id
WHERE t.active = true
ORDER BY t.thermostat_id;
"

Write-Host "`n=== STEP 6: Minute Readings Check ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
SELECT 
  thermostat_id,
  COUNT(*) as minute_records,
  MAX(minute_ts) as latest_minute
FROM minute_readings 
WHERE minute_ts > NOW() - INTERVAL '24 hours'
GROUP BY thermostat_id 
ORDER BY thermostat_id;
"