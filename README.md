> [!WARNING]
> As out server location currently faces extreme weather all operations are suspended for at least 6hours. 18:00-00:00
> 
> 17:43 07 01 2016, Numerator

# IDOS API

REST API for Czech public transport connections, powered by [idos.cz](https://idos.cz). Built with FastAPI + Playwright.

## Public instance

```
https://idos.numerlab.org/api
```

## Endpoints

### `GET /api/search`

Returns the next N connections between two stops.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `from_stop` | yes | — | Departure stop name |
| `to_stop` | yes | — | Arrival stop name |
| `n` | no | 3 | Number of connections (max 20) |
| `date` | no | today | Date (`DD.MM.YYYY`) |
| `time` | no | now | Time (`HH:MM`) |

**Example:**
```bash
curl "https://idos.numerlab.org/api/search?from_stop=Praha+hl.n.&to_stop=Brno+hl.n.&n=3"
```

**Response:**
```json
{
  "from": "Praha hl.n.",
  "to": "Brno hl.n.",
  "connections": [
    {
      "dep_time": "13:37",
      "dep_date": "28.6. ne",
      "duration": "2 hod 37 min",
      "delays": ["Odjezd bývá zpožděn"],
      "legs": [
        { "name": "Ex3 (EC 281 Metropolitan)", "type": "Eurocity" }
      ]
    }
  ]
}
```

### `GET /status`

Current load on this instance.

```json
{ "active_requests": 1, "capacity": 3, "daily_requests": 42, "daily_limit": 5000 }
```

### `GET /api/peers`

List of known peer instances in the cluster.

```json
[{ "url": "https://idos-api-2.onrender.com", "version": "1" }]
```

### `POST /api/peers/register`

Register a peer manually.

```bash
curl -X POST http://localhost:8001/api/peers/register \
  -H "Content-Type: application/json" \
  -d '{"url": "https://idos-api-2.onrender.com", "version": "1"}'
```

## Rate limiting

- **Per IP:** 10 requests per 60 seconds (via `CF-Connecting-IP` header)
- **Global:** 5,000 requests per 24 hours across all users
- **Concurrency:** max 3 simultaneous requests, 1 per IP
- Local/self-hosted instances have no limits

## Self-hosting

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

```bash
git clone https://github.com/wallach-game/idos-api
cd idos-api
docker compose up -d
```

API available at `http://localhost:8001`

## Clustering

Multiple instances can form a leaderless peer-to-peer cluster. Each node round-robins incoming requests across all known peers, distributing load and browser sessions across different IPs.

There is no central coordinator. Nodes discover each other through community-operated bootstrap peers — anyone can run a node and submit it to the list below.

**Setup:**
```
SELF_URL=https://your-instance.onrender.com
BOOTSTRAP_PEERS=https://node1.example.com,https://node2.example.com
```

On startup the node contacts all bootstrap peers in parallel, registers itself, and collects their full peer lists. If no bootstrap peers respond it starts solo and waits for incoming registrations.

**Community nodes** — add yours via PR:

| URL | Region |
|-----|--------|
| _(none yet — be the first)_ | — |

All env vars:

| Variable | Default | Description |
|----------|---------|-------------|
| `SELF_URL` | — | This instance's public URL |
| `BOOTSTRAP_PEERS` | — | Comma-separated peers to bootstrap from (grows automatically) |
| `PEERS_CACHE` | `/app/peers_cache.json` | Path to persist discovered peers across restarts |
| `PEER_REDISCOVER` | `3600` | Seconds between background rediscovery runs |
| `PEER_ROUTING` | `1` | Set to `0` to disable request forwarding |
| `MAX_HOPS` | `1` | Max times a request is forwarded between peers |
| `PEER_VERSION` | `1` | Protocol version of this node |
| `PEER_COMPATIBLE_VERSIONS` | `1` | Comma-separated versions to route to |

## Proxy rotation

The API can route scraping requests through free HTTP proxies to reduce IP-based blocking.

| Variable | Default | Description |
|----------|---------|-------------|
| `PROXY_ENABLED` | `0` | Set to `1` to enable |
| `PROXY_MAX_TRIES` | `3` | Proxy attempts before falling back to direct |
| `PROXY_REFRESH` | `3600` | Seconds between proxy list refreshes |

Proxy list is fetched from [free-proxy-list.net](https://free-proxy-list.net/en/) and refreshed automatically in the background.

## Home Assistant card

Use [idos-card](https://github.com/wallach-game/idos-card) to display connections directly in your HA dashboard.

## Disclaimer

This project scrapes idos.cz which is operated by CHAPS s.r.o. Use responsibly.
