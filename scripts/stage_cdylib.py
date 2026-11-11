#!/usr/bin/env python3
"""Vendor a built fontisan cdylib into the package and stamp the engine rev.

usage: stage_cdylib.py <path-to-cdylib> [<engine-rev>]

The rev defaults to the repo-root ENGINE_REV pin; the stamp (lib/ENGINE_REV)
is what the loader checks, because the pinned engine exports no rev symbol.
"""
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1])
rev = sys.argv[2] if len(sys.argv) > 2 else (root / "ENGINE_REV").read_text().strip()
if rev != (root / "ENGINE_REV").read_text().strip():
    sys.exit(f"refusing to stage rev {rev}: repo pins {(root / 'ENGINE_REV').read_text().strip()}")
dest = root / "src" / "fontisan" / "lib"
dest.mkdir(parents=True, exist_ok=True)
for old in dest.iterdir():
    old.unlink()
shutil.copy2(src, dest / src.name)
(dest / "ENGINE_REV").write_text(rev + "\n")
print(f"staged {src.name} @ {rev} -> {dest}")
