#!/bin/bash
# ======================================
# vLLM Startup Script (Ollama-Compatibility Proxy Backend)
# ======================================

# --------- CONSTANTS / CONFIG ---------
CONST_GPU_ID=${CONST_GPU_ID:-0}                # GPU ID (default: 0)
VLLM_PORT=${VLLM_PORT:-8000}                   # vLLM listening port
VLLM_HOST_IP=""
VLLM_MODEL_PATH="${VLLM_MODEL_PATH:-}"         # Optional local HF model dir
VLLM_MODEL_NAME="${VLLM_MODEL_NAME:-unsloth/medgemma-27b-text-it-unsloth-bnb-4bit}"

# Number of GPUs if multi-GPU (default: 1)
VLLM_GPU_COUNT="${VLLM_GPU_COUNT:-1}"

# Log file
LOGFILE="vllm.log"


# --------- PRECHECKS ---------

echo ">>> Checking for existing vLLM server on port $VLLM_PORT..."
PID=$(lsof -t -i :$VLLM_PORT)
if [ -n "$PID" ]; then
  echo ">>> Port $VLLM_PORT in use by PID $PID. Killing..."
  kill -9 $PID
  echo ">>> Process $PID terminated."
else
  echo ">>> Port $VLLM_PORT is free."
fi


# --------- GPU CONFIG ---------

export CUDA_VISIBLE_DEVICES=$CONST_GPU_ID
echo ">>> Using GPU ID(s): $CUDA_VISIBLE_DEVICES"


# --------- IP / HOST DISCOVERY ---------

# Prefer cluster-style IP (your 172.18.x.x logic)
VLLM_HOST_IP=$(ip a | grep 'inet ' | grep -oP '172\.18\.\d+\.\d+' | head -n 1)
[ -z "$VLLM_HOST_IP" ] && VLLM_HOST_IP="127.0.0.1"

echo ">>> vLLM will bind to: $VLLM_HOST_IP:$VLLM_PORT"


# --------- MODEL PATH CHECK ---------

if [ -n "$VLLM_MODEL_PATH" ]; then
  if [ -d "$VLLM_MODEL_PATH" ]; then
    echo ">>> Using local model path: $VLLM_MODEL_PATH"
  else
    echo ">>> ERROR: VLLM_MODEL_PATH '$VLLM_MODEL_PATH' does not exist."
    exit 1
  fi
fi


# --------- REMOVE OLD GPU LOCKS ---------

rm -f /tmp/gpu_*_lock
echo ">>> GPU locks cleared."


# --------- STARTUP BANNER ---------

echo ""
echo "+-------------------------------------------+"
echo "|                                           |"
echo "|   vLLM Server Backend for Ollama Proxy    |"
echo "|                                           |"
echo "|  Address:                                 |"
echo "|  http://$VLLM_HOST_IP:$VLLM_PORT/v1/models           |"
echo "|                                           |"
echo "|  Example Direct Call (OpenAI API):        |"
echo "|  curl --noproxy '*' \\                    |"
echo "|    -X POST http://$VLLM_HOST_IP:$VLLM_PORT/v1/chat/completions \\"
echo "|    -H 'Content-Type: application/json' \\  |"
echo "|    -d '{\"model\": \"$VLLM_MODEL_NAME\", \"messages\": [{\"role\": \"user\", \"content\": \"hello\"}]}'"
echo "|                                           |"
echo "+-------------------------------------------+"
echo ""


# --------- START vLLM SERVER ---------

echo ">>> Starting vLLM server..."

CMD="python3 -m vllm.entrypoints.openai.api_server \
  --host 0.0.0.0 \
  --port $VLLM_PORT \
  --tensor-parallel-size $VLLM_GPU_COUNT \
  --model $VLLM_MODEL_NAME"

# Add --model-path if provided
if [ -n "$VLLM_MODEL_PATH" ]; then
  CMD="$CMD --model-path $VLLM_MODEL_PATH"
fi

echo ">>> Command:"
echo "$CMD"
echo ""

# Launch (nohup background)
nohup $CMD > $LOGFILE 2>&1 &

sleep 1
disown

echo ">>> vLLM server started. Listening on port $VLLM_PORT"
echo ">>> Log: $(pwd)/$LOGFILE"
echo ""
echo "To stop vLLM: kill -9 \$(lsof -t -i :$VLLM_PORT)"
echo ""
echo "***** SECURITY NOTICE *****"
echo ">>> vLLM is running locally. Use your HTTPS proxy for external access."
echo ""
