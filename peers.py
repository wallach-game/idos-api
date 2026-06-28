"""
Peer-to-peer service discovery for FastAPI.

Drop-in module: set SELF_URL + optionally PEER_SEED_URL, mount the router,
call startup_connect() on startup. No other dependencies beyond httpx.

Usage in app.py:
    import peers
    app.include_router(peers.router)            # exposes GET/POST /peers
    # in startup:
    if seed := os.getenv("PEER_SEED_URL"):
        await peers.startup_connect(seed)

Env vars:
    SELF_URL                 This instance's public URL
    BOOTSTRAP_PEERS          Comma-separated list of peers to bootstrap from
    PEER_ROUTING             0|1  enable routing (default: 1)
    MAX_HOPS                 int  max forwarding hops (default: 1)
    PEER_VERSION             str  this node's version (default: "1")
    PEER_COMPATIBLE_VERSIONS comma-separated versions to accept (default: PEER_VERSION)
"""

import os
import json
import asyncio
import httpx
from fastapi import APIRouter
from pydantic import BaseModel

SELF_URL: str = os.getenv("SELF_URL", "").rstrip("/")
MAX_HOPS: int = int(os.getenv("MAX_HOPS", "1"))
ENABLED: bool = os.getenv("PEER_ROUTING", "1") not in ("0", "false", "off")
VERSION: str = os.getenv("PEER_VERSION", "1")
COMPATIBLE_VERSIONS: set[str] = set(os.getenv("PEER_COMPATIBLE_VERSIONS", VERSION).split(","))
_CACHE_FILE: str = os.getenv("PEERS_CACHE", "/app/peers_cache.json")
_REDISCOVER_INTERVAL: int = int(os.getenv("PEER_REDISCOVER", "3600"))

# url → version
_peers: dict[str, str] = {}
# insertion-ordered list for round-robin
_peer_list: list[str] = []
_idx: int = 0


def _save() -> None:
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump([{"url": u, "version": v} for u, v in _peers.items() if u != SELF_URL], f)
    except Exception:
        pass


def _load() -> None:
    try:
        with open(_CACHE_FILE) as f:
            for p in json.load(f):
                url = p["url"] if isinstance(p, dict) else p
                ver = p.get("version", "1") if isinstance(p, dict) else "1"
                _peers.setdefault(url, ver)
                if url not in _peer_list:
                    _peer_list.append(url)
    except Exception:
        pass


def register(url: str, version: str = VERSION) -> None:
    url = url.rstrip("/")
    if not url:
        return
    if url not in _peers:
        _peer_list.append(url)
    _peers[url] = version
    _save()


def get_all() -> list[dict]:
    return [{"url": url, "version": ver} for url, ver in _peers.items()]


def next_peer(current_hops: int = 0) -> str | None:
    """Round-robin over compatible peers; None means handle locally."""
    global _idx
    if not ENABLED or current_hops >= MAX_HOPS:
        return None
    compatible = [
        url for url in _peer_list
        if url != SELF_URL and _peers.get(url) in COMPATIBLE_VERSIONS
    ]
    if not compatible:
        return None
    _idx += 1
    return compatible[_idx % len(compatible)]


async def _connect_to(client: httpx.AsyncClient, seed_url: str) -> None:
    """Register with one peer and collect its peer list."""
    payload = {"url": SELF_URL, "version": VERSION}
    try:
        await client.post(f"{seed_url}/peers/register", json=payload)
    except Exception:
        return
    register(seed_url)
    try:
        resp = await client.get(f"{seed_url}/peers")
        for peer in resp.json():
            url = peer["url"] if isinstance(peer, dict) else peer
            ver = peer.get("version", "1") if isinstance(peer, dict) else "1"
            register(url, ver)
            if url not in (SELF_URL, seed_url):
                try:
                    await client.post(f"{url}/peers/register", json=payload)
                except Exception:
                    pass
    except Exception:
        pass


async def _do_bootstrap() -> None:
    """Connect to all known seeds (env + cache) in parallel."""
    if not SELF_URL:
        return
    env_seeds = [s.strip().rstrip("/") for s in os.getenv("BOOTSTRAP_PEERS", "").split(",") if s.strip()]
    cached = [u for u in _peer_list if u != SELF_URL]
    seeds = list(dict.fromkeys(env_seeds + cached))  # env first, deduped
    if not seeds:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await asyncio.gather(*[_connect_to(client, s) for s in seeds], return_exceptions=True)


async def bootstrap() -> None:
    """Load cache, connect to all seeds, then keep rediscovering periodically."""
    _load()
    await _do_bootstrap()
    asyncio.create_task(_rediscover_loop())


async def _rediscover_loop() -> None:
    while True:
        await asyncio.sleep(_REDISCOVER_INTERVAL)
        await _do_bootstrap()


# ── FastAPI router ─────────────────────────────────────────────────────────────

router = APIRouter()


class PeerBody(BaseModel):
    url: str
    version: str = VERSION


@router.get("/peers")
async def list_peers() -> list[dict]:
    return get_all()


@router.post("/peers/register")
async def register_peer(body: PeerBody) -> dict:
    register(body.url, body.version)
    return {"ok": True}


# register self on import
if SELF_URL:
    register(SELF_URL, VERSION)
