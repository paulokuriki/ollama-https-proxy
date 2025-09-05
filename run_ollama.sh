#!/bin/bash
# ======================================
# Final Ollama Startup Script for Radiology RAG System
# ======================================

# --------- CONSTANTS / CONFIG ---------
CONST_GPU_ID=${CONST_GPU_ID:-0}                 # GPU ID (default: 0)
OLLAMA_PORT=${OLLAMA_PORT:-11434}               # Default Ollama port (can override if supported)
OLLAMA_REQUIRES_SUDO=0                          # 1 = force sudo, 0 = no check

# Optional: Set OLLAMA_MODELS_DIR manually if needed
OLLAMA_MODELS_DIR="/project/radiology/Kuriki_lab/shared/ollama_models"

# --------- PRECHECKS ---------
if [ "$OLLAMA_REQUIRES_SUDO" -eq 1 ] && [ "$EUID" -ne 0 ]; then
  echo ">>> ERROR: Please run with sudo (or set OLLAMA_REQUIRES_SUDO=0)."
  exit 1
fi

# Kill any running Ollama processes
echo ">>> Stopping any existing Ollama processes..."
pkill -f "ollama serve" 2>/dev/null
pkill -x ollama 2>/dev/null
systemctl disable --now ollama.service 2>/dev/null

# GPU setup
export CUDA_VISIBLE_DEVICES=$CONST_GPU_ID
echo ">>> Using GPU ID: $CONST_GPU_ID"

# Check if port is in use and free it if necessary
PID=$(lsof -t -i :$OLLAMA_PORT)
if [ -n "$PID" ]; then
  echo ">>> Port $OLLAMA_PORT is in use by PID $PID. Killing the process..."
  kill -9 $PID
  echo ">>> Process $PID killed."
else
  echo ">>> Port $OLLAMA_PORT is free."
fi

# Set host dynamically (prefer cluster IP, fallback to localhost)
OLLAMA_IP=$(ip a | grep 'inet ' | grep -oP '172\.18\.\d+\.\d+' | head -n 1)
[ -z "$OLLAMA_IP" ] && OLLAMA_IP="127.0.0.1"
export OLLAMA_HOST=$OLLAMA_IP:$OLLAMA_PORT

# Verify models directory only if provided
if [ -n "$OLLAMA_MODELS_DIR" ]; then
  if [ -d "$OLLAMA_MODELS_DIR" ]; then
    echo ">>> Verified: directory exists at $OLLAMA_MODELS_DIR."
  else
    echo ">>> ERROR: OLLAMA_MODELS directory $OLLAMA_MODELS_DIR does not exist."
    echo ">>> Please create the directory or unset OLLAMA_MODELS_DIR."
    exit 1
  fi
fi

# Remove GPU locks
rm -f /tmp/gpu_*_lock

# Load required modules (ignore errors if not available)
echo ">>> Loading required modules..."
module load gpu_prepare || true
module load ollama || true

# --------- STARTUP INFO ---------
echo ""
echo "+-------------------------------------------+"
echo "|                                           |"
echo "|  Copy Ollama address:                     |"
echo "|  http://$OLLAMA_IP:$OLLAMA_PORT/api/generate  |"
echo "|                                           |"
echo "|  Example Pull Model:                      |"
echo "|  curl --noproxy '*' http://$OLLAMA_IP:$OLLAMA_PORT/api/pull -d '{\"name\": \"phi4:14b\"}'"
echo "|                                           |"
echo "|  Example Test Model:                      |"
echo "|  curl --noproxy '*' http://$OLLAMA_IP:$OLLAMA_PORT/api/generate -d '{\"model\": \"phi4:14b\", \"prompt\": \"hi\", \"stream\": false}'"
echo "|                                           |"
echo "+-------------------------------------------+"
echo ""

# --------- START SERVER ---------
echo ">>> Starting Ollama API server..."
if [ -n "$OLLAMA_MODELS_DIR" ]; then
  OLLAMA_MODELS=$OLLAMA_MODELS_DIR \
  CUDA_VISIBLE_DEVICES=$CONST_GPU_ID \
  OLLAMA_HOST=$OLLAMA_HOST \
  ollama serve > ollama.log 2>&1 &
else
  CUDA_VISIBLE_DEVICES=$CONST_GPU_ID \
  OLLAMA_HOST=$OLLAMA_HOST \
  ollama serve > ollama.log 2>&1 &
fi

disown

echo ">>> Ollama API server started successfully (port $OLLAMA_PORT)."
echo ">>> Server log available at: $(pwd)/ollama.log"
echo ">>> To stop Ollama, run: kill -9 \$(lsof -t -i :$OLLAMA_PORT)"
echo ""
echo "*****  SECURITY NOTICE  *****"
echo ">>> This Ollama instance is only accessible locally ($OLLAMA_HOST)."
echo ">>> To expose it externally, use a reverse proxy with HTTPS."
echo ""
