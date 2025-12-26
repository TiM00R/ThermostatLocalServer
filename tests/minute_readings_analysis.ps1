# Minute Readings Analysis from Discovery Time
# Analyzes minute_readings table starting from actual registration/discovery time

Write-Host "=== MINUTE READINGS ANALYSIS FROM DISCOVERY ==="
Write-Host "Times shown in EDT (Eastern Daylight Time)"
Write-Host ""

# STEP 1: Find discovery time and overall summary
Write-Host "=== STEP 1: Discovery Time and Overall Summary ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
)
SELECT 
  d.start_time AT TIME ZONE 'America/New_York' as discovery_time_edt,
  COUNT(m.*) as total_minute_records,
  COUNT(DISTINCT m.thermostat_id) as unique_thermostats,
  MIN(m.minute_ts) AT TIME ZONE 'America/New_York' as first_minute_edt,
  MAX(m.minute_ts) AT TIME ZONE 'America/New_York' as latest_minute_edt,
  ROUND(EXTRACT(EPOCH FROM (NOW() - d.start_time)) / 60, 0) as total_minutes_since_discovery,
  ROUND(EXTRACT(EPOCH FROM (MAX(m.minute_ts) - MIN(m.minute_ts))) / 60, 0) as actual_minutes_covered
FROM minute_readings m
CROSS JOIN discovery_time d
WHERE m.minute_ts >= d.start_time
GROUP BY d.start_time;
"

Write-Host ""
Write-Host "=== STEP 2: Count Per Thermostat Since Discovery ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
)
SELECT 
  m.thermostat_id,
  COUNT(*) as minute_records,
  MIN(m.minute_ts) AT TIME ZONE 'America/New_York' as first_minute_edt,
  MAX(m.minute_ts) AT TIME ZONE 'America/New_York' as last_minute_edt,
  ROUND(EXTRACT(EPOCH FROM (NOW() - d.start_time)) / 60, 0) as expected_minutes,
  ROUND((COUNT(*) * 100.0 / EXTRACT(EPOCH FROM (NOW() - d.start_time)) * 60)::NUMERIC, 1) as completeness_percent
FROM minute_readings m
CROSS JOIN discovery_time d
WHERE m.minute_ts >= d.start_time
GROUP BY m.thermostat_id, d.start_time
ORDER BY m.thermostat_id;
"

Write-Host ""
Write-Host "=== STEP 3: GAP ANALYSIS - Missing Minutes Since Discovery ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
),
minute_gaps AS (
  SELECT 
    m.thermostat_id,
    m.minute_ts,
    LAG(m.minute_ts) OVER (PARTITION BY m.thermostat_id ORDER BY m.minute_ts) as prev_minute,
    EXTRACT(EPOCH FROM (m.minute_ts - LAG(m.minute_ts) OVER (PARTITION BY m.thermostat_id ORDER BY m.minute_ts))) / 60 as gap_minutes
  FROM minute_readings m
  CROSS JOIN discovery_time d
  WHERE m.minute_ts >= d.start_time
),
significant_gaps AS (
  SELECT 
    thermostat_id,
    prev_minute AT TIME ZONE 'America/New_York' as gap_start_edt,
    minute_ts AT TIME ZONE 'America/New_York' as gap_end_edt,
    ROUND(gap_minutes::NUMERIC, 0) as missing_minutes,
    CASE 
      WHEN gap_minutes > 60 THEN '🔴 MAJOR GAP (>1hr)'
      WHEN gap_minutes > 10 THEN '🟡 LARGE GAP (>10min)' 
      WHEN gap_minutes > 2 THEN '🟠 SMALL GAP (>2min)'
      ELSE '🟢 NORMAL'
    END as severity
  FROM minute_gaps 
  WHERE gap_minutes > 2  -- Only show gaps > 2 minutes
)
SELECT 
  thermostat_id,
  gap_start_edt,
  gap_end_edt,
  missing_minutes,
  severity
FROM significant_gaps
ORDER BY missing_minutes DESC, thermostat_id
LIMIT 20;
"

Write-Host ""
Write-Host "=== STEP 4: ROLLUP SERVICE HEALTH - Expected vs Actual Minutes ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
),
expected_minutes AS (
  SELECT 
    generate_series(
      date_trunc('minute', d.start_time) + INTERVAL '1 minute',
      date_trunc('minute', NOW() - INTERVAL '1 minute'),
      '1 minute'::interval
    ) as expected_minute
  FROM discovery_time d
),
actual_minutes AS (
  SELECT DISTINCT m.minute_ts
  FROM minute_readings m
  CROSS JOIN discovery_time d
  WHERE m.minute_ts >= d.start_time
),
minute_completeness AS (
  SELECT 
    e.expected_minute,
    CASE WHEN a.minute_ts IS NULL THEN 'MISSING' ELSE 'PRESENT' END as status
  FROM expected_minutes e
  LEFT JOIN actual_minutes a ON e.expected_minute = a.minute_ts
)
SELECT 
  COUNT(*) as total_expected_minutes,
  COUNT(CASE WHEN status = 'PRESENT' THEN 1 END) as present_minutes,
  COUNT(CASE WHEN status = 'MISSING' THEN 1 END) as missing_minutes,
  ROUND((COUNT(CASE WHEN status = 'PRESENT' THEN 1 END) * 100.0 / COUNT(*))::NUMERIC, 1) as rollup_completeness_percent
FROM minute_completeness;
"

Write-Host ""
Write-Host "=== STEP 5: CONSISTENCY CHECK - Same Minutes Across Thermostats ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
),
minute_counts AS (
  SELECT 
    m.minute_ts,
    COUNT(*) as thermostat_count,
    COUNT(DISTINCT m.thermostat_id) as unique_thermostats,
    string_agg(m.thermostat_id, ', ' ORDER BY m.thermostat_id) as thermostat_list
  FROM minute_readings m
  CROSS JOIN discovery_time d
  WHERE m.minute_ts >= d.start_time
  GROUP BY m.minute_ts
),
inconsistent_minutes AS (
  SELECT 
    minute_ts AT TIME ZONE 'America/New_York' as minute_edt,
    thermostat_count,
    unique_thermostats,
    CASE 
      WHEN thermostat_count = 0 THEN '❌ NO DATA'
      WHEN thermostat_count < 4 THEN '🟡 MISSING SOME'
      WHEN thermostat_count = 4 THEN '✅ ALL PRESENT'
      ELSE '🔴 DUPLICATES'
    END as status,
    thermostat_list
  FROM minute_counts
  WHERE thermostat_count != 4  -- Expecting 4 thermostats
)
SELECT 
  minute_edt,
  thermostat_count,
  status,
  thermostat_list
FROM inconsistent_minutes
ORDER BY minute_edt DESC
LIMIT 20;
"

Write-Host ""
Write-Host "=== STEP 6: DATA QUALITY - Poll Counts Since Discovery ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
)
SELECT 
  m.thermostat_id,
  COUNT(*) as total_minutes,
  ROUND(AVG(m.poll_count)::NUMERIC, 1) as avg_polls_per_minute,
  MIN(m.poll_count) as min_polls,
  MAX(m.poll_count) as max_polls,
  SUM(m.poll_failures) as total_failures,
  ROUND((SUM(m.poll_failures) * 100.0 / NULLIF(SUM(m.poll_count), 0))::NUMERIC, 2) as failure_rate_percent,
  COUNT(CASE WHEN m.poll_count < 8 THEN 1 END) as minutes_with_low_polls
FROM minute_readings m
CROSS JOIN discovery_time d
WHERE m.minute_ts >= d.start_time
GROUP BY m.thermostat_id
ORDER BY m.thermostat_id;
"

Write-Host ""
Write-Host "=== STEP 7: Show Missing Minutes Since Discovery (if any) ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
),
expected_minutes AS (
  SELECT 
    generate_series(
      date_trunc('minute', d.start_time) + INTERVAL '1 minute',
      date_trunc('minute', NOW() - INTERVAL '1 minute'),
      '1 minute'::interval
    ) as expected_minute
  FROM discovery_time d
),
missing_minutes AS (
  SELECT e.expected_minute
  FROM expected_minutes e
  LEFT JOIN (
    SELECT DISTINCT m.minute_ts 
    FROM minute_readings m
    CROSS JOIN discovery_time d2
    WHERE m.minute_ts >= d2.start_time
  ) a ON e.expected_minute = a.minute_ts
  WHERE a.minute_ts IS NULL
)
SELECT 
  expected_minute AT TIME ZONE 'America/New_York' as missing_minute_edt,
  'ROLLUP SERVICE FAILED' as issue
FROM missing_minutes
ORDER BY expected_minute DESC
LIMIT 10;
"

Write-Host ""
Write-Host "=== STEP 8: Recent Pattern (Last 30 Minutes from Discovery) ==="
docker exec -it thermostat_cape_db psql -U postgres -d thermostat_db -c "
WITH discovery_time AS (
  SELECT MAX(last_seen) as start_time FROM thermostats
)
SELECT 
  m.minute_ts AT TIME ZONE 'America/New_York' as minute_edt,
  COUNT(*) as thermostat_count,
  string_agg(
    m.thermostat_id || ':' || m.poll_count::text, 
    ', ' ORDER BY m.thermostat_id
  ) as polls_per_thermostat,
  CASE 
    WHEN COUNT(*) = 4 THEN '✅'
    WHEN COUNT(*) = 3 THEN '🟡'
    WHEN COUNT(*) = 2 THEN '🟠'
    WHEN COUNT(*) = 1 THEN '🔴'
    ELSE '❌'
  END as completeness
FROM minute_readings m
CROSS JOIN discovery_time d
WHERE m.minute_ts >= d.start_time 
  AND m.minute_ts > NOW() - INTERVAL '30 minutes'
GROUP BY m.minute_ts
ORDER BY m.minute_ts DESC
LIMIT 30;
"

Write-Host ""
Write-Host "=== ANALYSIS COMPLETE ==="
Write-Host "Analysis starts from actual discovery/registration time"
Write-Host "Expected: 1 minute record per thermostat per minute (4 total per minute)"
Write-Host "Expected poll count: ~8 per minute (7.5-second actual polling)"