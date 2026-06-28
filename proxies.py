"""
Free proxy list loader with round-robin rotation.

Drop-in module — no app-specific imports. Requires httpx.

Usage:
    import proxies
    await proxies.start_background_refresh()   # once on startup
    proxy = proxies.next_proxy()               # None if disabled or list empty
    # Playwright: browser.new_context(proxy={"server": proxy})
    # httpx:      httpx.AsyncClient(proxy=proxy)

Env vars:
    PROXY_ENABLED    0|1          enable proxy rotation (default: 0)
    PROXY_MAX_TRIES  int          proxy attempts before direct fallback (default: 3)
    PROXY_REFRESH    int          seconds between list refreshes (default: 3600)
"""

import os
import re
import time
import asyncio
import httpx

ENABLED: bool = os.getenv("PROXY_ENABLED", "0") not in ("0", "false", "off")
MAX_TRIES: int = int(os.getenv("PROXY_MAX_TRIES", "3"))
_REFRESH: int = int(os.getenv("PROXY_REFRESH", "3600"))
_SOURCE = "https://free-proxy-list.net/en/"

_proxies: list[str] = []
_idx: int = 0
_last_fetched: float = 0.0
_lock: asyncio.Lock | None = None


async def _do_fetch() -> None:
    global _proxies, _last_fetched
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_SOURCE)
        pairs = re.findall(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})</td><td>(\d{1,5})', resp.text)
        if pairs:
            _proxies = [f"http://{ip}:{port}" for ip, port in pairs]
            _last_fetched = time.time()
    except Exception:
        pass  # keep existing list on failure


async def ensure_loaded() -> None:
    """Fetch proxy list if empty or stale. Safe to call on every request."""
    global _lock
    if not ENABLED:
        return
    if _proxies and time.time() - _last_fetched < _REFRESH:
        return
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _proxies and time.time() - _last_fetched < _REFRESH:
            return
        await _do_fetch()


async def _refresh_loop() -> None:
    await ensure_loaded()
    while True:
        await asyncio.sleep(_REFRESH)
        await _do_fetch()


async def start_background_refresh() -> None:
    """Start periodic background refresh. Call once on app startup."""
    if ENABLED:
        asyncio.create_task(_refresh_loop())


def next_proxy() -> str | None:
    """Round-robin next proxy, or None if disabled/unavailable."""
    global _idx
    if not ENABLED or not _proxies:
        return None
    proxy = _proxies[_idx % len(_proxies)]
    _idx = (_idx + 1) % len(_proxies)
    return proxy
