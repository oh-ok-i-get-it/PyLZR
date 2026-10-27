#!/usr/bin/env bash
set -e

# ANSI color codes
RESET="\e[0m"
BOLD="\e[1m"
UNDERLINE="\e[4m"
ITALICS="\e[3m"
ITALICS_OFF="\e[23m"
RED="\e[31m"
GREEN="\e[32m"
YELLOW="\e[33m"
BLUE="\e[34m"
MAGENTA="\e[35m"
CYAN="\e[36m"

# Print color text helper
color_print() {
  local color=$1; shift
  printf "%b\n" "${color}$*${RESET}"
}

# Hash a file using Python (cross-platform; `python` always exists inside the venv)
file_hash() {
  python -c "import hashlib; print(hashlib.sha256(open('$1','rb').read()).hexdigest())"
}

# Find a working system Python. Windows usually has `python` rather than
# `python3`, and may have a non-functional `python3` Store alias — so test each.
PY=""
for candidate in python3 python; do
    if "$candidate" -c "import sys" &> /dev/null; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    color_print "$RED${BOLD}" "No working python3/python found on PATH."
    exit 1
fi

# Create the venv if needed
VENV_IS_NEW=false
if [ ! -d ".venv" ]; then
    color_print "$BLUE${BOLD}${ITALICS}" "Creating virtual environment..."
    "$PY" -m venv .venv
    color_print "$GREEN${BOLD}" "Virtual environment created successfully.\n"
    VENV_IS_NEW=true
else
    color_print "$YELLOW${BOLD}" "Virtual environment already exists.\n"
fi

# Activate venv
color_print "$BLUE${BOLD}${ITALICS}" "Activating virtual environment..."
# venv layout differs: bin/ on macOS/Linux, Scripts/ on Windows (Git Bash)
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    source .venv/Scripts/activate
fi
color_print "$GREEN${BOLD}" "Virtual environment activated successfully.\n"


# Upgrade pip/setuptools/wheel only on fresh venv
if [ "$VENV_IS_NEW" = true ]; then
    color_print "$BLUE${BOLD}${ITALICS}" "Upgrading pip, setuptools, and wheel..."
    pip install --upgrade pip setuptools wheel
    color_print "$GREEN${BOLD}" "Upgraded successfully.\n"
fi


# Install dependencies only if requirements.txt has changed
REQ_HASH_FILE=".venv/.req_hash"
CURRENT_REQ_HASH=$(file_hash requirements.txt)
if [ ! -f "$REQ_HASH_FILE" ] || [ "$(cat "$REQ_HASH_FILE")" != "$CURRENT_REQ_HASH" ]; then
    color_print "$BLUE${BOLD}${ITALICS}" "Installing requirements.txt dependencies..."
    pip install -r requirements.txt
    echo "$CURRENT_REQ_HASH" > "$REQ_HASH_FILE"
    color_print "$GREEN${BOLD}" "Dependencies installed successfully.\n"
else
    color_print "$YELLOW${BOLD}" "Dependencies up to date, skipping install.\n"
fi


# Install in editable mode only if pyproject.toml has changed
PKG_HASH_FILE=".venv/.pkg_hash"
CURRENT_PKG_HASH=$(file_hash pyproject.toml)
if [ ! -f "$PKG_HASH_FILE" ] || [ "$(cat "$PKG_HASH_FILE")" != "$CURRENT_PKG_HASH" ]; then
    color_print "$BLUE${BOLD}${ITALICS}" "Installing PyLZR in editable mode..."
    pip install -e .
    echo "$CURRENT_PKG_HASH" > "$PKG_HASH_FILE"
    color_print "$GREEN${BOLD}" "PyLZR installed successfully.\n"
else
    color_print "$YELLOW${BOLD}" "PyLZR package up to date, skipping install.\n"
fi


# Launch
color_print "\n${MAGENTA}${BOLD}${ITALICS}" "Launching ${CYAN}${ITALICS_OFF}PyLZR...\n"

if command -v pylzr &> /dev/null; then
    color_print "$GREEN${BOLD}" "${ITALICS}pylzr ${ITALICS_OFF}${YELLOW}command found - running installed entry-point. \n\tProceeding to execute...\n"
    exec pylzr "$@"
else
    color_print "$RED${BOLD}" "${ITALICS}pylzr ${ITALICS_OFF}${YELLOW}command not found - running module directly. \n\tProceeding to execute...\n"
    exec python -m pylzr "$@"
fi
