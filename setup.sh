#!/bin/bash

# AI Legal Reasoning System - Setup Script

echo "=== AI Legal Reasoning System Setup ==="

# Check Python version
echo "\n1. Checking Python..."
python3 --version

# Install pip if not available
echo "\n2. Installing pip (requires sudo)..."
if ! command -v pip3 &> /dev/null; then
    echo "pip3 not found. Installing..."
    sudo apt update && sudo apt install -y python3-pip
else
    echo "pip3 already installed"
fi

# Install dependencies
echo "\n3. Installing Python dependencies..."
pip3 install -r requirements.txt

echo "\n=== Setup Complete ==="
echo "\nTo run the application:"
echo "  streamlit run src/ui/app.py"
