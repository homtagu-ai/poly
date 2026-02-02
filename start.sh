#!/bin/bash
# Startup script for Hosting Ukraine (poly-hunter.com)
# This script is referenced in the hosting panel's startup command

cd "$(dirname "$0")"
source .venv/bin/activate
exec python3.10 polyscalping/server.py
