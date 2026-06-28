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
"""

import os
import httpx
from fastapi import APIRouter
from pydantic import BaseModel

SELF_URL: str = os.getenv("SELF_URL", "").rstrip("/")
MAX_HOPS: int = int(os.getenv("MAX_HOPS", "1"))

_peers: list[str] = [SELF_URL] if SELF_URL else []
_idx: int = 0


def register(url: str) -> None:
    url = url.rstrip("/")
    if url and url not in _peers:
        _peers.append(url)


def get_all() -> list[str]:
    return list(_peers)


ENABLED: bool = os.getenv("PEER_ROUTING", "1") not in ("0", "false", "off")


def next_peer(current_hops: int = 0) -> str | None:
    """Return next peer URL for round-robin, or None if this node should handle it."""
    global _idx
    if not ENABLED or current_hops >= MAX_HOPS or len(_peers) <= 1:
        return None
    _idx = (_idx + 1) % len(_peers)
    chosen = _peers[_idx]
    return None if chosen == SELF_URL else chosen


async def startup_connect(seed_url: str) -> None:
    """Register with seed peer and collect its known peers."""
    seed_url = seed_url.rstrip("/")
    if not SELF_URL:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(f"{seed_url}/peers/register", json={"url": SELF_URL})
        except Exception:
            pass
        try:
            resp = await client.get(f"{seed_url}/peers")
            for url in resp.json():
                register(url)
                if url not in (SELF_URL, seed_url):
                    try:
                        await client.post(f"{url}/peers/register", json={"url": SELF_URL})
                    except Exception:
                        pass
        except Exception:
            pass
        register(seed_url)


# ── FastAPI router (mount wherever you like) ──────────────────────────────────

router = APIRouter()


class PeerBody(BaseModel):
    url: str


@router.get("/peers")
async def list_peers() -> list[str]:
    return get_all()


@router.post("/peers/register")
async def register_peer(body: PeerBody) -> dict:
    register(body.url)
    return {"ok": True}
