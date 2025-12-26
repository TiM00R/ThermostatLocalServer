#!/bin/bash

# Install Python 3.12 and pip on Ubuntu 22.04
# Fixed version: python3.12-distutils doesn't exist

set -e

echo "Installing Python 3.12 and pip..."

# Update package index
sudo apt-get update

# Install software-properties-common for PPA support
sudo apt-get install -y software-properties-common

# Add deadsnakes PPA for Python 3.12
sudo add-apt-repository -y ppa:deadsnakes/ppa

# Update package index after adding PPA
sudo apt-get update

# Install Python 3.12 and related packages
# Note: python3.12-distutils doesn't exist (distutils removed in 3.12)
sudo apt-get install -y \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    curl

# Install pip for Python 3.12
echo "Installing pip for Python 3.12..."
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

# Create symlinks for convenience
sudo ln -sf /usr/bin/python3.12 /usr/local/bin/python3
sudo ln -sf /usr/bin/python3.12 /usr/local/bin/python

# Verify installation
echo "Verifying installation..."
python3.12 --version
python3.12 -m pip --version

echo "Python 3.12 and pip installation completed successfully"
echo "Note: distutils was removed in Python 3.12 - setuptools is used instead"
