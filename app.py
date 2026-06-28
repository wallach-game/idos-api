from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
import os
import time

RATE_LIMIT      = 10    # per-IP requests per window
RATE_WINDOW     = 60    # seconds
GLOBAL_LIMIT    = 5000  # total requests per 24 hours
CONCURRENCY     = 3     # max simultaneous browser pages
CLEANUP_INTERVAL = 300  # sweep stale IP entries every 5 minutes

_hits: dict[str, list[float]] = {}
_rate_locks: dict[str, asyncio.Lock] = {}
_global_hits: list[float] = []
_global_sem                = None
_ip_sems: dict[str, asyncio.Semaphore] = {}
_ip_sems_lock              = None
_last_cleanup              = 0.0

async def _evict_stale():
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    cutoff = now - RATE_WINDOW
    stale = [ip for ip, ts in _hits.items() if all(t < cutoff for t in ts)]
    for ip in stale:
        _hits.pop(ip, None)
        _rate_locks.pop(ip, None)
        _ip_sems.pop(ip, None)

async def check_rate(ip: str) -> None:
    await _evict_stale()
    async with _rate_locks.setdefault(ip, asyncio.Lock()):
        now = time.time()
        hits = _hits.setdefault(ip, [])
        hits[:] = [t for t in hits if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        hits.append(now)

    global _global_hits
    _global_hits = [t for t in _global_hits if now - t < 86400]
    if len(_global_hits) >= GLOBAL_LIMIT:
        raise HTTPException(status_code=429, detail="Global daily limit reached")
    _global_hits.append(now)

async def acquire(ip: str | None):
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

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    title="IDOS API",
    description=(
        "Scrapes [idos.cz](https://idos.cz) and returns public transport connections.\n\n"
        "**Rate limiting:** 10 requests per 60 seconds per IP (via `CF-Connecting-IP`). "
        "Direct/local access has no limit.\n\n"
        f"**Hard limit:** {GLOBAL_LIMIT:,} total requests per 24 hours across all users.\n\n"
        f"**Concurrency:** max {CONCURRENCY} simultaneous requests, 1 per IP (round-robin)."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://idos.numerlab.org"],
    allow_methods=["GET"],
)
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
    import peers
    app.include_router(peers.router)
    if seed := os.getenv("PEER_SEED_URL"):
        await peers.startup_connect(seed)
