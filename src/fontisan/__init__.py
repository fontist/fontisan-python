"""fontisan-python: Python face of the fontisan font engine.

Rides the fontisan C-ABI cdylib (the one the Ruby `:ffi` tier uses) through
ctypes. This release binds the batch audit and table-read surface.
"""

from ._ffi import EngineError, abi_version, cdylib_path, engine_rev
from .api import (
    audit,
    audit_dir,
    audit_file,
    convert,  # noqa: F401  explicit `unsupported`
    extract,  # noqa: F401
    instance,  # noqa: F401
    read,
    read_file,
    scan,
    subset,  # noqa: F401
    woff2_encode,  # noqa: F401
)
from .errors import ErrorKind, FontisanError, UnsupportedError

__all__ = [
    "EngineError",
    "ErrorKind",
    "FontisanError",
    "UnsupportedError",
    "abi_version",
    "audit",
    "audit_dir",
    "audit_file",
    "cdylib_path",
    "convert",
    "engine_rev",
    "extract",
    "instance",
    "read",
    "read_file",
    "scan",
    "subset",
    "woff2_encode",
]
