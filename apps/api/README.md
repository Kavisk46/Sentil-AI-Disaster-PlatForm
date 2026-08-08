# SentinelAI Backend

FastAPI backend service. Sprint 2.1 delivers the backend foundation:
configuration, logging, middleware, a service/DI layer scaffold, API
versioning, and health/root checks — no database, authentication, or
domain business logic yet.

See [`docs/architecture/backend.md`](../../docs/architecture/backend.md)
for the architecture and layering conventions, and
[`docs/api/endpoints.md`](../../docs/api/endpoints.md) for the API
reference.

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate       # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs (Swagger UI) and `/redoc`

## Project layout

```
app/
├── main.py               # Application factory (create_app()) — the only place
│                          # settings, logging, middleware, and routers are wired together
├── core/
│   ├── config.py          # Settings (pydantic-settings) — no FastAPI imports
│   ├── logging.py          # logging.dictConfig-based setup
│   └── constants.py         # API_V1_PREFIX and other non-configurable constants
├── api/
│   ├── router.py           # Top-level router: aggregates root, health, and v1
│   ├── deps.py               # Shared dependency providers (e.g. get_system_service)
│   ├── root.py                # Unversioned GET /
│   ├── health.py               # Unversioned GET /health
│   └── v1/                      # Versioned routers, mounted under /api/v1
│       ├── router.py
│       └── endpoints/
├── services/                # Business logic, injected into routes via app/api/deps.py
├── schemas/                 # Pydantic request/response models
├── utils/                   # Generic helpers with no business meaning (e.g. datetime)
└── middleware/               # CORS policy, request logging
tests/                       # pytest suite
```

**Layering rule:** routes in `app/api` only translate HTTP ↔ Pydantic
models and call a service; anything resembling a decision or computation
belongs in `app/services`, where it's testable without the HTTP layer (see
`tests/test_system_service.py`).

## Commands

```bash
pytest              # run tests
ruff check .        # lint
ruff format .       # format
mypy .              # type-check
```
