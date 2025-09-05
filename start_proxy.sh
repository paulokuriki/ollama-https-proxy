#!/bin/bash
set -e

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

# Setup check
if [ ! -d "venv" ] || [ ! -f "certificates/cert.pem" ]; then
    echo "Setting up HTTPS proxy..."

    mkdir -p certificates src

    # Generate SSL cert
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

# Activate venv
source venv/bin/activate

# Start proxy
uvicorn proxy:app --host 0.0.0.0 --port 11443 \
    --ssl-keyfile certificates/key.pem \
    --ssl-certfile certificates/cert.pem
