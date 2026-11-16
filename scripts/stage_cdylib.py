#!/usr/bin/env python3
"""Derive the engine pin from the pinned Ruby crate and verify a built cdylib."""
import argparse
import ast
import ctypes
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARIES = ("libfontisan_cdylib.so", "libfontisan_cdylib.dylib", "fontisan_cdylib.dll")
CARGO_PATH = "ext/fontisan_cdylib/Cargo.toml"


def source_engine_rev(source):
    """Read the inline dependency used by the pinned standalone Rust crate.

    Keep this deliberately narrow so Python 3.9 needs no TOML dependency. If
    upstream changes the dependency layout, fail instead of guessing a pin.
    """
    source = source.resolve()
    expected = (ROOT / "FONTISAN_REV").read_text().strip()
    actual = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != expected:
        raise ValueError(f"source checkout is {actual}; FONTISAN_REV pins {expected}")
    manifest = (source / CARGO_PATH).read_text()
    committed = subprocess.check_output(
        ["git", "-C", str(source), "show", f"HEAD:{CARGO_PATH}"], text=True
    )
    if manifest != committed:
        raise ValueError("source Cargo.toml differs from the pinned commit")
    section = re.search(r"(?ms)^\[dependencies\]\s*\n(.*?)(?=^\[|\Z)", manifest)
    dependency = re.search(r"(?ms)^fontisan\s*=\s*\{([^}]+)\}", section[1]) if section else None
    if dependency is None:
        raise ValueError("expected an inline fontisan dependency in Cargo.toml")
    git = re.search(r'\bgit\s*=\s*"([^"]+)"', dependency[1])
    rev = re.search(r'\brev\s*=\s*"([0-9a-f]{40})"', dependency[1])
    if git is None or git[1] != "https://github.com/fontist/fontisan-rs" or rev is None:
        raise ValueError("expected fontist/fontisan-rs with an exact 40-character rev")
    return rev[1]


def check_engine_pin(rev):
    pinned = (ROOT / "ENGINE_REV").read_text().strip()
    module = ast.parse((ROOT / "src/fontisan/_engine.py").read_text())
    generated = [
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "ENGINE_REV" for target in node.targets)
    ]
    if pinned != rev or generated != [rev]:
        raise ValueError("engine pins differ from Cargo.toml; run with --update-engine-rev")


def update_engine_pin(rev):
    (ROOT / "ENGINE_REV").write_text(rev + "\n")
    (ROOT / "src/fontisan/_engine.py").write_text(
        '\"\"\"Generated from the pinned fontisan cdylib Cargo.toml.\n\n'
        'Regenerate with scripts/stage_cdylib.py --fontisan-source <checkout> --update-engine-rev.\n\"\"\"\n\n'
        f'ENGINE_REV = "{rev}"\n'
    )


def stage(binary, rev):
    binary = binary.resolve()
    if binary.name not in LIBRARIES:
        raise ValueError(f"unexpected library name: {binary.name}")
    library = ctypes.CDLL(str(binary))
    exported_rev = library.fontisan_cdylib_engine_rev
    exported_rev.argtypes = []
    exported_rev.restype = ctypes.c_char_p
    actual = exported_rev()
    if actual != rev.encode("ascii"):
        raise ValueError(f"binary exports engine rev {actual!r}; Cargo.toml pins {rev}")
    dest = ROOT / "src/fontisan/lib"
    dest.mkdir(parents=True, exist_ok=True)
    # Validate everything before replacing any previously staged library.
    target = dest / binary.name
    if binary != target.resolve():
        shutil.copy2(binary, target)
    for name in (*LIBRARIES, "libfontisan.so", "libfontisan.dylib", "fontisan.dll", "ENGINE_REV"):
        old = dest / name
        if old != target:
            old.unlink(missing_ok=True)
    print(f"staged {binary.name} @ {rev} -> {dest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", nargs="?", type=Path, help="built cdylib to verify and stage")
    parser.add_argument("--fontisan-source", required=True, type=Path, help="checkout at FONTISAN_REV")
    parser.add_argument("--update-engine-rev", action="store_true", help="regenerate ENGINE_REV and _engine.py from Cargo.toml")
    args = parser.parse_args()
    if args.binary is None and not args.update_engine_rev:
        parser.error("binary is required unless --update-engine-rev is used")
    try:
        rev = source_engine_rev(args.fontisan_source)
        if args.update_engine_rev:
            update_engine_pin(rev)
            print(f"generated engine pins @ {rev}")
        check_engine_pin(rev)
        if args.binary is not None:
            stage(args.binary, rev)
    except (OSError, ValueError, AttributeError, subprocess.CalledProcessError) as exc:
        sys.exit(f"refusing to stage: {exc}")


if __name__ == "__main__":
    main()
