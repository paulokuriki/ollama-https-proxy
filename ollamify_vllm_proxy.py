import os
import logging
import time
import json
from typing import Dict, Any, AsyncGenerator, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response
import httpx

# Clear proxy settings if needed
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""

app = FastAPI()

# ===============================
# CONFIG
# ===============================

# vLLM server (OpenAI-compatible)
VLLM_URL = "http://localhost:8000"  # where you run vLLM
VLLM_MODEL = "unsloth/medgemma-27b-text-it-unsloth-bnb-4bit"  # or any other

# What your clients think they're talking to (Ollama-style proxy)
PROXY_PORT = 11443

# Timeout configuration
TIMEOUT_SECONDS = 300  # 5 minutes for long-running requests (doc only)
CONNECT_TIMEOUT = 10   # Connection timeout
READ_TIMEOUT = 300     # Read timeout for streaming responses

# Configure logging
logging.basicConfig(
    filename="api_usage.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # silence httpx noise


# ===============================
# LOGGING MIDDLEWARE
# ===============================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()

    body_size = int(request.headers.get("content-length", 0))
    logging.info(
        f"REQUEST: {request.client.host} {request.method} {request.url.path} "
        f"(body: {body_size} bytes)"
    )

    try:
        response = await call_next(request)
        duration = time.time() - start
        logging.info(
            f"RESPONSE: {request.client.host} {request.method} {request.url.path} "
            f"→ {response.status_code} ({duration:.2f}s)"
        )
        return response
    except Exception as e:
        duration = time.time() - start
        logging.error(
            f"ERROR: {request.client.host} {request.method} {request.url.path} "
            f"→ {type(e).__name__}: {str(e)} ({duration:.2f}s)"
        )
        raise


# ===============================
# HELPERS
# ===============================

def map_options(options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map Ollama-style options -> vLLM/OpenAI-style."""
    if not options:
        return {}
    out: Dict[str, Any] = {}
    if "temperature" in options:
        out["temperature"] = options["temperature"]
    if "top_p" in options:
        out["top_p"] = options["top_p"]
    # Ollama num_predict ~= max_tokens
    if "num_predict" in options:
        out["max_tokens"] = options["num_predict"]
    if "max_tokens" in options:
        out["max_tokens"] = options["max_tokens"]
    # extend here if you use other options (top_k, presence_penalty, etc.)
    return out


def json_response(content: dict, status_code: int = 200) -> Response:
    return Response(
        content=json.dumps(content),
        status_code=status_code,
        media_type="application/json"
    )


async def vllm_chat_request(payload: Dict[str, Any], stream: bool):
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=READ_TIMEOUT,
        write=None,
        pool=None,
    )
    client = httpx.AsyncClient(timeout=timeout)
    if stream:
        # Return client and a stream context manager for the caller
        return client, client.stream("POST", f"{VLLM_URL}/v1/chat/completions", json=payload)
    else:
        try:
            r = await client.post(f"{VLLM_URL}/v1/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
            await client.aclose()
            return data
        except Exception:
            await client.aclose()
            raise


# ===============================
# HEALTH CHECK (define BEFORE catch-all)
# ===============================

@app.get("/health")
async def health_check():
    """Health check against vLLM /v1/models."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(f"{VLLM_URL}/v1/models")
            if response.status_code == 200:
                return {"status": "healthy", "backend": "vllm"}
    except Exception:
        pass
    return Response(
        content=json.dumps({"status": "unhealthy", "backend": "disconnected"}),
        status_code=503,
        media_type="application/json"
    )


# ===============================
# MAIN PROXY ROUTE
# ===============================

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    """
    Frontend:
      - Exposes Ollama-style endpoints: /api/chat, /api/generate, /api/tags, etc.
      - Also accepts OpenAI/vLLM-style requests on /v1/...
    Backend:
      - Talks to vLLM's /v1/chat/completions and /v1/models
    """

    # Read the request body once
    body = await request.body()

    # Parse JSON if possible
    json_body: Optional[Dict[str, Any]] = None
    if body and request.headers.get("content-type", "").startswith("application/json"):
        try:
            json_body = json.loads(body)
        except json.JSONDecodeError:
            json_body = None

    # Detect streaming (for any JSON POST)
    is_streaming = False
    if request.method == "POST" and json_body:
        is_streaming = bool(json_body.get("stream", False))
        if is_streaming:
            logging.info(
                f"Streaming request detected for /{path} "
                f"(model: {json_body.get('model', 'unknown')})"
            )

    # ---------------------------
    # /api/chat (Ollama) -> vLLM chat/completions
    # ---------------------------

    if path == "api/chat" and request.method == "POST" and json_body:
        messages = json_body.get("messages", [])
        options = json_body.get("options", {})
        ollama_model = json_body.get("model", "ollama-model")

        # Build vLLM payload
        payload: Dict[str, Any] = {
            "model": VLLM_MODEL,
            "messages": messages,
            "stream": is_streaming,
        }
        payload.update(map_options(options))

        # Non-streaming: single response
        if not is_streaming:
            try:
                data = await vllm_chat_request(payload, stream=False)
            except httpx.HTTPError as e:
                logging.error(f"vLLM error /api/chat: {e}")
                return json_response(
                    {"error": f"Backend vLLM error: {str(e)}"}, status_code=502
                )

            content = data["choices"][0]["message"]["content"]
            finish_reason = data["choices"][0].get("finish_reason", "stop")
            usage = data.get("usage", {})

            ollama_resp = {
                "model": ollama_model,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "done": True,
                "done_reason": finish_reason,
                # some stats for compatibility; they can be 0 if you don't care
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": usage.get("prompt_tokens", 0),
                "prompt_eval_duration": 0,
                "eval_count": usage.get("completion_tokens", 0),
                "eval_duration": 0,
            }
            return json_response(ollama_resp)

        # Streaming: convert vLLM SSE -> Ollama NDJSON
        async def chat_streamer() -> AsyncGenerator[bytes, None]:
            client, stream_ctx = await vllm_chat_request(payload, stream=True)
            async with stream_ctx as resp:
                try:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            final_obj = {
                                "model": ollama_model,
                                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                },
                                "done": True,
                                "done_reason": "stop",
                                "total_duration": 0,
                                "load_duration": 0,
                                "prompt_eval_count": 0,
                                "prompt_eval_duration": 0,
                                "eval_count": 0,
                                "eval_duration": 0,
                            }
                            yield (json.dumps(final_obj) + "\n").encode("utf-8")
                            break

                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk["choices"][0]["delta"]
                        piece = delta.get("content", "")
                        if not piece:
                            continue

                        obj = {
                            "model": ollama_model,
                            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "message": {
                                "role": "assistant",
                                "content": piece,
                            },
                            "done": False,
                        }
                        yield (json.dumps(obj) + "\n").encode("utf-8")
                finally:
                    await client.aclose()

        return StreamingResponse(
            chat_streamer(),
            media_type="application/x-ndjson",
        )

    # ---------------------------
    # /api/generate (Ollama) -> vLLM chat/completions
    # ---------------------------

    if path == "api/generate" and request.method == "POST" and json_body:
        prompt = json_body.get("prompt", "")
        options = json_body.get("options", {})
        ollama_model = json_body.get("model", "ollama-model")

        messages = [{"role": "user", "content": prompt}]

        payload: Dict[str, Any] = {
            "model": VLLM_MODEL,
            "messages": messages,
            "stream": is_streaming,
        }
        payload.update(map_options(options))

        if not is_streaming:
            try:
                data = await vllm_chat_request(payload, stream=False)
            except httpx.HTTPError as e:
                logging.error(f"vLLM error /api/generate: {e}")
                return json_response(
                    {"error": f"Backend vLLM error: {str(e)}"}, status_code=502
                )

            content = data["choices"][0]["message"]["content"]
            finish_reason = data["choices"][0].get("finish_reason", "stop")
            usage = data.get("usage", {})

            ollama_resp = {
                "model": ollama_model,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "response": content,
                "done": True,
                "done_reason": finish_reason,
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": usage.get("prompt_tokens", 0),
                "prompt_eval_duration": 0,
                "eval_count": usage.get("completion_tokens", 0),
                "eval_duration": 0,
            }
            return json_response(ollama_resp)

        async def generate_streamer() -> AsyncGenerator[bytes, None]:
            client, stream_ctx = await vllm_chat_request(payload, stream=True)
            async with stream_ctx as resp:
                try:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            final_obj = {
                                "model": ollama_model,
                                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "response": "",
                                "done": True,
                                "done_reason": "stop",
                                "total_duration": 0,
                                "load_duration": 0,
                                "prompt_eval_count": 0,
                                "prompt_eval_duration": 0,
                                "eval_count": 0,
                                "eval_duration": 0,
                            }
                            yield (json.dumps(final_obj) + "\n").encode("utf-8")
                            break

                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk["choices"][0]["delta"]
                        piece = delta.get("content", "")
                        if not piece:
                            continue

                        obj = {
                            "model": ollama_model,
                            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "response": piece,
                            "done": False,
                        }
                        yield (json.dumps(obj) + "\n").encode("utf-8")
                finally:
                    await client.aclose()

        return StreamingResponse(
            generate_streamer(),
            media_type="application/x-ndjson",
        )

    # ---------------------------
    # /api/tags -> fake a single model so UIs don’t freak out
    # ---------------------------

    if path == "api/tags" and request.method == "GET":
        return json_response({
            "models": [
                {
                    "name": "medgemma:27b",
                    "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "size": 0,
                    "digest": "",
                    "details": {
                        "parameter_size": "27B",
                        "quantization_level": "4bit",
                    },
                }
            ]
        })

    # ---------------------------
    # Fallback: vLLM /v1/... passthrough (supports OpenAI-style streaming)
    # ---------------------------

    headers = dict(request.headers)
    headers.pop("host", None)

    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=READ_TIMEOUT,
        write=None,
        pool=None
    )

    # Special-case OpenAI-style streaming on /v1/chat/completions and /v1/completions
    if (
        request.method == "POST"
        and json_body
        and is_streaming
        and path in ("v1/chat/completions", "v1/completions")
    ):
        client = httpx.AsyncClient(timeout=timeout)
        try:
            resp = await client.request(
                request.method,
                f"{VLLM_URL}/{path}",
                headers=headers,
                content=body,
                params=request.query_params,
                stream=True,
            )

            async def openai_streamer() -> AsyncGenerator[bytes, None]:
                try:
                    async for chunk in resp.aiter_bytes(1024):
                        if chunk:
                            # Pass bytes through unchanged (SSE or chunked JSON)
                            yield chunk
                finally:
                    await resp.aclose()
                    await client.aclose()

            return StreamingResponse(
                openai_streamer(),
                status_code=resp.status_code,
                headers=dict(resp.headers),
                media_type=resp.headers.get("content-type", "text/event-stream"),
            )
        except httpx.ReadTimeout:
            await client.aclose()
            logging.error(f"Timeout on /{path} after {READ_TIMEOUT}s (OpenAI streaming)")
            return Response(
                content=f"Request timeout: backend took longer than {READ_TIMEOUT} seconds to respond",
                status_code=504,
                headers={"content-type": "text/plain"},
            )
        except httpx.ConnectTimeout:
            await client.aclose()
            logging.error(f"Connection timeout to backend on /{path} (OpenAI streaming)")
            return Response(
                content="Connection timeout: Could not connect to backend",
                status_code=503,
                headers={"content-type": "text/plain"},
            )
        except httpx.HTTPError as e:
            await client.aclose()
            logging.error(f"HTTP error on /{path} (OpenAI streaming): {e}")
            return Response(
                content=f"Proxy error: {str(e)}",
                status_code=502,
                headers={"content-type": "text/plain"},
            )
        except Exception as e:
            await client.aclose()
            logging.error(f"Unexpected error on /{path} (OpenAI streaming): {e}")
            return Response(
                content=f"Internal proxy error: {str(e)}",
                status_code=500,
                headers={"content-type": "text/plain"},
            )

    # Non-streaming fallback: just forward to vLLM unchanged
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                request.method,
                f"{VLLM_URL}/{path}",
                headers=headers,
                content=body,
                params=request.query_params
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers)
        )
    except httpx.ReadTimeout:
        logging.error(f"Timeout on /{path} after {READ_TIMEOUT}s")
        return Response(
            content=f"Request timeout: backend took longer than {READ_TIMEOUT} seconds to respond",
            status_code=504,
            headers={"content-type": "text/plain"}
        )
    except httpx.ConnectTimeout:
        logging.error(f"Connection timeout to backend on /{path}")
        return Response(
            content="Connection timeout: Could not connect to backend",
            status_code=503,
            headers={"content-type": "text/plain"}
        )
    except httpx.HTTPError as e:
        logging.error(f"HTTP error on /{path}: {e}")
        return Response(
            content=f"Proxy error: {str(e)}",
            status_code=502,
            headers={"content-type": "text/plain"}
        )
    except Exception as e:
        logging.error(f"Unexpected error on /{path}: {e}")
        return Response(
            content=f"Internal proxy error: {str(e)}",
            status_code=500,
            headers={"content-type": "text/plain"}
        )


# ===============================
# STARTUP BANNER
# ===============================

@app.on_event("startup")
async def startup_event():
    import socket
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "127.0.0.1"

    BOX_WIDTH = 70

    def box_line(text=""):
        return "| " + text.ljust(BOX_WIDTH - 3) + "|"

    print("")
    print("+" + "-" * (BOX_WIDTH - 2) + "+")
    print(box_line("OLLAMA → vLLM PROXY IS RUNNING"))
    print(box_line())
    print(box_line(f"Local:  http://127.0.0.1:{PROXY_PORT}"))
    print(box_line(f"LAN:    https://{ip}:{PROXY_PORT}"))
    print(box_line())
    print(box_line(f"Timeout: {READ_TIMEOUT}s for streaming requests"))
    print(box_line(f"Health:  https://{ip}:{PROXY_PORT}/health"))
    print(box_line())
    print(box_line("Example (Ollama-style):"))
    print(box_line(f"curl -k --noproxy '*' https://{ip}:{PROXY_PORT}/api/tags"))
    print("+" + "-" * (BOX_WIDTH - 2) + "+")
    print("")

    # Quick backend check
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(f"{VLLM_URL}/v1/models")
            if response.status_code == 200:
                print(f"✓ Connected to vLLM at {VLLM_URL}")
            else:
                print(f"⚠ vLLM responded with status {response.status_code}")
    except Exception as e:
        print(f"✗ Could not connect to vLLM: {e}")
        print(f"  Make sure vLLM is running on {VLLM_URL}")


# ===============================
# MAIN
# ===============================

if __name__ == "__main__":
    import uvicorn
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=PROXY_PORT,
            ssl_keyfile="key.pem",
            ssl_certfile="cert.pem"
        )
    except FileNotFoundError:
        print("SSL certificates not found. Running without HTTPS.")
        print("To enable HTTPS, generate certificates with:")
        print("  openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365")
        uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT)
