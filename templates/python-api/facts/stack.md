---
name: Stack overview
type: fact
date: YYYY-MM-DD
---

# Stack

| Layer | Choice | Version | Notes |
|-------|--------|---------|-------|
| Framework | FastAPI / Flask / Django | | |
| Python | 3.x | | |
| ASGI server | Uvicorn / Hypercorn | | |
| ORM | SQLAlchemy / Tortoise / Django ORM | | |
| Database | Postgres / SQLite / ? | | |
| Cache | Redis / Memcached / in-proc | | |
| Auth | JWT / session / OAuth | | |
| Deploy | Fly.io / Railway / AWS / Docker | | |
| Testing | pytest | | |

## Commands
- `uv run uvicorn app.main:app --reload` — local dev
- `pytest` — run tests
- `ruff check .` — lint
- `alembic upgrade head` — apply migrations
