from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from collections import defaultdict
import time
import os

RATE_LIMIT = 10   # requests per window
RATE_WINDOW = 60  # seconds

_hits: dict = defaultdict(list)

def check_rate(ip: str) -> None:
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < RATE_WINDOW]
    if len(_hits[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _hits[ip].append(now)

os.environ["DISPLAY"] = ":0"

app = FastAPI(
    openapi_url="/api/openapi.json",
    title="IDOS API",
    description=(
        "Scrapes [idos.cz](https://idos.cz) and returns public transport connections.\n\n"
        "**Rate limiting:** 10 requests per 60 seconds per IP (via `CF-Connecting-IP`). "
        "Direct/local access has no limit."
    ),
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])
browser = None

@app.on_event("startup")
async def startup_event():
    global browser
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
    try:
        from routes import router
        app.include_router(router)
    except ImportError:
        pass
