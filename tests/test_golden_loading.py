"""Goldens use UTF-8 regardless of the runner's locale."""

from pathlib import Path

from conftest import load_json


def test_load_json_preserves_unicode_with_windows_default_encoding(tmp_path, monkeypatch):
    golden = tmp_path / "golden.json"
    golden.write_bytes('{"name": "Mix Café", "message": "widths — alignment"}'.encode("utf-8"))
    original_read_text = Path.read_text

    def windows_read_text(path, encoding=None, errors=None, **kwargs):
        return original_read_text(path, encoding=encoding or "cp1252", errors=errors, **kwargs)

    monkeypatch.setattr(Path, "read_text", windows_read_text)
    assert load_json(golden) == {"name": "Mix Café", "message": "widths — alignment"}
