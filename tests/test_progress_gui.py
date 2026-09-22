"""Progresión en la interfaz (Qt 'offscreen'): pistas, evaluación con XP, panel de progreso, caso del día."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from vsm.cases import CASES
from vsm.hints import hints_cost
from vsm.main_window import MainWindow
from vsm.progress import Progress, daily_case
from vsm.progress_dialogs import HintDialog, ProgressDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    monkeypatch.setattr(QDialog, "exec_", lambda self: 0)          # los diálogos modales no bloquean
    w = MainWindow(progress=Progress(str(tmp_path / "p.json")))
    w.load_case(CASES["taburetes"])
    w.canvas.set_map(CASES["taburetes"].reference_map())
    return w


def test_dialogo_de_pistas_revela_y_suma_costo(app):
    c, used = CASES["taburetes"], set()
    d = HintDialog(c, used)
    assert "takt" in d.buttons
    d.buttons["takt"].click()
    assert used == {"takt"} and "takt" not in d.buttons
    assert "−2 pts" in d.total.text()
    d.buttons["bottleneck"].click()
    assert hints_cost(c, used) == 6 and "−6 pts" in d.total.text()


def test_evaluar_suma_xp_y_las_pistas_restan(win):
    win._hints_used["taburetes"] = {"takt", "lead"}                # 2 + 5 = 7 pts
    win.evaluate_map()
    e = win.progress.entry("taburetes")
    assert e["best_net"] == 93 and e["passed"] and win.progress.xp == e["xp"] > 0
    assert str(win.progress.xp) in win.rank_label.text()


def test_ver_la_solucion_no_da_xp(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win.show_reference()
    win.evaluate_map()
    assert win.progress.xp == 0 and win.progress.entry("taburetes")["attempts"] == 0


def test_caso_del_dia_carga_el_caso_y_avisa(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)    # confirma reemplazar el mapa
    win.open_daily_case()
    from datetime import date
    assert win.case is daily_case(date.today())
    assert "Caso del día" in win.case_view.toHtml()


def test_panel_de_progreso_y_menu(win):
    win.evaluate_map()
    d = ProgressDialog(win.progress)
    assert d.table.rowCount() == 6 and "Cinturón" in d.belt_lbl.text()
    assert "Progreso" in [a.text().replace("&", "") for a in win.menuBar().actions()]
    win.open_progress()
    win.open_hints()


def test_pistas_sin_caso_avisan(app, tmp_path, monkeypatch):
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[1]))
    w = MainWindow(progress=Progress(str(tmp_path / "p.json")))
    w.open_hints()
    assert avisos == ["Sin caso"]


def test_cargar_el_caso_de_nuevo_reinicia_pistas_y_solucion_vista(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win._hints_used["taburetes"] = {"takt", "lead"}
    win._update_hint_button()
    assert "−7 pts" in win.hint_btn.text()
    win.show_reference()
    assert "taburetes" in win._solution_seen
    win.load_case(CASES["taburetes"])                              # intento nuevo
    assert win._hints_used["taburetes"] == set() and "taburetes" not in win._solution_seen
    assert win.hint_btn.text() == "Pedir pista"


def test_usar_todas_las_pistas_cuesta_18_y_aun_aprueba(win):
    win._hints_used["taburetes"] = {h.id for h in __import__("vsm.hints", fromlist=["x"]).available_hints(CASES["taburetes"])}
    win.canvas.set_map(CASES["taburetes"].reference_map())
    win.evaluate_map()                                              # 100 − 18 = 82: aún aprueba
    assert win.progress.entry("taburetes")["best_net"] == 82 and win.progress.xp > 0
