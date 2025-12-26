# ThermostatLocalServer - Quick Reference Guide

Quick reference for common operations and troubleshooting.

---

## Quick Start

```bash
# 1. Navigate to project
cd /opt/ThermostatLocalServer

# 2. Check PostgreSQL container
docker ps | grep postgres

# 3. Start server
./deployment/06-start-server.sh

# Or with systemd
sudo systemctl start thermostat-local
```

---

## Service Management

### Systemd Commands

```bash
# Start service
sudo systemctl start thermostat-local

# Stop service
sudo systemctl stop thermostat-local

# Restart service
sudo systemctl restart thermostat-local

# Check status
sudo systemctl status thermostat-local

# Enable auto-start on boot
sudo systemctl enable thermostat-local

# Disable auto-start
sudo systemctl disable thermostat-local

# View logs (follow)
sudo journalctl -u thermostat-local -f

# View recent logs
sudo journalctl -u thermostat-local -n 100

# View logs since boot
sudo journalctl -u thermostat-local -b
```

### Manual Operation

```bash
# Activate virtual environment
source .venv/bin/activate

# Run server
python -m src.main

# Run with specific config
CONFIG_FILE=config/config-nh.yaml python -m src.main

# Deactivate virtual environment
deactivate
```

---

## Database Operations

### PostgreSQL Container Management

```bash
# List containers
docker ps -a

# Start container
docker start postgres_cape

# Stop container
docker stop postgres_cape

# Restart container
docker restart postgres_cape

# View logs
docker logs postgres_cape
docker logs -f postgres_cape  # Follow logs

# Remove container (WARNING: destroys data)
docker rm -f postgres_cape
```

### Database Access

```bash
# Connect to database
docker exec -it postgres_cape psql -U postgres thermostat_db

# Execute query from command line
docker exec postgres_cape psql -U postgres thermostat_db -c "SELECT * FROM thermostats;"

# Execute SQL file
docker exec -i postgres_cape psql -U postgres thermostat_db < script.sql
```

### Common Queries

```sql
-- List all thermostats
SELECT thermostat_id, name, ip_address, active, last_seen 
FROM thermostats 
ORDER BY name;

-- Get current status
SELECT t.name, cs.temp, cs.t_heat, cs.tmode, cs.tstate, cs.ts
FROM current_state cs
JOIN thermostats t ON cs.thermostat_id = t.thermostat_id
WHERE t.active = true
ORDER BY t.name;

-- Check raw reading count
SELECT COUNT(*) FROM raw_readings;

-- Check minute reading count
SELECT COUNT(*) FROM minute_readings;

-- Get recent readings
SELECT thermostat_id, ts, temp, t_heat, tmode, tstate 
FROM raw_readings 
WHERE ts > NOW() - INTERVAL '1 hour'
ORDER BY ts DESC
LIMIT 100;

-- Get HVAC runtime for today
SELECT thermostat_id, 
       AVG(hvac_runtime_percent) as avg_runtime,
       COUNT(*) as minutes
FROM minute_readings
WHERE minute_ts >= CURRENT_DATE
GROUP BY thermostat_id;

-- Check database size
SELECT pg_database_size('thermostat_db') / 1024 / 1024 as size_mb;

-- Vacuum database
VACUUM ANALYZE;
```

### Backup & Restore

```bash
# Create backup
docker exec postgres_cape pg_dump -U postgres thermostat_db > backup_$(date +%Y%m%d).sql

# Restore from backup
docker exec -i postgres_cape psql -U postgres thermostat_db < backup_20241224.sql

# Create compressed backup
docker exec postgres_cape pg_dump -U postgres thermostat_db | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore from compressed backup
gunzip -c backup_20241224.sql.gz | docker exec -i postgres_cape psql -U postgres thermostat_db
```

---

## Configuration

### Switch Location

```powershell
# From Windows PowerShell
.\switch-location.ps1 -Location cape
.\switch-location.ps1 -Location fram
.\switch-location.ps1 -Location nh
```

### View Current Config

```bash
# View active configuration
cat config/config.yaml

# View specific section
grep -A 10 "database:" config/config.yaml

# Check environment variables
cat .env
```

### Edit Configuration

```bash
# Edit main config
nano config/config.yaml

# Edit environment
nano .env

# Restart after changes
sudo systemctl restart thermostat-local
```

---

## Monitoring

### View Logs

```bash
# Application logs
tail -f logs/thermostat_server.log

# Last 100 lines
tail -n 100 logs/thermostat_server.log

# Search for errors
grep ERROR logs/thermostat_server.log

# Search for specific thermostat
grep "Living Room" logs/thermostat_server.log

# Systemd logs
sudo journalctl -u thermostat-local -f
```

### Check API

```bash
# List thermostats
curl http://localhost:8000/api/thermostats | jq

# System info
curl http://localhost:8000/api/system/info | jq

# Health check
curl http://localhost:8000/api/system/health | jq

# Weather status
curl http://localhost:8000/api/weather/status | jq

# Get thermostat status (replace ID)
curl http://localhost:8000/api/thermostats/YOUR_ID_HERE/status | jq
```

### Monitor Processes

```bash
# Check if running
ps aux | grep python | grep thermostat

# Check CPU/memory usage
top -p $(pgrep -f "python.*thermostat")

# Detailed process info
ps -ef | grep thermostat

# Check network connections
netstat -tulpn | grep python
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check systemd status
sudo systemctl status thermostat-local

# Check logs
sudo journalctl -u thermostat-local -n 50

# Try manual start to see errors
cd /opt/ThermostatLocalServer
source .venv/bin/activate
python -m src.main
```

**Common Issues**:
- Database not running: `docker start postgres_cape`
- Config file missing: Check `config/config.yaml` exists
- Permission errors: Check file ownership
- Port already in use: Change port in config or kill process

### No Thermostats Discovered

```bash
# Test UDP discovery (from Windows)
.\tests\Discover-TstatsUDP.ps1

# Test TCP scan
.\tests\Scan-Tstats.ps1

# Check IP ranges in config
grep "ip_ranges:" config/config.yaml

# Test network connectivity
ping 10.0.60.1

# Check firewall
sudo ufw status
```

**Solutions**:
- Enable TCP discovery in config
- Verify IP ranges are correct
- Check network connectivity
- Ensure thermostats are on same network
- Check for firewall blocking UDP/TCP

### Database Connection Failed

```bash
# Check container running
docker ps | grep postgres

# Check container logs
docker logs postgres_cape

# Test connection
docker exec postgres_cape psql -U postgres -c "SELECT 1"

# Restart container
docker restart postgres_cape

# Check port mapping
docker port postgres_cape
```

**Solutions**:
- Start PostgreSQL container
- Verify port in config matches container
- Check password in `.env` matches container
- Rebuild container if corrupted

### Public Server Sync Issues

```bash
# Check logs for sync errors
grep "public server" logs/thermostat_server.log | tail -n 50

# Test connectivity
curl -k https://your-server.com:8001/api/health

# Verify SSL certificate
ls -l certs/thermo-ca.crt

# Check site token
grep PUBLIC_SERVER_TOKEN .env
```

**Solutions**:
- Verify base_url in config
- Check SSL certificate exists and valid
- Verify site token is correct
- Check network allows HTTPS outbound
- Disable SSL verification temporarily for testing

### High CPU/Memory Usage

```bash
# Check process usage
top -p $(pgrep -f thermostat)

# Check database connections
docker exec postgres_cape psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check log file size
ls -lh logs/thermostat_server.log
```

**Solutions**:
- Increase polling interval (>5 seconds)
- Rotate log files
- Clean old database data
- Reduce number of thermostats
- Check for infinite loops in logs

### Weather Service Not Working

```bash
# Check weather status
curl http://localhost:8000/api/weather/status | jq

# Test OpenWeatherMap API
curl "https://api.openweathermap.org/data/2.5/weather?zip=02632,US&appid=YOUR_KEY&units=imperial"

# Check config
grep -A 5 "weather:" config/config.yaml

# Check API key
grep WEATHER_API_KEY .env
```

**Solutions**:
- Verify API key is valid
- Check zip code is correct
- Disable weather service if not needed
- Check API rate limits
- Use fallback temperature

---

## Common Tasks

### Add New Thermostat

Thermostats are discovered automatically. To force discovery:

```bash
# Trigger manual discovery
curl -X POST http://localhost:8000/api/discovery/scan

# Or restart service
sudo systemctl restart thermostat-local
```

### Change Thermostat Temperature

```bash
# Via API
curl -X POST http://localhost:8000/api/thermostats/THERMOSTAT_ID/temperature \
  -H "Content-Type: application/json" \
  -d '{"t_heat": 72.0, "hold": true}'

# Or directly (if on local network)
curl -X POST http://10.0.60.1/tstat \
  -H "Content-Type: application/json" \
  -d '{"tmode": 1, "t_heat": 72.0, "hold": 1}'
```

### View Current Status

```bash
# All thermostats
curl http://localhost:8000/api/site/status | jq

# Specific thermostat
curl http://localhost:8000/api/thermostats/THERMOSTAT_ID/status | jq

# From database
docker exec postgres_cape psql -U postgres thermostat_db -c \
  "SELECT t.name, cs.temp, cs.t_heat, cs.tmode FROM current_state cs 
   JOIN thermostats t ON cs.thermostat_id = t.thermostat_id;"
```

### Clean Old Data

```bash
# From database (manual cleanup)
docker exec postgres_cape psql -U postgres thermostat_db -c \
  "DELETE FROM raw_readings WHERE ts < NOW() - INTERVAL '14 days';"

docker exec postgres_cape psql -U postgres thermostat_db -c \
  "DELETE FROM minute_readings WHERE minute_ts < NOW() - INTERVAL '365 days';"

# Vacuum database
docker exec postgres_cape psql -U postgres thermostat_db -c "VACUUM ANALYZE;"
```

Note: Automatic cleanup runs daily at 2 AM.

### Update Application

```bash
# Pull latest code
cd /opt/ThermostatLocalServer
git pull

# Update dependencies
source .venv/bin/activate
pip install -r requirements.txt

# Restart service
sudo systemctl restart thermostat-local
```

---

## Emergency Procedures

### Complete Reset

**WARNING**: This will delete all data!

```bash
# Stop service
sudo systemctl stop thermostat-local

# Remove database container
docker rm -f postgres_cape

# Remove data directory
sudo rm -rf data/postgres_cape

# Recreate database
./deployment/02-setup-postgres.sh

# Start service
sudo systemctl start thermostat-local
```

### Restore from Backup

```bash
# Stop service
sudo systemctl stop thermostat-local

# Restore database
./deployment/03-restore-database.sh backup_20241224.sql

# Start service
sudo systemctl start thermostat-local
```

### Network Issues

```bash
# Restart networking
sudo systemctl restart networking

# Flush DNS
sudo systemd-resolve --flush-caches

# Check routes
ip route show

# Test connectivity
ping -c 3 10.0.60.1
```

---

## Performance Checks

### Database Performance

```sql
-- Table sizes
SELECT 
    schemaname || '.' || tablename AS table,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Index usage
SELECT 
    schemaname || '.' || tablename AS table,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Slow queries
SELECT 
    query,
    calls,
    total_time,
    mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

### Application Performance

```bash
# Check polling interval
grep "Polling performance:" logs/thermostat_server.log | tail -n 10

# Check sync statistics
grep "Sync Stats" logs/thermostat_server.log | tail -n 10

# Check discovery timing
grep "Enhanced discovery complete" logs/thermostat_server.log | tail -n 5
```

---

## Useful Commands

### Search Logs

```bash
# Find all errors
grep -i error logs/thermostat_server.log

# Find warnings
grep -i warning logs/thermostat_server.log

# Find specific thermostat
grep "Living Room" logs/thermostat_server.log

# Find database errors
grep -i "database" logs/thermostat_server.log | grep -i error

# Find network errors
grep -i "connection" logs/thermostat_server.log

# Count errors by type
grep -i error logs/thermostat_server.log | cut -d':' -f4 | sort | uniq -c
```

### System Info

```bash
# Disk usage
df -h

# Check data directory size
du -sh data/postgres_*

# Check log file size
du -sh logs/

# Memory usage
free -h

# CPU info
lscpu
```

### Network Testing

```bash
# Test thermostat connectivity
for ip in 10.0.60.{1..10}; do
  echo -n "$ip: "
  curl -s --max-time 2 http://$ip/sys/name | jq -r .name || echo "No response"
done

# Test public server
curl -k -I https://your-server.com:8001

# Check open ports
sudo netstat -tulpn | grep LISTEN
```

---

## API Examples

### List Thermostats

```bash
curl http://localhost:8000/api/thermostats | jq '.[].name'
```

### Set Temperature (All Thermostats)

```bash
# Get all IDs
IDS=$(curl -s http://localhost:8000/api/thermostats | jq -r '.[].thermostat_id')

# Set each to 70°F
for id in $IDS; do
  curl -X POST http://localhost:8000/api/thermostats/$id/temperature \
    -H "Content-Type: application/json" \
    -d '{"t_heat": 70.0, "hold": true}'
done
```

### Set Mode (Single Thermostat)

```bash
# Set to HEAT mode (1)
curl -X POST http://localhost:8000/api/thermostats/THERMOSTAT_ID/mode \
  -H "Content-Type: application/json" \
  -d '{"tmode": 1}'

# Set to OFF mode (0)
curl -X POST http://localhost:8000/api/thermostats/THERMOSTAT_ID/mode \
  -H "Content-Type: application/json" \
  -d '{"tmode": 0}'
```

---

## Configuration Examples

### Minimal Configuration

```yaml
site:
  site_id: "my_site"
  site_name: "My Home"
  timezone: "America/New_York"

network:
  ip_ranges:
    - "192.168.1.1-192.168.1.254"

polling:
  status_interval_seconds: 5

database:
  host: "localhost"
  port: 5432
  database: "thermostat_db"
  username: "postgres"
  password: "postgres"

public_server:
  enabled: false

weather:
  enabled: false
```

### Production Configuration

See `config/config.yaml.template` for full example with all options.

---

*Quick Reference Guide - Last updated December 2024*
