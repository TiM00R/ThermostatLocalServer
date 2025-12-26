#!/bin/bash

# Restore existing PostgreSQL database data
# Fixed version: works from deployment folder and handles stopped containers

set -e

# Get project root (parent of deployment folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Script dir: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"
echo "Restoring existing database data..."

CONTAINER_NAME="thermostat_postgres"
SOURCE_DATA_DIR="$PROJECT_ROOT/data"

# Check if container exists
if ! docker ps -a | grep -q $CONTAINER_NAME; then
    echo "Error: PostgreSQL container '$CONTAINER_NAME' does not exist"
    echo "Please run deployment/02-setup-postgres.sh first"
    exit 1
fi

# Only stop container if it's actually running
if docker ps | grep -q $CONTAINER_NAME; then
    echo "Stopping PostgreSQL container..."
    docker stop $CONTAINER_NAME
else
    echo "Container is already stopped"
fi

# Check for existing database directories
echo "Looking for database folders in: $SOURCE_DATA_DIR"

if [ -d "$SOURCE_DATA_DIR/postgres_cape" ]; then
    echo "✓ Found Cape database data"
    CAPE_DATA="$SOURCE_DATA_DIR/postgres_cape"
fi

if [ -d "$SOURCE_DATA_DIR/postgres_fram" ]; then
    echo "✓ Found Fram database data"
    FRAM_DATA="$SOURCE_DATA_DIR/postgres_fram"
fi

if [ -d "$SOURCE_DATA_DIR/postgres_nh" ]; then
    echo "✓ Found NH database data"
    NH_DATA="$SOURCE_DATA_DIR/postgres_nh"
fi

# Check if any database was found
if [ -z "$CAPE_DATA" ] && [ -z "$FRAM_DATA" ] && [ -z "$NH_DATA" ]; then
    echo "Error: No database folders found in $SOURCE_DATA_DIR"
    echo "Looking for: postgres_cape, postgres_fram, postgres_nh"
    echo "Contents of data directory:"
    ls -la "$SOURCE_DATA_DIR" 2>/dev/null || echo "Data directory does not exist"
    exit 1
fi

# Prompt user to select which database to restore
echo ""
echo "Available databases:"
[ -n "$CAPE_DATA" ] && echo "1) Cape (postgres_cape)"
[ -n "$FRAM_DATA" ] && echo "2) Fram (postgres_fram)"
[ -n "$NH_DATA" ] && echo "3) NH (postgres_nh)"

read -p "Select database to restore (1/2/3): " choice

case $choice in
    1)
        if [ -n "$CAPE_DATA" ]; then
            SOURCE_DB_DIR="$CAPE_DATA"
            echo "Selected Cape database"
        else
            echo "Cape database not found"
            exit 1
        fi
        ;;
    2)
        if [ -n "$FRAM_DATA" ]; then
            SOURCE_DB_DIR="$FRAM_DATA"
            echo "Selected Fram database"
        else
            echo "Fram database not found"
            exit 1
        fi
        ;;
    3)
        if [ -n "$NH_DATA" ]; then
            SOURCE_DB_DIR="$NH_DATA"
            echo "Selected NH database"
        else
            echo "NH database not found"
            exit 1
        fi
        ;;
    *)
        echo "Invalid selection"
        exit 1
        ;;
esac

# Create container data directory if it doesn't exist
CONTAINER_DATA_DIR="$PROJECT_ROOT/data/postgres_data"
mkdir -p "$CONTAINER_DATA_DIR"

# Copy database data
echo "Copying database data from $SOURCE_DB_DIR to $CONTAINER_DATA_DIR..."
sudo rm -rf "$CONTAINER_DATA_DIR"/*
sudo cp -r "$SOURCE_DB_DIR"/* "$CONTAINER_DATA_DIR"/

# Set correct permissions
sudo chown -R 999:999 "$CONTAINER_DATA_DIR"

# Start container
echo "Starting PostgreSQL container..."
docker start $CONTAINER_NAME

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
sleep 15

# Test connection
echo "Testing database connection..."
if docker exec $CONTAINER_NAME pg_isready -U postgres -d thermostat_db; then
    echo "✓ Database restoration completed successfully"
else
    echo "✗ Database connection failed - check container logs:"
    docker logs --tail 10 $CONTAINER_NAME
    exit 1
fi
