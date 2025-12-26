#!/bin/bash

# Start the thermostat server application
# This script activates the virtual environment and starts the server

set -e

echo "Starting thermostat server..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found"
    echo "Please run 05-install-packages.sh first"
    exit 1
fi

# Check if PostgreSQL container is running
if ! docker ps | grep -q "thermostat_postgres"; then
    echo "Error: PostgreSQL container is not running"
    echo "Please run 02-setup-postgres.sh and 03-restore-database.sh first"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Set Python path
export PYTHONPATH="./src:$PYTHONPATH"

# Check if config file exists
CONFIG_FILE="config/config-cape.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Warning: Config file $CONFIG_FILE not found"
    echo "Available config files:"
    ls -la config/config*.yaml 2>/dev/null || echo "No config files found"
    read -p "Enter config file name (e.g., config-cape.yaml): " CONFIG_INPUT
    CONFIG_FILE="config/$CONFIG_INPUT"
    
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Error: Config file $CONFIG_FILE not found"
        exit 1
    fi
fi

echo "Using config file: $CONFIG_FILE"

# Create logs directory
mkdir -p logs

# Set environment variables
export CONFIG_FILE="$CONFIG_FILE"
export POSTGRES_HOST="localhost"
export POSTGRES_PORT="5432"
export POSTGRES_PASSWORD="postgres"

# Start the server
echo "Starting thermostat server with config: $CONFIG_FILE"
python src/main.py

echo "Server stopped"
