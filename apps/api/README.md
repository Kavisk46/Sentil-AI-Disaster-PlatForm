# SentinelAI Backend

FastAPI backend service. Milestone 2 adds the platform's first real
capability — image ingestion — on top of the Milestone 1 foundation
(configuration, logging, middleware, API versioning, health/root checks).
Still no database, authentication, computer vision, or AI inference.

See [`docs/architecture/backend.md`](../../docs/architecture/backend.md)
for the architecture and layering conventions, and
[`docs/api/endpoints.md`](../../docs/api/endpoints.md) for the full API
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

## Endpoints

| Method & Path | Purpose |
|---|---|
| `GET /` | Project identification and current API version |
| `GET /health` | Liveness check |
| `GET /api/v1` | Confirms the v1 API surface is available |
| `GET /api/v1/system/info` | Basic, non-sensitive service metadata |
| `POST /api/v1/analysis` | Upload an image for analysis (see below) |

### `POST /api/v1/analysis` — image upload

Accepts an aerial/satellite image and returns an analysis ID for tracking
in a later milestone. **This milestone only ingests and records the
upload — no computer vision or AI processing happens yet.**

**Request** — `multipart/form-data`, field name `image`:

```bash
curl -X POST http://localhost:8000/api/v1/analysis \
  -F "image=@aerial.jpg;type=image/jpeg"
```

**Supported types:** JPEG, PNG, WEBP — determined by actually decoding the
file with Pillow, not by trusting the client's declared `Content-Type` or
filename extension (see Security, below).

**Maximum size:** configurable via `MAX_UPLOAD_SIZE_MB` (default `10`; see
`.env.example`).

**Response** — `201 Created`:

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "uploaded",
  "filename": "aerial.jpg"
}
```

`status` is always `"uploaded"` for a newly-created analysis — this
milestone does not pretend any processing has happened. The full lifecycle
(`uploaded` → `processing` → `completed`/`failed`) is defined in
`app/schemas/analysis.py` for a later milestone to drive.

**Error responses:**

| Status | Cause |
|---|---|
| `400 Bad Request` | File content isn't decodable as an image (corrupted, or not an image at all) |
| `413 Payload Too Large` | File exceeds `MAX_UPLOAD_SIZE_MB` |
| `415 Unsupported Media Type` | Declared or actual (Pillow-detected) type isn't JPEG/PNG/WEBP |
| `422 Unprocessable Entity` | `image` field missing from the request |

### Local storage

Uploaded files are written to `UPLOAD_DIR` (default `storage/uploads`,
relative to `apps/api`) under a **server-generated** name
(`<analysis_id>.<ext>`) — the client's original filename is never used to
build a filesystem path. This directory is gitignored and is a
development-only convenience; `app/services/file_storage.py` defines a
`FileStorage` protocol so it can be replaced by an S3/R2/GCS-backed
implementation later without changing `AnalysisService` or the API layer.

### Security considerations

- **Content is validated, not trusted.** Declared `Content-Type` is checked
  first as a cheap rejection, but the authoritative check is Pillow
  actually decoding the bytes and confirming the *real* format is
  supported — closing the gap where a client sends a mismatched or spoofed
  header.
- **Filenames never touch the filesystem.** Storage names are always
  server-generated (`uuid4()` + an extension derived from the
  Pillow-detected format), so path traversal via a crafted filename
  (`../../etc/passwd`) is structurally impossible, not just filtered.
- **The original filename is sanitized before being echoed back** in the
  response (`app/utils/sanitize.py`) — directory components and unsafe
  characters are stripped.
- **Size is enforced without buffering unbounded input.** The upload is
  read bounded to `MAX_UPLOAD_SIZE_MB + 1` bytes, so an oversized upload is
  rejected without ever holding the full payload in memory.
- **Uploaded files are never executed** or otherwise treated as anything
  but opaque bytes written to disk.

## Project layout

```
app/
├── main.py                    # Application factory (create_app())
├── core/
│   ├── config.py                # Settings (pydantic-settings) — no FastAPI imports
│   ├── logging.py                # logging.dictConfig-based setup
│   └── constants.py               # API_V1_PREFIX, allowed image types, and other app-wide constants
├── api/
│   ├── router.py                 # Top-level router: aggregates root, health, and v1
│   ├── deps.py                     # Shared dependency providers
│   ├── exception_handlers.py        # Maps service-layer errors to HTTP responses
│   ├── root.py                       # Unversioned GET /
│   ├── health.py                      # Unversioned GET /health
│   └── v1/                             # Versioned routers, mounted under /api/v1
│       ├── router.py
│       └── endpoints/ {status.py, system.py, analysis.py}
├── services/
│   ├── system_service.py             # Backing service/DI scaffold (Milestone 1)
│   ├── analysis_service.py            # Orchestrates upload validation, storage, metadata
│   ├── image_validation.py             # Pillow-based content validation
│   ├── file_storage.py                  # FileStorage protocol + LocalFileStorage
│   ├── analysis_repository.py            # In-memory analysis metadata store
│   └── exceptions.py                      # Domain errors (no FastAPI dependency)
├── schemas/                    # Pydantic request/response models
├── utils/                      # Generic helpers with no business meaning (datetime, sanitize)
└── middleware/                  # CORS policy, request logging
tests/                          # pytest suite
```

**Layering rule:** routes in `app/api` only translate HTTP ↔ Pydantic
models and call a service; anything resembling a decision, validation, or
I/O belongs in `app/services`, where it's testable without the HTTP layer.
`POST /api/v1/analysis` follows: route → `AnalysisService` → `FileStorage` /
`image_validation`.

## Commands

```bash
pytest              # run tests
ruff check .        # lint
ruff format .       # format
mypy .              # type-check
```
