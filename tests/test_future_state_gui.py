"""Diálogos del estado futuro (calculadora de Kanban / supermercado y vista económica). Qt 'offscreen'."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QFileDialog

from vsm.calc_dialogs import PullCalcDialog, EconomicDialog
from vsm.canvas_view import CanvasView
from vsm.cases import CASES
from vsm.economics import analyze, scale_inventories, money
from vsm.main_window import MainWindow
from vsm.persistence import save_map


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_dialogo_kanban_coloca_en_el_mapa_y_se_deshace(app):
    cv = CanvasView(CASES["jugos"].reference_map())
    d = PullCalcDialog(cv)
    d.demand.setValue(1000)
    d.container.setValue(50)
    d.lead_unit.setCurrentIndex(d.lead_unit.findData("d"))
    d.lead.setValue(0.5)
    d.safety_pct.setValue(10)
    assert d._kanban.cards == 11 and "<b>11</b>" in d.k_out.text()
    n0 = len(cv.map.nodes)
    d._place_kanban()
    d._place_market()
    new = list(cv.map.nodes.values())[n0:]
    assert [n.kind for n in new] == ["kanban_production", "supermarket"]
    assert new[0].value == 50 and new[0].name == "11 tarjetas"
    assert new[1].quantity == round(d._market.avg_level)
    cv.undo()
    assert len(cv.map.nodes) == n0 + 1


def test_dialogo_kanban_muestra_errores_sin_romper(app):
    d = PullCalcDialog(CanvasView(CASES["jugos"].reference_map()))
    d.container.setValue(0)
    assert d._kanban is None and not d.k_btn.isEnabled() and "contenedor" in d.k_out.text()
    d.container.setValue(50)
    assert d.k_btn.isEnabled()


def test_dialogo_economico_escenario_y_comparacion_con_archivo(app, tmp_path, monkeypatch):
    m = CASES["taburetes"].reference_map()
    d = EconomicDialog(m)
    assert d.table.rowCount() == len(analyze(m).lines) + 1
    d.material.setValue(20)
    assert m.econ.material_cost == 20                                    # se escribe en el mapa
    assert "Elige una reducción" in d.result.text()
    d.reduction.setValue(50)
    d.invest.setValue(10000)
    assert "liberan" in d.result.text() and "meses" in d.result.text()
    assert "liberan" in d._summary

    fut = scale_inventories(m, 0.25)
    f = tmp_path / "futuro.vsm.json"
    save_map(fut, str(f))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(f), ""))
    d._load_future()
    assert d._future is not None and not d.reduction.isEnabled()
    cur = analyze(m)
    assert money(cur.capital_total - analyze(fut, m.econ).capital_total) in d.result.text()
    d._clear_future()
    assert d._future is None and d.reduction.isEnabled()


def test_menu_estado_futuro(app):
    w = MainWindow()
    titles = [a.text() for a in w.menuBar().actions()]
    assert "E&stado futuro" in titles


def test_acciones_del_menu_abren_los_dialogos(app):
    w = MainWindow()
    for abrir in (w.open_pull_calc, w.open_economics):
        QTimer.singleShot(50, lambda: app.activeModalWidget().accept())
        abrir()
