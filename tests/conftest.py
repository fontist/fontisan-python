from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _corpus_root() -> Path:
    env = os.environ.get("FONTISAN_CORPUS_DIR")
    return Path(env) / "corpus" if env else ROOT / ".corpus" / "fontisan" / "corpus"


CORPUS = _corpus_root()


@pytest.fixture(scope="session")
def corpus() -> Path:
    if not (CORPUS / "goldens" / "read").is_dir() or not (CORPUS / "fonts").is_dir():
        if os.environ.get("FONTISAN_REQUIRE_CORPUS"):
            pytest.fail(f"corpus missing at {CORPUS}; run scripts/corpus_fetch.py")
        pytest.skip(f"corpus not fetched at {CORPUS} (scripts/corpus_fetch.py, or FONTISAN_CORPUS_DIR)")
    return CORPUS


def font_path(corpus: Path, name: str) -> Path:
    """Derived fonts live in corpus/derived, fetched sources in corpus/fonts/<id>/."""
    derived = corpus / "derived" / name
    if derived.exists():
        return derived
    for path in (corpus / "fonts").glob("*/*"):  # no pattern in `name`: names may contain [ ]
        if path.name == name:
            return path
    raise FileNotFoundError(f"{name} not in corpus/fonts or corpus/derived")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
