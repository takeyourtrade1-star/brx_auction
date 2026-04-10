# Ebartex Marketplace Backend (Python)

Backend riscritto da Node.js a Python (FastAPI), con PostgreSQL, Redis, JWT RS256 (BRX_auth), e integrazione BRX_Search.

## Stack

- **FastAPI** + Gunicorn/Uvicorn
- **PostgreSQL** (async con asyncpg + SQLAlchemy 2.0)
- **Redis** (cache, rate limiting, coda reindex)
- **Pydantic V2**, **SlowAPI** (rate limit)

## Setup

1. Copia `.env.example` in `.env` e compila (DATABASE_URL, REDIS_URL, AUTH_JWT_PUBLIC_KEY, SEARCH_*).
2. Crea il virtualenv e installa dipendenze:
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```
3. Migrazioni DB:
   ```bash
   alembic upgrade head
   ```
4. Avvio API:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   In produzione: `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 -w 4`

## Worker Reindex

Per consumare la coda Redis e chiamare BRX_Search reindex:

```bash
python worker_reindex.py
```

(Eseguire in un processo separato o come servizio.)

## Struttura

- `app/api/` – router FastAPI (auctions, bids, products)
- `app/core/` – config, JWT, rate limit, dependencies
- `app/schemas/` – Pydantic DTO
- `app/models/` – SQLAlchemy (auctions, bids, products, sync)
- `app/services/` – logica di business
- `app/infrastructure/` – DB, Redis, client Auth/Search
- `app/utils/` – eccezioni, request_id, error handler

## Linee guida

Vedi [migration_guidelines.md](migration_guidelines.md) per stack, sicurezza e scalabilità.
