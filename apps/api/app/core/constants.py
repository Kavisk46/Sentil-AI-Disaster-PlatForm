"""Application-wide constants that are not user-configurable settings."""

API_V1_PREFIX = "/api/v1"
HEALTH_PATH = "/health"

REQUEST_ID_HEADER = "X-Request-ID"
PROCESS_TIME_HEADER = "X-Process-Time-Ms"

# Supported image types (Milestone 2 — image ingestion). Which formats the
# platform accepts is a product decision, not something that varies by
# deployment environment, so it lives here rather than in Settings.
ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

# Pillow's `Image.format` values corresponding to the content types above —
# the authoritative check, since it reflects what the bytes actually are
# rather than what the client claimed. Also doubles as the source of truth
# for the server-generated storage extension.
IMAGE_FORMAT_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
