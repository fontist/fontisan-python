"""Error surface. Switch on `kind` (fontisan.h FONTISAN_KIND_*), not on the message."""

from __future__ import annotations

import enum
from typing import Any, Optional


class ErrorKind(enum.IntEnum):
    NONE = 0
    INVALID_FONT = 1
    INVALID_AXIS = 2
    INVALID_COORDINATES = 3
    IO = 4
    UNSUPPORTED = 5
    SUBSETTING = 6
    CORRUPTED_TABLE = 7
    MISSING_TABLE = 8
    INVALID_ARGUMENT = 9
    TRUNCATED = 10
    OTHER = 11


class FontisanError(Exception):
    """An engine error. For read/audit failures `error_class`/`causes` carry the
    Ruby error surface the goldens record ({class, message, causes})."""

    def __init__(
        self,
        message: str,
        *,
        kind: ErrorKind = ErrorKind.OTHER,
        status: int = 0,
        error_class: Optional[str] = None,
        causes: Optional[list[dict[str, Any]]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status = status
        self.error_class = error_class
        self.causes = causes or []


class UnsupportedError(FontisanError):
    """Explicit `unsupported` result: the engine does not serve this natively
    (dfont, Type 1) or this binding does not expose the operation."""

    def __init__(self, message: str, **kw: Any):
        kw.setdefault("kind", ErrorKind.UNSUPPORTED)
        super().__init__(message, **kw)
