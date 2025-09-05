#!/bin/bash
set -e

# Check if this is first run (setup needed)
if [ ! -d "venv" ] || [ ! -f "certificates/cert.pem" ]; then
    echo "Setting up HTTPS proxy..."
    
    # Load Python if available
    module load python 2>/dev/null || true
    
    # Create directories
    mkdir -p certificates src
    
    # Generate SSL cert
    if [ ! -f "certificates/cert.pem" ]; then
        openssl req -x509 -newkey rsa:2048 -nodes \
            -out certificates/cert.pem \
            -keyout certificates/key.pem \
            -days 365 \
            -subj "/CN=localhost"
        echo "SSL certificates created"
    fi
    
    # Create venv and install deps
    if [ ! -d "venv" ]; then
        python -m venv venv
    fi
    
    source venv/bin/activate
    pip install fastapi uvicorn httpx
    
    echo "Setup complete."
fi

# Load Python module
module load python

# Activate virtual environment  
source venv/bin/activate

# Start HTTPS proxy to Ollama
uvicorn src.middleware:app --host 0.0.0.0 --port 8000 \
    --ssl-keyfile certificates/key.pem \
    --ssl-certfile certificates/cert.pem
