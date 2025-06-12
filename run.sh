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

# Create the venv if needed
if [ ! -d ".venv" ]; then
    color_print "$BLUE${BOLD}${ITALICS}" "Creating virtual environment..."
    python3 -m venv .venv
    color_print "$GREEN${BOLD}" "Virtual environment created successfully.\n"
else
    color_print "$YELLOW${BOLD}" "Virtual environment already exists.\n"
fi

# Activate venv
color_print "$BLUE${BOLD}${ITALICS}" "Activating virtual environment..."
source .venv/bin/activate
color_print "$GREEN${BOLD}" "Virtual environment activated successfully.\n"


# Upgrade pip/setuptools/wheel
color_print "$BLUE${BOLD}${ITALICS}" "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel
color_print "$GREEN${BOLD}" "Upgraded successfully.\n"


# Install dependencies
color_print "$BLUE${BOLD}${ITALICS}" "Installing requirements.txt dependencies..."
pip install -r requirements.txt
color_print "$GREEN${BOLD}" "Dependencies installed successfully.\n"


# Install in editable mode
color_print "$BLUE${BOLD}${ITALICS}" "Installing PyLZR in editable mode..."
pip install -e .
color_print "$GREEN${BOLD}" "PyLZR installed successfully.\n"


# Launch 
color_print "\n${MAGENTA}${BOLD}${ITALICS}" "Launching ${CYAN}${ITALICS_OFF}PyLZR...\n"

if command -v pylzr &> /dev/null; then
    color_print "$GREEN${BOLD}" "${ITALICS}pylzr ${ITALICS_OFF}${YELLOW}command found - running installed entry-point. \n\tProceeding to execute...\n"
    exec pylzr "$@"
else
    color_print "$RED${BOLD}" "${ITALICS}pylzr ${ITALICS_OFF}${YELLOW}command not found - running module directly. \n\tProceeding to execute...\n"
    exec -m pylzr "$@"
fi

