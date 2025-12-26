#!/bin/bash

# Make all deployment scripts executable
# Run this first after copying files to Ubuntu server

echo "Making deployment scripts executable..."

chmod +x deployment/01-install-docker.sh
chmod +x deployment/02-setup-postgres.sh
chmod +x deployment/03-restore-database.sh
chmod +x deployment/04-install-python.sh
chmod +x deployment/05-install-packages.sh
chmod +x deployment/06-start-server.sh

echo "All deployment scripts are now executable"
echo ""
echo "Run the scripts in order:"
echo "1. ./deployment/01-install-docker.sh"
echo "2. ./deployment/02-setup-postgres.sh"
echo "3. ./deployment/03-restore-database.sh"
echo "4. ./deployment/04-install-python.sh"
echo "5. ./deployment/05-install-packages.sh"
echo "6. ./deployment/06-start-server.sh"
