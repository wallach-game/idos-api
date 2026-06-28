# IDOS API

REST API for Czech public transport connections, powered by [idos.cz](https://idos.cz). Built with FastAPI + Playwright.

## Public instance

```
https://idos.numerlab.org/api
```

API docs: [idos.numerlab.org/docs](https://idos.numerlab.org/docs)

## Endpoints

### `GET /api/search`

Returns the next N connections between two stops.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `from_stop` | yes | — | Departure stop name |
| `to_stop` | yes | — | Arrival stop name |
| `n` | no | 3 | Number of connections |
| `date` | no | today | Date (e.g. `28.6.2026`) |
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

## Rate limiting

- **Per IP:** 10 requests per 60 seconds (via `CF-Connecting-IP` header)
- **Global:** 5,000 requests per 24 hours across all users
- **Concurrency:** max 3 simultaneous requests, 1 per IP (round-robin)
- Local/self-hosted instances have no limits

## Self-hosting

**Requirements:** Docker, Docker Compose

```bash
git clone https://github.com/wallach-game/idos-api
cd idos-api
docker compose up -d
```

API available at `http://localhost:8001`

## Home Assistant card

Use [idos-card](https://github.com/wallach-game/idos-card) to display connections directly in your HA dashboard.

## Disclaimer

This project scrapes idos.cz which is operated by CHAPS s.r.o. Use responsibly.
