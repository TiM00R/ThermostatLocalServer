#!/bin/bash

# Setup PostgreSQL container for thermostat project
# Uses PostgreSQL 15 with thermostat_db database

set -e

echo "Setting up PostgreSQL container..."

# Container configuration
CONTAINER_NAME="thermostat_postgres"
DB_NAME="thermostat_db"
DB_USER="postgres"
DB_PASSWORD="postgres"
DB_PORT="5433"
DATA_DIR="./data/postgres_data"

# Stop and remove existing container if it exists
if docker ps -a | grep -q $CONTAINER_NAME; then
    echo "Stopping and removing existing container..."
    docker stop $CONTAINER_NAME || true
    docker rm $CONTAINER_NAME || true
fi

# Create data directory
mkdir -p $DATA_DIR

# Run PostgreSQL container
echo "Starting PostgreSQL container..."
docker run -d \
    --name $CONTAINER_NAME \
    -e POSTGRES_DB=$DB_NAME \
    -e POSTGRES_USER=$DB_USER \
    -e POSTGRES_PASSWORD=$DB_PASSWORD \
    -p $DB_PORT:5432 \
    -v "$(pwd)/$DATA_DIR:/var/lib/postgresql/data" \
    --restart unless-stopped \
    postgres:15

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
sleep 10

# Test connection
docker exec $CONTAINER_NAME pg_isready -U $DB_USER -d $DB_NAME

echo "PostgreSQL container setup completed"
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Password: $DB_PASSWORD"
echo "Port: $DB_PORT"
echo "Container: $CONTAINER_NAME"
