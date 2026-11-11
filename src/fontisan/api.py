"""Batch read / audit / scan surface over the C ABI.

Payloads are "packed rows": u32 BE row count, then per row a u32 BE byte length
and that many bytes of UTF-8 JSON. Rows are returned as the decoded dicts; no
object-by-object marshalling happens across the FFI boundary.
"""

from __future__ import annotations

import json
import os
import struct
from typing import Any, Union

from . import _ffi
from .errors import ErrorKind, FontisanError, UnsupportedError

PathLike = Union[str, "os.PathLike[str]"]


def unpack_rows(payload: bytes) -> list[dict[str, Any]]:
    if len(payload) < 4:
        raise FontisanError("payload shorter than the row count", kind=ErrorKind.OTHER)
    (count,) = struct.unpack_from(">I", payload, 0)
    at = 4
    rows = []
    for _ in range(count):
        (length,) = struct.unpack_from(">I", payload, at)
        at += 4
        rows.append(json.loads(payload[at : at + length].decode("utf-8")))
        at += length
    if at != len(payload):
        raise FontisanError("payload has trailing bytes", kind=ErrorKind.OTHER)
    return rows


def _raise(reply: _ffi.Reply) -> None:
    try:
        kind = ErrorKind(reply.error_kind)
    except ValueError:
        kind = ErrorKind.OTHER
    if reply.status == _ffi.E_UNSUPPORTED:
        raise UnsupportedError(reply.message, status=reply.status)
    if reply.status == _ffi.E_READ_FAILED:
        try:
            doc = json.loads(reply.message)
        except ValueError:
            doc = None
        if isinstance(doc, dict):
            raise FontisanError(
                doc.get("message", reply.message),
                kind=kind,
                status=reply.status,
                error_class=doc.get("class"),
                causes=doc.get("causes"),
            )
    raise FontisanError(reply.message, kind=kind, status=reply.status)


def _rows(op: int, data: bytes, flags: int) -> list[dict[str, Any]]:
    reply = _ffi.call(op, data, flags)
    if reply.status != _ffi.OK:
        _raise(reply)
    return unpack_rows(reply.payload)


def read(data: bytes, *, metadata: bool = False, lazy: bool = False) -> list[dict[str, Any]]:
    """Read every face of a font file: one canonical document per face
    (Reference.read). Raises UnsupportedError for dfont / Type 1."""
    flags = (_ffi.READ_METADATA if metadata else 0) | (_ffi.READ_LAZY if lazy else 0)
    return _rows(_ffi.OP_READ, data, flags)


def audit(data: bytes, source_name: str = "", *, validate: bool = False) -> list[dict[str, Any]]:
    """Audit report per face. `source_name` is echoed as `source_file`."""
    name = source_name.encode("utf-8")
    payload = struct.pack(">I", len(name)) + name + bytes(data)
    return _rows(_ffi.OP_AUDIT, payload, _ffi.AUDIT_VALIDATE if validate else 0)


def scan(path: PathLike) -> list[dict[str, Any]]:
    """Scan a file or directory (recursive, sorted by path). Rows with status
    `unsupported` are for the caller to serve."""
    return _rows(_ffi.OP_SCAN, os.fsencode(os.fspath(path)), 0)


def audit_dir(path: PathLike, *, validate: bool = False) -> list[dict[str, Any]]:
    """One row per file: {path, status ok|unsupported|error, reports | error}."""
    return _rows(_ffi.OP_AUDIT_DIR, os.fsencode(os.fspath(path)), _ffi.AUDIT_VALIDATE if validate else 0)


def read_file(path: PathLike, **kw: Any) -> list[dict[str, Any]]:
    with open(path, "rb") as fh:
        return read(fh.read(), **kw)


def audit_file(path: PathLike, **kw: Any) -> list[dict[str, Any]]:
    with open(path, "rb") as fh:
        return audit(fh.read(), os.path.basename(os.fspath(path)), **kw)


# Operations the C ABI does expose (fontisan.h) but this release does not bind:
# convert / extract / woff2_encode / subset / instance. They answer with an
# explicit `unsupported`, as does anything the ABI never had.
_UNBOUND = ("convert", "extract", "woff2_encode", "subset", "instance")


def _unbound(name: str):
    def fn(*_args: Any, **_kw: Any):
        raise UnsupportedError(f"fontisan.{name}: not bound in this release (read, audit, scan, audit_dir only)")

    fn.__name__ = name
    return fn


for _n in _UNBOUND:
    globals()[_n] = _unbound(_n)
