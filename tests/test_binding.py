"""Binding-level checks: ABI, engine rev, struct layout, error surface, unsupported."""

from __future__ import annotations

import ctypes
from pathlib import Path

import pytest

import fontisan
from fontisan import _ffi
from fontisan._engine import ENGINE_REV

ROOT = Path(__file__).resolve().parents[1]


def test_result_struct_is_72_bytes_with_error_kind_after_payload_len():
    assert ctypes.sizeof(_ffi._Result) == 72
    assert _ffi._Result.payload_len.offset == 56
    assert _ffi._Result.error_kind.offset == 64
    assert _ffi._Result.reserved.offset == 68
    assert ctypes.sizeof(_ffi._Request) == 40


def test_abi_version_is_one():
    assert fontisan.abi_version() == 1


def test_engine_rev_pin_matches_repo_file_and_loaded_cdylib():
    assert ENGINE_REV == (ROOT / "ENGINE_REV").read_text().strip()
    assert fontisan.engine_rev() == ENGINE_REV


def test_mismatched_stamp_is_refused(tmp_path, monkeypatch):
    lib = Path(fontisan.cdylib_path())
    (tmp_path / lib.name).write_bytes(lib.read_bytes())
    (tmp_path / "ENGINE_REV").write_text("0" * 40 + "\n")
    monkeypatch.setattr(_ffi, "_lib", None)
    monkeypatch.setenv("FONTISAN_CDYLIB", str(tmp_path / lib.name))
    with pytest.raises(fontisan.EngineError, match="built from engine"):
        _ffi.load()


def test_garbage_font_is_a_typed_error_not_a_crash():
    with pytest.raises(fontisan.FontisanError) as caught:
        fontisan.read(b"\xab" * 64)
    assert caught.value.kind == fontisan.ErrorKind.INVALID_FONT
    assert caught.value.error_class


def test_empty_input_read_fails_with_ruby_shaped_error():
    with pytest.raises(fontisan.FontisanError) as caught:
        fontisan.read(b"")
    assert caught.value.error_class == "Fontisan::InvalidFontError"


def test_bad_audit_prefix_is_invalid_argument():
    reply = _ffi.call(_ffi.OP_AUDIT, b"\x00\x00")
    assert reply.status == _ffi.E_INVALID_ARG
    assert reply.error_kind == fontisan.ErrorKind.INVALID_ARGUMENT


@pytest.mark.parametrize("name", ["convert", "extract", "woff2_encode", "subset", "instance"])
def test_unbound_operations_answer_unsupported(name):
    with pytest.raises(fontisan.UnsupportedError) as caught:
        getattr(fontisan, name)(b"")
    assert caught.value.kind == fontisan.ErrorKind.UNSUPPORTED
