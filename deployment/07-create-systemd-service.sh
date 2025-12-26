#!/bin/bash

# Create systemd service for thermostat local server
# This script creates a systemd service that will run the thermostat server automatically at boot
# Run this script once to set up the service

set -e

echo "Setting up systemd service for thermostat local server..."

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "Project directory: $PROJECT_DIR"

# Define service file path
SERVICE_FILE="/etc/systemd/system/thermostat-local.service"

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run with sudo"
    echo "Usage: sudo ./07-create-systemd-service.sh"
    exit 1
fi

# Function to print help commands
print_help() {
    echo ""
    echo "=========================================="
    echo "Thermostat Local Server - Service Commands"
    echo "=========================================="
    echo ""
    echo "Service file: $SERVICE_FILE"
    echo "Project directory: $PROJECT_DIR"
    echo ""
    echo "Service Management Commands:"
    echo ""
    echo "  # Start the service:"
    echo "  sudo systemctl start thermostat-local.service"
    echo ""
    echo "  # Stop the service:"
    echo "  sudo systemctl stop thermostat-local.service"
    echo ""
    echo "  # Restart the service:"
    echo "  sudo systemctl restart thermostat-local.service"
    echo ""
    echo "  # Check service status:"
    echo "  sudo systemctl status thermostat-local.service"
    echo ""
    echo "  # View service logs (live):"
    echo "  sudo journalctl -u thermostat-local.service -f"
    echo ""
    echo "  # View service logs (last 100 lines):"
    echo "  sudo journalctl -u thermostat-local.service -n 100"
    echo ""
    echo "  # Enable service to start at boot:"
    echo "  sudo systemctl enable thermostat-local.service"
    echo ""
    echo "  # Disable service from starting at boot:"
    echo "  sudo systemctl disable thermostat-local.service"
    echo ""
    echo "  # Reload systemd configuration:"
    echo "  sudo systemctl daemon-reload"
    echo ""
    echo "=========================================="
    echo ""
}

# Check if service already exists
if [ -f "$SERVICE_FILE" ]; then
    echo ""
    echo "Service already exists: $SERVICE_FILE"
    echo ""
    echo "To recreate the service, first remove it with:"
    echo "  sudo systemctl stop thermostat-local.service"
    echo "  sudo systemctl disable thermostat-local.service"
    echo "  sudo rm $SERVICE_FILE"
    echo "  sudo systemctl daemon-reload"
    echo ""
    echo "Then run this script again."
    exit 0
fi

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project directory not found: $PROJECT_DIR"
    exit 1
fi

# Check if venv exists
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "Error: Virtual environment not found"
    echo "Please run 05-install-packages.sh first"
    exit 1
fi

# Check if source directory exists
if [ ! -d "$PROJECT_DIR/src" ]; then
    echo "Error: Source directory not found: $PROJECT_DIR/src"
    exit 1
fi

# Check if main.py exists
if [ ! -f "$PROJECT_DIR/src/main.py" ]; then
    echo "Error: main.py not found: $PROJECT_DIR/src/main.py"
    exit 1
fi

# Check if config directory exists
if [ ! -d "$PROJECT_DIR/config" ]; then
    echo "Error: Config directory not found: $PROJECT_DIR/config"
    exit 1
fi

# Find the first .yaml file in the config directory
CONFIG_FILE_FULL=$(ls "$PROJECT_DIR/config"/*.yaml 2>/dev/null | head -n 1)

if [ -z "$CONFIG_FILE_FULL" ]; then
    echo "Error: No .yaml config files found in $PROJECT_DIR/config/"
    echo "Please ensure there is at least one .yaml config file"
    exit 1
fi

# Get the relative path from project directory (config/filename.yaml)
CONFIG_FILE="$PROJECT_DIR/config/$(basename "$CONFIG_FILE_FULL")"

echo "Using config file: $CONFIG_FILE"

# Create the systemd service file
echo "Creating service file: $SERVICE_FILE"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Thermostat Local Server
After=network.target docker.service
Requires=docker.service
Wants=network-online.target

[Service]
Type=exec
User=$SUDO_USER
Group=$SUDO_USER
WorkingDirectory=$PROJECT_DIR
Environment=PYTHONPATH=$PROJECT_DIR/src
Environment=CONFIG_FILE=$CONFIG_FILE

# Wait for PostgreSQL container
ExecStartPre=/bin/sleep 10
ExecStartPre=/usr/bin/docker ps -q -f name=thermostat_postgres

# Start the application by running src/main.py directly
ExecStart=$PROJECT_DIR/venv/bin/python src/main.py

# Restart policy
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=thermostat-local

[Install]
WantedBy=multi-user.target
EOF

# Set proper permissions
chmod 644 "$SERVICE_FILE"

echo ""
echo "Service file created successfully!"
echo ""

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable the service (but don't start it)
echo "Enabling service to start at boot..."
systemctl enable thermostat-local.service

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Service has been created and enabled for auto-start at boot."
echo "The service is NOT started yet."
echo ""
echo "IMPORTANT: Make sure PostgreSQL container is running before starting!"
echo "Check with: docker ps | grep thermostat_postgres"
echo ""

print_help
