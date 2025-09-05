import os
import logging
import time
from fastapi import FastAPI, Request
from fastapi.responses import Response
import httpx

# Clear proxy settings if needed
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""

app = FastAPI()

OLLAMA_URL = "http://localhost"
OLLAMA_PORT = 11434
PROXY_PORT = 11443

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
    response = await call_next(request)
    duration = time.time() - start
    logging.info(
        f"{request.client.host} {request.method} {request.url.path} "
        f"? {response.status_code} ({duration:.2f}s)"
    )
    return response


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()

    async with httpx.AsyncClient() as client:
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
    print(box_line(f"Local:  http://127.0.0.1:{OLLAMA_PORT}"))
    print(box_line(f"LAN:    https://{ip}:{PROXY_PORT}"))
    print(box_line())
    print(box_line("Example:"))
    print(box_line(f"curl -k --noproxy '*'  https://{ip}:{PROXY_PORT}/api/tags"))
    print("+" + "-" * (BOX_WIDTH - 2) + "+")
    print("")
