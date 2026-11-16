"""ctypes binding for the fontisan C ABI (fontisan.h, ABI version 1).

Same surface the Ruby ffi tier drives: `fontisan_abi_version`,
`fontisan_call`, `fontisan_result_free`. Nothing here interprets payloads;
see `fontisan.api`.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Optional

from ._engine import ENGINE_REV

MAGIC = 0x4E415346  # "FSAN" little-endian
ABI_VERSION = 1

# fontisan_call statuses
OK = 0
E_INVALID_ARG = 7
E_CONVERT_FAILED = 8
E_READ_FAILED = 9
E_UNSUPPORTED = 10

# ops (fontisan.h)
OP_ECHO = 0
OP_CONVERT = 1
OP_EXTRACT = 2
OP_WOFF2_ENCODE = 3
OP_SUBSET = 6
OP_INSTANCE = 7
OP_READ = 8
OP_AUDIT = 9
OP_SCAN = 10
OP_AUDIT_DIR = 11

READ_METADATA = 1
READ_LAZY = 2
AUDIT_VALIDATE = 1

_LIB_NAMES = ("libfontisan_cdylib.dylib", "libfontisan_cdylib.so", "fontisan_cdylib.dll", "libfontisan_cdylib.dll")


class EngineError(RuntimeError):
    """The cdylib could not be loaded, or speaks another ABI / engine rev."""


class _Header(ctypes.Structure):
    _fields_ = [
        ("magic", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


class _Request(ctypes.Structure):
    _fields_ = [
        ("header", _Header),
        ("op", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("input", ctypes.c_void_p),
        ("input_len", ctypes.c_size_t),
    ]


class _ErrorRow(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_int32),
        ("message", ctypes.c_void_p),
        ("message_len", ctypes.c_size_t),
    ]


class _Result(ctypes.Structure):
    # 72 bytes on 64-bit: error_kind and reserved follow payload_len. They are
    # only valid when header.struct_size >= 72 (older cdylibs allocate 64).
    _fields_ = [
        ("header", _Header),
        ("status", ctypes.c_int32),
        ("error", _ErrorRow),
        ("payload", ctypes.c_void_p),
        ("payload_len", ctypes.c_size_t),
        ("error_kind", ctypes.c_int32),
        ("reserved", ctypes.c_int32),
    ]


_RESULT_WITH_KIND = ctypes.sizeof(_Result) if ctypes.sizeof(ctypes.c_void_p) == 8 else 0


class Reply:
    """One call's outcome, copied out of the engine-owned result block."""

    __slots__ = ("status", "payload", "message", "error_kind")

    def __init__(self, status: int, payload: bytes, message: str, error_kind: int):
        self.status = status
        self.payload = payload
        self.message = message
        self.error_kind = error_kind


_lib: Optional[ctypes.CDLL] = None
_lib_path: Optional[str] = None


def _candidate_paths() -> list[str]:
    out: list[str] = []
    env = os.environ.get("FONTISAN_CDYLIB")
    if env:
        out.append(env)
    packaged = Path(__file__).resolve().parent / "lib"
    out.extend(str(packaged / n) for n in _LIB_NAMES)
    return out


def load() -> ctypes.CDLL:
    """dlopen the cdylib once, bind it, and check ABI version and engine rev."""
    global _lib, _lib_path
    if _lib is not None:
        return _lib

    errors: list[str] = []
    lib = None
    path = None
    for candidate in _candidate_paths():
        if not Path(candidate).exists():
            errors.append(f"{candidate}: not found")
            continue
        try:
            lib = ctypes.CDLL(candidate)
            path = candidate
            break
        except OSError as error:
            errors.append(f"{candidate}: {error}")
    if lib is None or path is None:
        raise EngineError(
            "libfontisan_cdylib not found (build it with `cargo build --release "
            "--manifest-path ext/fontisan_cdylib/Cargo.toml` in fontisan at FONTISAN_REV "
            "and point FONTISAN_CDYLIB at it, or install a wheel that "
            "vendors it). Tried:\n  " + "\n  ".join(errors)
        )

    lib.fontisan_abi_version.argtypes = []
    lib.fontisan_abi_version.restype = ctypes.c_uint32
    lib.fontisan_call.argtypes = [ctypes.POINTER(_Request), ctypes.POINTER(ctypes.POINTER(_Result))]
    lib.fontisan_call.restype = ctypes.c_int32
    lib.fontisan_result_free.argtypes = [ctypes.POINTER(_Result)]
    lib.fontisan_result_free.restype = None

    found = lib.fontisan_abi_version()
    if found != ABI_VERSION:
        raise EngineError(f"{path} speaks ABI {found}, this package expects {ABI_VERSION}")

    try:
        revision = lib.fontisan_cdylib_engine_rev
    except AttributeError as error:
        raise EngineError(f"{path} exports no engine rev (fontisan_cdylib_engine_rev)") from error
    revision.argtypes = []
    revision.restype = ctypes.c_char_p
    raw = revision()
    if not raw:
        raise EngineError(f"{path} exports an empty engine rev")
    try:
        reported = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise EngineError(f"{path} exports an invalid engine rev") from error
    if reported != ENGINE_REV:
        raise EngineError(f"{path} was built from engine {reported}, this package pins {ENGINE_REV}")

    _lib, _lib_path = lib, path
    return lib


def cdylib_path() -> Optional[str]:
    load()
    return _lib_path


def engine_rev() -> str:
    """The verified fontisan-rs rev exported by the loaded cdylib."""
    return load().fontisan_cdylib_engine_rev().decode("ascii")


def abi_version() -> int:
    return load().fontisan_abi_version()


def call(op: int, input_bytes: bytes, flags: int = 0) -> Reply:
    lib = load()
    data = bytes(input_bytes)
    buf = ctypes.create_string_buffer(data, max(len(data), 1))
    req = _Request()
    req.header.magic = MAGIC
    req.header.abi_version = ABI_VERSION
    req.header.struct_size = ctypes.sizeof(_Request)
    req.header.reserved = 0
    req.op = op
    req.flags = flags
    req.input = ctypes.cast(buf, ctypes.c_void_p)
    req.input_len = len(data)

    out = ctypes.POINTER(_Result)()
    lib.fontisan_call(ctypes.byref(req), ctypes.byref(out))
    if not out:
        raise EngineError("fontisan_call returned no result block")
    try:
        r = out.contents
        payload = ctypes.string_at(r.payload, r.payload_len) if r.payload and r.payload_len else b""
        message = (
            ctypes.string_at(r.error.message, r.error.message_len).decode("utf-8", "replace")
            if r.error.message and r.error.message_len
            else ""
        )
        has_kind = r.header.struct_size >= _RESULT_WITH_KIND > 0
        return Reply(r.status, payload, message, r.error_kind if has_kind else 0)
    finally:
        lib.fontisan_result_free(out)


def lib_filename() -> str:
    if sys.platform == "darwin":
        return "libfontisan_cdylib.dylib"
    if sys.platform.startswith("win"):
        return "fontisan_cdylib.dll"
    return "libfontisan_cdylib.so"
