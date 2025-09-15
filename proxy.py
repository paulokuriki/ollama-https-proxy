import os
import logging
import time
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response
import httpx
import asyncio

# Clear proxy settings if needed
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""

app = FastAPI()

OLLAMA_URL = "http://localhost"
OLLAMA_PORT = 11434
PROXY_PORT = 11443

# Timeout configuration
TIMEOUT_SECONDS = 300  # 5 minutes for long-running requests
CONNECT_TIMEOUT = 10  # Connection timeout
READ_TIMEOUT = 300  # Read timeout for streaming responses

# Configure logging
logging.basicConfig(
    filename="api_usage.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # silence httpx noise


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()

    # Log the incoming request
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


async def stream_response(response):
    """Stream the response content chunk by chunk"""
    try:
        async for chunk in response.aiter_bytes(chunk_size=8192):
            yield chunk
    except Exception as e:
        logging.error(f"Streaming error: {e}")
        raise


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    headers = dict(request.headers)
    headers.pop("host", None)

    # Read the request body
    body = await request.body()

    # Configure timeout
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=READ_TIMEOUT,
        write=None,
        pool=None
    )

    # Check if this is a streaming endpoint
    is_streaming = path == "api/chat" and request.method == "POST"

    try:
        if is_streaming:
            # For streaming responses, use a streaming approach
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Make the request with stream=True
                async with client.stream(
                        request.method,
                        f"{OLLAMA_URL}:{OLLAMA_PORT}/{path}",
                        headers=headers,
                        content=body,
                        params=request.query_params
                ) as response:
                    # Return a streaming response
                    return StreamingResponse(
                        stream_response(response),
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.headers.get("content-type", "application/json")
                    )
        else:
            # For non-streaming endpoints, use regular request
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    request.method,
                    f"{OLLAMA_URL}:{OLLAMA_PORT}/{path}",
                    headers=headers,
                    content=body,
                    params=request.query_params
                )

                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )

    except httpx.ReadTimeout:
        logging.error(f"Timeout on {path} after {READ_TIMEOUT}s")
        return Response(
            content=f"Request timeout: Ollama took longer than {READ_TIMEOUT} seconds to respond",
            status_code=504,  # Gateway Timeout
            headers={"content-type": "text/plain"}
        )
    except httpx.ConnectTimeout:
        logging.error(f"Connection timeout to Ollama on {path}")
        return Response(
            content="Connection timeout: Could not connect to Ollama backend",
            status_code=503,  # Service Unavailable
            headers={"content-type": "text/plain"}
        )
    except httpx.HTTPError as e:
        logging.error(f"HTTP error on {path}: {e}")
        return Response(
            content=f"Proxy error: {str(e)}",
            status_code=502,  # Bad Gateway
            headers={"content-type": "text/plain"}
        )
    except Exception as e:
        logging.error(f"Unexpected error on {path}: {e}")
        return Response(
            content=f"Internal proxy error: {str(e)}",
            status_code=500,
            headers={"content-type": "text/plain"}
        )


@app.get("/health")
async def health_check():
    """Health check endpoint for the proxy"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(f"{OLLAMA_URL}:{OLLAMA_PORT}/api/tags")
            if response.status_code == 200:
                return {"status": "healthy", "ollama": "connected"}
    except:
        pass
    return {"status": "unhealthy", "ollama": "disconnected"}, 503


@app.on_event("startup")
async def startup_event():
    import socket
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "127.0.0.1"

    BOX_WIDTH = 70  # total width inside +---...---+

    def box_line(text=""):
        return "| " + text.ljust(BOX_WIDTH - 3) + "|"

    print("")
    print("+" + "-" * (BOX_WIDTH - 2) + "+")
    print(box_line("OLLAMA PROXY IS RUNNING"))
    print(box_line())
    print(box_line(f"Local:  http://127.0.0.1:{PROXY_PORT}"))
    print(box_line(f"LAN:    https://{ip}:{PROXY_PORT}"))
    print(box_line())
    print(box_line(f"Timeout: {READ_TIMEOUT}s for streaming requests"))
    print(box_line(f"Health:  https://{ip}:{PROXY_PORT}/health"))
    print(box_line())
    print(box_line("Example:"))
    print(box_line(f"curl -k --noproxy '*' https://{ip}:{PROXY_PORT}/api/tags"))
    print("+" + "-" * (BOX_WIDTH - 2) + "+")
    print("")

    # Test Ollama connection
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(f"{OLLAMA_URL}:{OLLAMA_PORT}/api/tags")
            if response.status_code == 200:
                print(f"✓ Successfully connected to Ollama at {OLLAMA_URL}:{OLLAMA_PORT}")
            else:
                print(f"⚠ Ollama responded with status {response.status_code}")
    except Exception as e:
        print(f"✗ Could not connect to Ollama: {e}")
        print(f"  Make sure Ollama is running on {OLLAMA_URL}:{OLLAMA_PORT}")


if __name__ == "__main__":
    import uvicorn

    # Run with SSL support if certificates are available
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