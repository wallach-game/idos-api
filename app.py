from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from collections import defaultdict
import asyncio
import time
import os

RATE_LIMIT   = 10    # per-IP requests per window
RATE_WINDOW  = 60    # seconds
GLOBAL_LIMIT = 5000  # total requests per 24 hours
CONCURRENCY  = 3     # max simultaneous browser pages

_hits: dict        = defaultdict(list)
_global_hits: list = []
_global_sem        = None   # set on startup (asyncio not available at import)
_ip_sems: dict     = {}
_ip_sems_lock      = None

def check_rate(ip: str) -> None:
    now = time.time()

    # per-IP sliding window
    _hits[ip] = [t for t in _hits[ip] if now - t < RATE_WINDOW]
    if len(_hits[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _hits[ip].append(now)

    # global daily hard limit
    global _global_hits
    _global_hits = [t for t in _global_hits if now - t < 86400]
    if len(_global_hits) >= GLOBAL_LIMIT:
        raise HTTPException(status_code=429, detail="Global daily limit reached")
    _global_hits.append(now)

async def acquire(ip: str | None):
    # round-robin: max 1 concurrent request per IP, max CONCURRENCY total
    if ip:
        if ip not in _ip_sems:
            async with _ip_sems_lock:
                if ip not in _ip_sems:
                    _ip_sems[ip] = asyncio.Semaphore(1)
        await _ip_sems[ip].acquire()
    await _global_sem.acquire()

def release(ip: str | None):
    _global_sem.release()
    if ip and ip in _ip_sems:
        _ip_sems[ip].release()

os.environ["DISPLAY"] = ":0"

app = FastAPI(
    openapi_url="/api/openapi.json",
    title="IDOS API",
    description=(
        "Scrapes [idos.cz](https://idos.cz) and returns public transport connections.\n\n"
        "**Rate limiting:** 10 requests per 60 seconds per IP (via `CF-Connecting-IP`). "
        "Direct/local access has no limit.\n\n"
        f"**Hard limit:** {GLOBAL_LIMIT} total requests per 24 hours across all users.\n\n"
        f"**Concurrency:** max {CONCURRENCY} simultaneous requests, 1 per IP (round-robin)."
    ),
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])
browser = None

@app.on_event("startup")
async def startup_event():
    global browser, _global_sem, _ip_sems_lock
    _global_sem   = asyncio.Semaphore(CONCURRENCY)
    _ip_sems_lock = asyncio.Lock()
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
    try:
        from routes import router
        app.include_router(router)
    except ImportError:
        pass
