#!/bin/bash

# Install Python packages from requirements.txt
# This script creates a virtual environment and installs all required packages

set -e

echo "Installing Python packages for thermostat project..."

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "Error: requirements.txt not found"
    echo "Please ensure you are in the project root directory"
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
python3.12 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install packages from requirements.txt
echo "Installing packages from requirements.txt..."
pip install -r requirements.txt

# Verify key packages
echo "Verifying installation..."
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import asyncpg; print(f'asyncpg: {asyncpg.__version__}')"
python -c "import aiohttp; print(f'aiohttp: {aiohttp.__version__}')"
python -c "import uvicorn; print(f'uvicorn: {uvicorn.__version__}')"

echo "Python packages installation completed successfully"
echo ""
echo "To activate the virtual environment in the future, run:"
echo "source venv/bin/activate"
echo ""
echo "To deactivate the virtual environment, run:"
echo "deactivate"
