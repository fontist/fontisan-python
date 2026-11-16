#!/usr/bin/env python3
"""Fetch the shared fontisan corpus (fontist/fontisan `corpus/`) for the parity test.

usage: corpus_fetch.py [<dest>]      (default: ./.corpus/fontisan)

Mirrors `cargo xtask corpus-fetch` in fontisan-rs: the manifest, goldens and
derived fonts come from fontist/fontisan at the CORPUS_REV pin; the ci-tier
source fonts are downloaded from their pinned upstream URLs and sha256-checked.
The large tier (170 MB CJK collections) is not fetched.
FONTISAN_CORPUS_SRC may point at an existing fontisan checkout/export that
already holds `corpus/` (git is then not used).
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path


def _remove_readonly(function, path, exc_info):
    """Windows cannot unlink Git's read-only pack files until made writable."""
    if not isinstance(exc_info[1], PermissionError):
        raise exc_info[1]
    os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
    function(path)


root = Path(__file__).resolve().parents[1]
dest = Path(sys.argv[1]) if len(sys.argv) > 1 else root / ".corpus" / "fontisan"
rev = (root / "CORPUS_REV").read_text().strip()
corpus = dest / "corpus"

if not (corpus / "manifest.json").exists():
    dest.mkdir(parents=True, exist_ok=True)
    src = os.environ.get("FONTISAN_CORPUS_SRC")
    if src:
        shutil.copytree(Path(src) / "corpus", corpus)
    else:
        tmp = dest / "_clone"
        # Fetch all objects at the pin before checkout; no lazy blob hydration.
        tmp.mkdir()
        subprocess.check_call(["git", "-C", str(tmp), "init"])
        subprocess.check_call(["git", "-C", str(tmp), "remote", "add", "origin", "https://github.com/fontist/fontisan"])
        subprocess.check_call(["git", "-C", str(tmp), "fetch", "--depth=1", "origin", rev])
        subprocess.check_call(["git", "-C", str(tmp), "checkout", "FETCH_HEAD", "--", "corpus"])
        shutil.move(str(tmp / "corpus"), str(corpus))
        shutil.rmtree(tmp, onerror=_remove_readonly)

manifest = json.loads((corpus / "manifest.json").read_text())
n = 0
for font in manifest["fonts"]:
    if font["type"] != "source" or font["tier"] != "ci":
        continue
    target = corpus / "fonts" / font["id"] / font["file"]
    if not (target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == font["sha256"]):
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(font["source"]["url"].replace("[", "%5B").replace("]", "%5D")) as r:
            data = r.read()
        got = hashlib.sha256(data).hexdigest()
        if got != font["sha256"]:
            sys.exit(f"{font['id']}: sha256 {got} != manifest {font['sha256']}")
        target.write_bytes(data)
    n += 1
print(f"corpus-fetch: {n} ci source fonts verified in {corpus}")
