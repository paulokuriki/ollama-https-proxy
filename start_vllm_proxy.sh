#!/bin/bash
set -e

# --------- CONSTANTS / CONFIG ---------
PROXY_PORT=${PROXY_PORT:-11443}   # Proxy HTTPS port (default: 11443)
PROXY_MODULE=${PROXY_MODULE:-ollamify_vllm_proxy}  # Python module with FastAPI app

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
if [ ! -d "venv" ] || [ ! -f "certificates/cert.pem" ] || [ ! -f "certificates/key.pem" ]; then
    echo ">>> Setting up HTTPS proxy environment..."

    mkdir -p certificates

    # Generate SSL cert if missing
    if [ ! -f "certificates/cert.pem" ] || [ ! -f "certificates/key.pem" ]; then
        echo ">>> Generating self-signed TLS certificate..."
        openssl req -x509 -newkey rsa:2048 -nodes \
            -out certificates/cert.pem \
            -keyout certificates/key.pem \
            -days 365 \
            -subj "/CN=localhost"
    fi

    # Create venv
    echo ">>> Creating Python virtual environment..."
    $PYTHON -m venv venv
    source venv/bin/activate

    echo ">>> Installing Python dependencies (FastAPI + vLLM)..."
    pip install --upgrade pip wheel setuptools

    # Core proxy deps
    pip install fastapi uvicorn httpx

    # Install vLLM (GPU version, works for both CUDA 11.8 and CUDA 12.x)
    pip install "vllm[gpu]"

    echo ">>> Setup complete."
else
    echo ">>> Existing venv and certificates found. Skipping setup."
fi

# --------- ACTIVATE VENV ---------
source venv/bin/activate

# --------- START PROXY ---------
echo ">>> Starting HTTPS proxy on port $PROXY_PORT using module '$PROXY_MODULE'..."
uvicorn ${PROXY_MODULE}:app --host 0.0.0.0 --port $PROXY_PORT \
    --ssl-keyfile certificates/key.pem \
    --ssl-certfile certificates/cert.pem
