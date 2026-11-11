from pathlib import Path

from fontisan._engine import ENGINE_REV

ROOT = Path(__file__).resolve().parents[1]


def test_engine_pin_files_agree():
    assert ENGINE_REV == (ROOT / "ENGINE_REV").read_text().strip()
    assert len(ENGINE_REV) == 40
