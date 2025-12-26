#!/bin/bash

# Debug script to find database folders and project structure
# Run this to see what folders exist and where

echo "=== Current Directory ==="
pwd
echo ""

echo "=== Files in Current Directory ==="
ls -la
echo ""

echo "=== Looking for data/ folder ==="
if [ -d "data" ]; then
    echo "✓ Found data/ folder in current directory"
    echo "Contents of data/:"
    ls -la data/
    echo ""
    
    echo "=== Looking for PostgreSQL database folders ==="
    if [ -d "data/postgres_cape" ]; then
        echo "✓ Found data/postgres_cape/"
        echo "Size: $(du -sh data/postgres_cape/ | cut -f1)"
    else
        echo "✗ data/postgres_cape/ not found"
    fi
    
    if [ -d "data/postgres_fram" ]; then
        echo "✓ Found data/postgres_fram/"
        echo "Size: $(du -sh data/postgres_fram/ | cut -f1)"
    else
        echo "✗ data/postgres_fram/ not found"
    fi
    
    if [ -d "data/postgres_nh" ]; then
        echo "✓ Found data/postgres_nh/"
        echo "Size: $(du -sh data/postgres_nh/ | cut -f1)"
    else
        echo "✗ data/postgres_nh/ not found"
    fi
    
    if [ -d "data/postgres_data" ]; then
        echo "✓ Found data/postgres_data/ (container data)"
        echo "Size: $(du -sh data/postgres_data/ | cut -f1)"
    else
        echo "✗ data/postgres_data/ not found (will be created by container)"
    fi
else
    echo "✗ data/ folder not found in current directory"
    echo ""
    echo "=== Searching for data/ folder in nearby directories ==="
    find . -name "data" -type d 2>/dev/null | head -5
    echo ""
    echo "=== Searching for postgres database folders ==="
    find . -name "postgres_*" -type d 2>/dev/null | head -10
fi

echo ""
echo "=== Looking for other project files ==="
if [ -f "requirements.txt" ]; then
    echo "✓ Found requirements.txt"
else
    echo "✗ requirements.txt not found"
fi

if [ -d "src" ]; then
    echo "✓ Found src/ folder"
else
    echo "✗ src/ folder not found"
fi

if [ -d "config" ]; then
    echo "✓ Found config/ folder"
    echo "Config files:"
    ls -la config/*.yaml 2>/dev/null || echo "No .yaml files found"
else
    echo "✗ config/ folder not found"
fi

if [ -d "deployment" ]; then
    echo "✓ Found deployment/ folder"
else
    echo "✗ deployment/ folder not found"
fi

echo ""
echo "=== Full directory tree (2 levels) ==="
tree -L 2 2>/dev/null || find . -type d -name ".*" -prune -o -type d -print | head -20
