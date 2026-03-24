# microservice-boilerplate

Production-ready **Python 3.11** async microservice template with FastAPI, SQLAlchemy 2.0, RabbitMQ, Loguru, Prometheus, and a full test suite.

---

## Features

| Area | Technology |
|---|---|
| **API framework** | FastAPI (async) |
| **Validation** | Pydantic v2 |
| **ORM / DB** | SQLAlchemy 2.0 async — PostgreSQL, MySQL, SQLite, SQL Server, Oracle |
| **Message queue** | RabbitMQ via `aio-pika` (async, auto-reconnect) |
| **Logging** | Loguru with `enqueue=True` (thread-safe, async-safe) |
| **Metrics** | Prometheus `/metrics` endpoint + per-request stats |
| **Testing** | pytest-asyncio, in-memory SQLite, mocked broker |
| **Containerisation** | Multi-stage Dockerfile, docker-compose (app + Postgres + RabbitMQ) |
| **CI/CD** | GitHub Actions (lint → test → docker build → sdist) |

---

## Quick start

### 1 — Clone and install

```bash
git clone <repo-url>
cd microservice-boilerplate
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

### 2 — Configure

```bash
cp .env.example .env
# Edit .env or config/config.yaml
```

The default config uses **SQLite** (`dev.db`) and expects RabbitMQ on `localhost:5672`.
No external services are required to run the tests.

### 3 — Run locally

```bash
# Hot-reload development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or via Make
make run
```

Open the interactive docs: <http://localhost:8000/docs>

### 4 — Run with Docker (full stack)

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| API | <http://localhost:8000/docs> |
| RabbitMQ management | <http://localhost:15672> (guest / guest) |

---

## Project structure

```
microservice-boilerplate/
├── app/
│   ├── main.py                  # FastAPI app + lifespan startup/shutdown
│   ├── config.py                # Centralised settings (yaml + env vars)
│   ├── logger.py                # Loguru setup, stdlib intercept
│   ├── api/
│   │   ├── health.py            # GET /api/health, /api/health/ready, /db, /queue
│   │   ├── stats.py             # GET /api/stats, /api/stats/system, /api/stats/info
│   │   └── v1/items.py          # Full CRUD + event publish example
│   ├── db/
│   │   ├── session.py           # Async engine, session factory, health check
│   │   ├── models/item.py       # ORM model with cross-DB UUID, timestamps
│   │   └── repositories/        # Repository pattern — all DB operations here
│   ├── messaging/
│   │   ├── producer.py          # Async RabbitMQ publisher
│   │   ├── consumer.py          # Async RabbitMQ consumer with routing-key dispatch
│   │   └── handlers.py          # @on("routing.key") decorator registry
│   ├── services/item_service.py # Business logic, owns session scope
│   ├── schemas/item.py          # Pydantic DTOs (request/response)
│   └── middleware/              # Request logging + AppStats collector
├── tests/
│   ├── conftest.py              # Shared fixtures (test DB, mock producer, client)
│   ├── unit/                    # No external deps — fast
│   └── integration/             # Repository + service + messaging tests
├── config/config.yaml           # All tuneable settings
├── Dockerfile                   # Multi-stage build
├── docker-compose.yml           # App + Postgres + RabbitMQ
├── .github/workflows/ci.yml     # Lint → Test → Docker → sdist
└── Makefile                     # Convenience targets
```

---

## Database configuration

Change a single line in `config/config.yaml` (or set `DATABASE_URL` in `.env`):

```yaml
database:
  url: "postgresql+asyncpg://user:pass@localhost:5432/mydb"
```

| Database | URL format | Extra package |
|---|---|---|
| **PostgreSQL** | `postgresql+asyncpg://user:pass@host:5432/db` | `asyncpg` (included) |
| **MySQL** | `mysql+aiomysql://user:pass@host:3306/db` | `aiomysql` (included) |
| **SQLite** | `sqlite+aiosqlite:///./app.db` | `aiosqlite` (included) |
| **SQL Server** | `mssql+pyodbc://user:pass@host:1433/db?driver=ODBC+Driver+17+for+SQL+Server` | `pip install pyodbc` |
| **Oracle** | `oracle+cx_oracle://user:pass@host:1521/SERVICE` | `pip install cx_Oracle` |

---

## API endpoints

### Health

```
GET /api/health           liveness probe
GET /api/health/ready     readiness (DB + RabbitMQ)
GET /api/health/db        database connectivity
GET /api/health/queue     RabbitMQ connectivity
```

### Stats

```
GET /api/stats            request counters, error rates, per-endpoint timings
GET /api/stats/system     CPU, memory, process info
GET /api/stats/info       service name / version / environment
```

### Items (example CRUD)

```
POST   /api/v1/items              create
GET    /api/v1/items?skip=0&limit=100&name=widget  list (paginated + filtered)
GET    /api/v1/items/{id}         get single
PATCH  /api/v1/items/{id}         partial update
DELETE /api/v1/items/{id}         soft-delete  (?hard=true for permanent)
POST   /api/v1/items/{id}/publish publish event to RabbitMQ
```

### Metrics

```
GET /metrics    Prometheus scrape endpoint
```

---

## RabbitMQ messaging

**Publish a message from code:**

```python
from app.messaging.producer import MessageProducer

producer = MessageProducer()
await producer.connect()
await producer.publish(
    payload={"event": "order.placed", "order_id": "abc123"},
    routing_key="microservice.order.placed",
)
```

**Register a consumer handler:**

```python
from app.messaging.handlers import on

@on("microservice.order.*")
async def handle_order(body: dict) -> None:
    print(f"Order event: {body['event']}")
```

---

## Testing

```bash
# All tests
pytest

# Unit tests only (no external services)
pytest tests/unit/

# With coverage report
pytest --cov=app --cov-report=html

# Single test file
pytest tests/unit/test_items.py -v
```

All tests use **in-memory SQLite** and **mock RabbitMQ** — no external services required.

---

## Build a source distribution

```bash
# sdist (tarball)
python setup.py sdist

# sdist + wheel
python -m build

# Install from dist
pip install dist/microservice_boilerplate-1.0.0.tar.gz
```

---

## Logging

Logs go to **stdout** (colourised) and `logs/app.log` (rotating, compressed).
`enqueue=True` ensures all writes happen in a single background thread —
worker threads and asyncio tasks never block on or interleave log I/O.

```python
from app.logger import get_logger
log = get_logger(__name__)

log.info("Starting job {id}", id=job_id)
log.bind(user_id="u123").warning("Rate limit hit")
```

---

## Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | (from config.yaml) | Full DB connection URL |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ AMQP URL |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `APP_ENV` | `development` | Environment name |
| `APP_DEBUG` | `false` | Enable uvicorn auto-reload |
| `APP_SECRET_KEY` | `change-me` | Application secret |

---

## CI/CD (GitHub Actions)

On every push / PR to `main` or `develop`:

1. **Lint** — ruff + mypy
2. **Test** — pytest on Python 3.11 and 3.12 with coverage upload
3. **Docker build** — validates the multi-stage Dockerfile
4. **sdist + wheel** — artifacts uploaded

---

## License

MIT
