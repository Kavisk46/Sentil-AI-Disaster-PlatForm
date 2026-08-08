"""Filename sanitization."""

import re

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_MAX_FILENAME_LENGTH = 255
_FALLBACK_FILENAME = "upload"


def sanitize_filename(filename: str | None) -> str:
    """Reduce a client-supplied filename to a safe display name.

    This is for display/metadata only — it is never used to build a
    filesystem path. Storage filenames are always generated server-side
    (see `app/services/analysis_service.py`), so this function's job isn't
    to make the name *safe to write to disk*, only to stop a hostile or
    malformed client filename (`"../../etc/passwd"`, a `NUL` byte, an
    absolute path) from being echoed back to API consumers unchanged.
    """
    if not filename:
        return _FALLBACK_FILENAME

    # Strip any directory components regardless of separator style, so
    # "../../etc/passwd" or "C:\\evil\\payload.png" degrades to just its
    # final segment.
    candidate = filename.replace("\\", "/").split("/")[-1].strip()
    candidate = _UNSAFE_CHARS.sub("_", candidate)
    candidate = candidate.strip("._") or _FALLBACK_FILENAME
    return candidate[:_MAX_FILENAME_LENGTH]
