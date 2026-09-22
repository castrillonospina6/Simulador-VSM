"""Smoke test de la interfaz en modo headless (Qt 'offscreen')."""
import json
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QPointF, QMimeData
from PyQt5.QtGui import QDropEvent

from vsm.main_window import MainWindow
from vsm.cases import CASES
from vsm.toolbox import MIME_TYPE
from vsm.evaluation import evaluate
from vsm.models import PROCESS_KINDS


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _drop(cv, kind, x, y):
    mime = QMimeData()
    mime.setData(MIME_TYPE, json.dumps({"kind": kind, "preset": {}}).encode())
    ev = QDropEvent(QPointF(cv.mapFromScene(QPointF(x, y))), Qt.CopyAction, mime,
                    Qt.LeftButton, Qt.NoModifier)
    cv.dropEvent(ev)
    return list(cv.map.nodes.values())[-1]


def test_flujo_completo(app):
    w = MainWindow()
    w.show()
    w.load_case(CASES["taburetes"])
    cv = w.canvas
    sup, p1, cus = _drop(cv, "supplier", 50, 50), _drop(cv, "process", 300, 300), _drop(cv, "customer", 700, 50)
    p1.name, p1.cycle_time_s, p1.uptime_pct = "Pintura", 60, 90
    cv.item_for(p1.id).refresh()
    w.conn_actions["push"].setChecked(True)
    for a, b in ((sup, p1), (p1, cus)):
        cv._connect_click(cv.item_for(a.id))
        cv._connect_click(cv.item_for(b.id))
    assert len(cv.map.connections) == 2
    assert 0 < evaluate(cv.map, w.case).score < 60
    # borrar un nodo elimina sus flechas
    cv.item_for(p1.id).setSelected(True)
    cv.delete_selected()
    assert p1.id not in cv.map.nodes and not cv.map.connections


def test_referencia_marca_cuello_en_rojo(app):
    w = MainWindow()
    w.show()
    for cid, bott in (("taburetes", "Pintura"), ("farma", "Blisteado"), ("autopartes", "Soldadura")):
        w.canvas.set_map(CASES[cid].reference_map())
        reds = [n.name for n in w.canvas.map.nodes.values()
                if n.kind in PROCESS_KINDS and w.canvas.item_for(n.id).alert]
        assert reds == [bott]
