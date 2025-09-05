#!/bin/bash
set -e

# --------- CONSTANTS / CONFIG ---------
PROXY_PORT=${PROXY_PORT:-11443}   # Proxy HTTPS port (default: 11443)

# Load Python module if available (for HPC clusters)
module load python 2>/dev/null || true

# Find a valid Python interpreter
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "Python is not installed."
    exit 1
fi

# --------- SETUP CHECK ---------
if [ ! -d "venv" ] || [ ! -f "certificates/cert.pem" ]; then
    echo "Setting up HTTPS proxy..."

    mkdir -p certificates

    # Generate SSL cert if missing
    if [ ! -f "certificates/cert.pem" ]; then
        openssl req -x509 -newkey rsa:2048 -nodes \
            -out certificates/cert.pem \
            -keyout certificates/key.pem \
            -days 365 \
            -subj "/CN=localhost"
    fi

    # Create venv
    $PYTHON -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install fastapi uvicorn httpx

    echo "Setup complete."
fi

# --------- ACTIVATE VENV ---------
source venv/bin/activate

# --------- START PROXY ---------
echo ">>> Starting HTTPS proxy on port $PROXY_PORT..."
uvicorn proxy:app --host 0.0.0.0 --port $PROXY_PORT \
    --ssl-keyfile certificates/key.pem \
    --ssl-certfile certificates/cert.pem
