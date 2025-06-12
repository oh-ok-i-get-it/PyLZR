#!/usr/bin/env bash

set -e

# Create the venv if needed
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate venv
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip/setuptools/wheel
echo "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel

# Install in editable mode
echo "Installing PyLZR in editable mode..."
pip install -e .

# Launch 
echo "Launching PyLZR..."
exec pylzr "$@"
