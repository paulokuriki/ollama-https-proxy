#!/bin/bash

# Ensure the script is run with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo."
  exit 1
fi

# Kill any running ollama processes
pkill -f "ollama serve" 2>/dev/null
pkill -x ollama 2>/dev/null

# Disable autostart if using systemd
systemctl disable --now ollama.service 2>/dev/null

# Environment variables
# export CUDA_VISIBLE_DEVICES=0
# export OLLAMA_HOST=0.0.0.0
# export OLLAMA_ORIGINS="*"
export OLLAMA_PORT=11123

# Start Ollama
ollama serve
