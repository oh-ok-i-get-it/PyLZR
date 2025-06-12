#!/usr/bin/env bash

set -e

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

sourc .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e .
exec pylzr


