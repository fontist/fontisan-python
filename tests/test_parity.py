"""Corpus parity: Python results through the C ABI vs the Ruby-tier goldens.

Port of fontisan-rs crates/fontisan/tests/ffi_read_ops.rs (read, audit, scan,
malformed, audit_dir): same goldens, same comparison rules. Totals are printed
and asserted so a silently shrinking corpus fails.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

import fontisan
from conftest import font_path, load_json

VARIANTS = ("full/lazy", "full/eager", "metadata/lazy", "metadata/eager")
COUNTS: dict[str, int] = {}


def bump(key: str, n: int = 1) -> None:
    COUNTS[key] = COUNTS.get(key, 0) + n


def norm(s: str) -> str:
    return re.sub(r"\d+", "<N>", s)


def read_cases(corpus: Path):
    root = corpus / "goldens" / "read"
    for path in sorted(root.glob("*.json")):
        g = load_json(path)
        if g.get("tier") != "ci":
            continue
        yield g["id"], g["file"], font_path(corpus, g["file"]).read_bytes(), g, False
    for path in sorted((root / "_swallow").glob("*.json")):
        font = path.with_suffix(".ttf")
        yield f"_swallow/{path.stem}", font.name, font.read_bytes(), load_json(path), True


def read_entry(g, key):
    e = g["read"][key]
    return g["read"][e["same_as"]] if isinstance(e.get("same_as"), str) else e


def error_doc(err: fontisan.FontisanError, normalise=False):
    msg = norm(err.message) if normalise else err.message
    causes = [{**c, "message": norm(c["message"])} if normalise else c for c in err.causes]
    return err.error_class, msg, causes


def test_read_matches_goldens(corpus):
    ok = errors = unsupported = 0
    for cid, _file, data, g, swallow in read_cases(corpus):
        for key in VARIANTS:
            if swallow and key != "full/eager":
                continue
            want = read_entry(g, key)
            mode, lazy = key.split("/")
            what = f"{cid} {key}"
            try:
                got = fontisan.read(data, metadata=mode == "metadata", lazy=lazy == "lazy")
            except fontisan.UnsupportedError:
                unsupported += 1  # dfont / Type 1: the golden is ok, Ruby serves it
                continue
            except fontisan.FontisanError as err:
                assert "error" in want, f"{what}: unexpected error {err}"
                assert err.error_class == want["error"]["class"], what
                assert err.message == want["error"]["message"], what
                errors += 1
                continue
            assert "ok" in want, f"{what}: expected an error"
            faces = want["ok"]
            assert len(got) == len(faces), f"{what}: face count"
            deduped = isinstance(g["read"][key].get("same_as"), str)
            for i, (have, w) in enumerate(zip(got, faces)):
                if deduped:
                    # the golden dedups eager as `same_as` lazy, ignoring the echoed lazy/mode
                    assert have["lazy"] == (lazy == "lazy"), what
                    have = {**have, "lazy": w["lazy"]}
                    assert have["mode"] == mode, what
                    have = {**have, "mode": w["mode"]}
                diff = [k for k in w if have.get(k) != w[k]]
                assert not diff and have == w, f"{what}[{i}]: differing keys {diff}"
                ok += 1
    COUNTS.update(read_faces=ok, read_errors=errors, read_unsupported=unsupported)
    assert ok >= 150 and unsupported >= 4, (ok, unsupported)


def test_audit_matches_goldens(corpus):
    ok = errors = unsupported = 0
    for cid, file, data, g, _swallow in read_cases(corpus):
        for profile, validate in (("default", False), ("validate", True)):
            want = g["audit"][profile]
            what = f"{cid} {profile}"
            try:
                got = fontisan.audit(data, file, validate=validate)
            except fontisan.UnsupportedError:
                unsupported += 1
                continue
            except fontisan.FontisanError as err:
                assert "error" in want, f"{what}: unexpected error {err}"
                assert err.error_class == want["error"]["class"], what
                assert err.message == want["error"]["message"], what
                errors += 1
                continue
            assert "ok" in want, f"{what}: expected an error"
            assert got == want["ok"], what
            ok += len(got)
    COUNTS.update(audit_reports=ok, audit_errors=errors, audit_unsupported=unsupported)
    assert ok >= 60, ok


def test_scan_one_file_matches_scan_goldens(corpus):
    matched = unsupported = 0
    for path in sorted((corpus / "goldens" / "scan").glob("*.json")):
        g = load_json(path)
        if g.get("tier") != "ci":
            continue
        font = font_path(corpus, g["file"])
        got = fontisan.scan(font)
        if got[0]["status"] == "unsupported":
            assert len(got) == 1, g["id"]
            unsupported += 1
            continue
        want = g["rows"]
        assert len(got) == len(want), f"{g['id']}: rows"
        for n, (have, w) in enumerate(zip(got, want)):
            have = dict(have)
            assert have.pop("status") == "ok"
            assert have.pop("path").endswith(w["path"]), g["id"]
            assert have == {k: v for k, v in w.items() if k != "path"}, f"{g['id']}[{n}]"
            matched += 1
    COUNTS.update(scan_rows=matched, scan_unsupported=unsupported)
    assert matched >= 40 and unsupported >= 2, (matched, unsupported)


def test_malformed_goldens_match(corpus):
    files = sorted((corpus / "goldens" / "malformed").glob("*.json"))
    assert len(files) == 17
    reads = audits = scans = 0
    for path in files:
        g = load_json(path)
        mid, font = g["id"], font_path(corpus, g["file"])
        data = font.read_bytes()
        for combo in ("full/lazy=false", "full/lazy=true", "metadata/lazy=false", "metadata/lazy=true"):
            mode, lz = combo.split("/lazy=")
            want = g["combos"][combo]["ops"]["read"]
            what = f"{mid} {combo}"
            try:
                fontisan.read(data, metadata=mode == "metadata", lazy=lz == "true")
                assert want["outcome"] == "ok", f"{what}: expected an error"
            except fontisan.FontisanError as err:
                assert want["outcome"] != "ok", f"{what}: unexpected error {err}"
                cls, msg, causes = error_doc(err, True)
                assert (cls, msg, causes) == (want["error_class"], want["message"], want["causes"]), what
            reads += 1
        want = g["audit"]
        try:
            fontisan.audit(data, g["file"])
            assert want["outcome"] == "ok", f"{mid} audit: expected an error"
        except fontisan.FontisanError as err:
            assert want["outcome"] != "ok", f"{mid} audit: unexpected error {err}"
            assert error_doc(err, True) == (want["error_class"], want["message"], want["causes"]), mid
        audits += 1
        want = g["scan"]["summary"][0]
        row = fontisan.scan(font)[0]
        assert row["format"] == want["format"] and row["num_faces"] == want["num_faces"], f"{mid} scan"
        for slot in ("font_file", "collection_file"):
            have, w = row["errors"][slot], want["errors"][slot]
            if w is None:
                assert have is None, f"{mid} scan {slot}"
                continue
            assert have["class"] == w["class"], f"{mid} scan {slot}"
            assert norm(have["message"]) == w["message"], f"{mid} scan {slot}"
            assert (have.get("cause") or {}).get("class") == (w.get("cause") or {}).get("class"), f"{mid} scan {slot} cause"
        scans += 1
    COUNTS.update(malformed_reads=reads, malformed_audits=audits, malformed_scans=scans)


def test_scan_and_audit_dir_serve_a_mixed_directory(corpus, tmp_path):
    (tmp_path / "sub").mkdir()
    for name, sub in (
        ("TestTTF.ttf", ""),
        ("TestTTC.ttc", ""),
        ("TestDFONT.dfont", ""),
        ("TestT1-Regular.pfb", "sub"),
        ("TestOTF.otf", "sub"),
    ):
        shutil.copy(font_path(corpus, name), tmp_path / sub / name)
    (tmp_path / "README.txt").write_bytes(b"not a font")
    (tmp_path / "broken.ttf").write_bytes(font_path(corpus, "TestTTF.ttf").read_bytes()[:100])

    scan = fontisan.scan(tmp_path)
    paths = [r["path"] for r in scan]
    assert paths == sorted(paths)
    assert not any(p.endswith("README.txt") for p in paths)

    def status(rows, name):
        return [r["status"] for r in rows if r["path"].endswith(name)]

    assert status(scan, "TestDFONT.dfont") == ["unsupported"]
    assert status(scan, "TestT1-Regular.pfb") == ["unsupported"]
    assert status(scan, "TestTTF.ttf") == ["ok"]
    assert status(scan, "TestTTC.ttc") == ["ok", "ok"]
    broken = next(r for r in scan if r["path"].endswith("broken.ttf"))
    assert broken["status"] == "ok" and broken["errors"]["font_file"] is not None

    for validate in (False, True):
        audit = fontisan.audit_dir(tmp_path, validate=validate)
        by = {Path(r["path"]).name: r for r in audit}
        assert len(audit) == 6
        assert by["TestDFONT.dfont"]["status"] == "unsupported"
        assert by["TestT1-Regular.pfb"]["status"] == "unsupported"
        assert len(by["TestTTC.ttc"]["reports"]) == 2
        ttf = by["TestTTF.ttf"]["reports"][0]
        assert ttf["source_file"] == "TestTTF.ttf"
        assert ("validation_summary" in ttf) == validate
        assert by["broken.ttf"]["status"] == "error"
        assert by["broken.ttf"]["error"]["class"] == "Fontisan::Error"
        assert fontisan.audit_file(tmp_path / "TestTTF.ttf", validate=validate)[0] == ttf
    COUNTS["audit_dir_files"] = 6


def test_zz_summary(corpus, capsys):
    """Runs last: prints the parity totals (use `pytest -s` to see them)."""
    with capsys.disabled():
        print("\nparity totals:", COUNTS)
