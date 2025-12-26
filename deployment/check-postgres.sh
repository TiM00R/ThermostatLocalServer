#!/bin/bash

# Check PostgreSQL container status and health
# Run this after 02-setup-postgres.sh and before 03-restore-database.sh

echo "Checking PostgreSQL container status..."

CONTAINER_NAME="thermostat_postgres"

# Check if container exists and is running
echo "=== Container Status ==="
docker ps -a | grep $CONTAINER_NAME

# Check if container is running (not just exists)
if docker ps | grep -q $CONTAINER_NAME; then
    echo "✓ Container is running"
else
    echo "✗ Container is not running"
    echo "Starting container..."
    docker start $CONTAINER_NAME
    sleep 5
fi

# Check PostgreSQL readiness
echo ""
echo "=== PostgreSQL Health Check ==="
if docker exec $CONTAINER_NAME pg_isready -U postgres -d thermostat_db; then
    echo "✓ PostgreSQL is ready"
else
    echo "✗ PostgreSQL is not ready"
    exit 1
fi

# Test database connection
echo ""
echo "=== Database Connection Test ==="
docker exec $CONTAINER_NAME psql -U postgres -d thermostat_db -c "SELECT version();"

# Show container logs (last 10 lines)
echo ""
echo "=== Recent Container Logs ==="
docker logs --tail 10 $CONTAINER_NAME

# Show container details
echo ""
echo "=== Container Details ==="
docker inspect $CONTAINER_NAME | grep -E '"IPAddress"|"Ports"' -A 5

echo ""
echo "Container check completed successfully"
echo "You can now proceed with 03-restore-database.sh"
