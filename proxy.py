from fastapi import FastAPI, Request
from fastapi.responses import Response
import httpx
import logging
import time

app = FastAPI()

# Simple logging
logging.basicConfig(filename="api_usage.log", level=logging.INFO)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    logging.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logging.info(f"Completed in {time.time() - start:.2f}s")
    return response

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    
    async with httpx.AsyncClient() as client:
        response = await client.request(
            request.method,
            f"http://localhost:11434/{path}",
            headers=headers,
            content=body,
            params=request.query_params
        )
    
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers)
    )
