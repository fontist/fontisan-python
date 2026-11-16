"""Binding-level checks: ABI, engine rev, struct layout, error surface, unsupported."""

from __future__ import annotations

import ctypes
import importlib.util
import subprocess
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


@pytest.fixture
def revision_cdylib(tmp_path):
    """Build real ABI stubs so revision failures exercise dlopen and symbols."""
    def build(rev, abi=1):
        source = tmp_path / "revision.rs"
        exports = f"""
#[no_mangle]
pub extern "C" fn fontisan_abi_version() -> u32 {{ {abi} }}
#[no_mangle]
pub extern "C" fn fontisan_call() -> i32 {{ 0 }}
#[no_mangle]
pub extern "C" fn fontisan_result_free() {{}}
"""
        if rev is not None:
            value = 'std::ptr::null()' if rev == "null" else rf'b"{rev}\0".as_ptr()'
            exports += f"""
#[no_mangle]
pub extern "C" fn fontisan_cdylib_engine_rev() -> *const u8 {{ {value} }}
"""
        source.write_text(exports)
        library = tmp_path / _ffi.lib_filename()
        subprocess.run(
            ["rustc", "--crate-type", "cdylib", str(source), "-o", str(library)],
            check=True, capture_output=True, text=True,
        )
        return library
    return build


@pytest.mark.parametrize("rev", ["0" * 40, None, "", "null"])
def test_unverified_or_mismatched_export_is_refused(revision_cdylib, monkeypatch, rev):
    library = revision_cdylib(rev)
    # A matching legacy stamp must not rescue a missing or incorrect export.
    (library.parent / "ENGINE_REV").write_text(ENGINE_REV + "\n")
    monkeypatch.setattr(_ffi, "_lib", None)
    monkeypatch.setattr(_ffi, "_lib_path", None)
    monkeypatch.setenv("FONTISAN_CDYLIB", str(library))
    with pytest.raises(fontisan.EngineError, match="engine rev|built from engine"):
        _ffi.load()
    assert _ffi._lib is None
    assert _ffi._lib_path is None


def test_exported_pin_is_used_without_a_stamp(revision_cdylib, monkeypatch):
    library = revision_cdylib(ENGINE_REV)
    monkeypatch.setattr(_ffi, "_lib", None)
    monkeypatch.setattr(_ffi, "_lib_path", None)
    monkeypatch.setenv("FONTISAN_CDYLIB", str(library))
    assert fontisan.engine_rev() == ENGINE_REV
    assert fontisan.cdylib_path() == str(library)
    # Old staging metadata is no longer an authority for the binary revision.
    (library.parent / "ENGINE_REV").write_text("0" * 40 + "\n")
    monkeypatch.setattr(_ffi, "_lib", None)
    assert fontisan.engine_rev() == ENGINE_REV


def test_mismatched_abi_is_refused(revision_cdylib, monkeypatch):
    library = revision_cdylib(ENGINE_REV, abi=2)
    monkeypatch.setattr(_ffi, "_lib", None)
    monkeypatch.setenv("FONTISAN_CDYLIB", str(library))
    with pytest.raises(fontisan.EngineError, match="speaks ABI 2"):
        _ffi.load()


@pytest.fixture
def stage_script(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("stage_cdylib", ROOT / "scripts/stage_cdylib.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def test_staging_rejects_wrong_export_before_replacing_library(stage_script, revision_cdylib):
    library = revision_cdylib("0" * 40)
    dest = stage_script.ROOT / "src/fontisan/lib"
    dest.mkdir(parents=True)
    staged = dest / library.name
    staged.write_bytes(b"previous library")
    with pytest.raises(ValueError, match="binary exports engine rev"):
        stage_script.stage(library, ENGINE_REV)
    assert staged.read_bytes() == b"previous library"


def test_staging_uses_new_library_name_without_stamp(stage_script, revision_cdylib):
    library = revision_cdylib(ENGINE_REV)
    dest = stage_script.ROOT / "src/fontisan/lib"
    dest.mkdir(parents=True)
    (dest / "ENGINE_REV").write_text(ENGINE_REV)
    (dest / "libfontisan.so").write_bytes(b"legacy library")
    stage_script.stage(library, ENGINE_REV)
    assert sorted(path.name for path in dest.iterdir()) == [library.name]
    assert (dest / library.name).read_bytes() == library.read_bytes()


def test_engine_pin_is_generated_from_pinned_crate(stage_script, monkeypatch):
    source = stage_script.ROOT / "fontisan"
    manifest = source / stage_script.CARGO_PATH
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        '[dependencies]\n'
        'fontisan = { git = "https://github.com/fontist/fontisan-rs", '
        f'rev = "{ENGINE_REV}", features = ["ffi"] }}\n'
    )
    revision = "1" * 40
    (stage_script.ROOT / "FONTISAN_REV").write_text(revision)
    monkeypatch.setattr(
        stage_script.subprocess, "check_output",
        lambda args, **kwargs: revision if "rev-parse" in args else manifest.read_text(),
    )
    (stage_script.ROOT / "src/fontisan").mkdir(parents=True)
    derived = stage_script.source_engine_rev(source)
    assert derived == ENGINE_REV
    stage_script.update_engine_pin(derived)
    stage_script.check_engine_pin(derived)
    assert (stage_script.ROOT / "ENGINE_REV").read_text().strip() == ENGINE_REV
    (stage_script.ROOT / "FONTISAN_REV").write_text("2" * 40)
    with pytest.raises(ValueError, match="source checkout"):
        stage_script.source_engine_rev(source)


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
