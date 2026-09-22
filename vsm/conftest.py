"""Aísla el progreso de los tests: nunca escribe en ~/.simulador_vsm."""
import pytest


@pytest.fixture(autouse=True)
def _progreso_temporal(tmp_path, monkeypatch):
    monkeypatch.setenv("VSM_PROGRESS_FILE", str(tmp_path / "progreso_test.json"))
