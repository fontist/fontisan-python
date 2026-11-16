import hashlib
import json
import os
import runpy
import stat
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "corpus_fetch.py"


def git(path, *args, env=None):
    return subprocess.check_output(["git", "-C", str(path), *args], env=env, text=True).strip()


def test_fetches_pinned_corpus_without_partial_clone(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "fixture@example.test")
    git(source, "config", "user.name", "fixture")
    corpus = source / "corpus"
    (corpus / "fonts" / "fixture").mkdir(parents=True)
    derived = b"pinned derived font bytes"
    (corpus / "fonts" / "fixture" / "derived.ttf").write_bytes(derived)
    manifest = {"fonts": [{"id": "fixture", "type": "derived", "tier": "ci", "file": "derived.ttf"}]}
    (corpus / "manifest.json").write_text(json.dumps(manifest))
    source_bytes = b"pinned source font bytes"
    source_file = tmp_path / "source-font.ttf"
    source_file.write_bytes(source_bytes)
    source_entry = {
        "id": "source-fixture", "type": "source", "tier": "ci", "file": "source.ttf",
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source": {"url": source_file.as_uri()},
    }
    manifest["fonts"].append(source_entry)
    (corpus / "manifest.json").write_text(json.dumps(manifest))
    git(source, "add", "corpus")
    git(source, "-c", "commit.gpgsign=false", "commit", "-m", "pinned corpus")
    pin = git(source, "rev-parse", "HEAD")
    (corpus / "fonts" / "fixture" / "derived.ttf").write_bytes(b"later HEAD bytes")
    git(source, "-c", "commit.gpgsign=false", "commit", "-am", "later corpus")

    harness = tmp_path / "harness"
    (harness / "scripts").mkdir(parents=True)
    (harness / "scripts" / "corpus_fetch.py").write_bytes(SCRIPT.read_bytes())
    (harness / "CORPUS_REV").write_text(pin)
    # Git's URL rewrite substitutes the local fixture for the script's fixed remote.
    env = os.environ.copy()
    env.pop("FONTISAN_CORPUS_SRC", None)
    env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "url." + source.as_uri() + ".insteadOf",
                "GIT_CONFIG_VALUE_0": "https://github.com/fontist/fontisan"})
    dest = tmp_path / "result"
    subprocess.check_call([sys.executable, str(harness / "scripts" / "corpus_fetch.py"), str(dest)], env=env)

    assert (dest / "corpus" / "fonts" / "fixture" / "derived.ttf").read_bytes() == derived
    source_target = dest / "corpus" / "fonts" / "source-fixture" / "source.ttf"
    assert source_target.read_bytes() == source_bytes
    assert json.loads((dest / "corpus" / "manifest.json").read_text()) == manifest
    assert not (dest / "_clone").exists()

    source_target.write_bytes(b"corrupted bytes")
    subprocess.check_call([sys.executable, str(harness / "scripts" / "corpus_fetch.py"), str(dest)], env=env)
    assert source_target.read_bytes() == source_bytes
    assert hashlib.sha256(source_target.read_bytes()).hexdigest() == source_entry["sha256"]


def test_cleanup_retries_readonly_git_pack_and_propagates_other_errors(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "manifest.json").write_text('{"fonts": []}')
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(tmp_path)])
    cleanup = runpy.run_path(str(SCRIPT))["_remove_readonly"]
    pack = tmp_path / "pack.pack"
    pack.write_bytes(b"pack")
    pack.chmod(stat.S_IREAD)

    def windows_unlink(path):
        if not path.stat().st_mode & stat.S_IWRITE:
            raise PermissionError("read-only pack")
        path.unlink()

    cleanup(windows_unlink, pack, (PermissionError, PermissionError("read-only pack"), None))
    assert not pack.exists()
    error = OSError("other cleanup error")
    with pytest.raises(OSError, match="other cleanup error"):
        cleanup(windows_unlink, pack, (OSError, error, None))
