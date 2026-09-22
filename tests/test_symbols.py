"""Auditoría de cobertura: el 100 % de la iconografía de las fuentes está implementada."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QStyleOptionGraphicsItem
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtCore import QPointF

from vsm.models import (ALL_NODE_KINDS, CONN_KINDS, VSMMap, make_node, node_from_dict, Connection,
                        SYMBOL_SPECS, KIND_LABELS)
from vsm.symbol_catalog import CATALOG
from vsm.toolbox import palette_kinds, make_icon, make_conn_icon, ToolboxList
from vsm.canvas_items import create_item, ConnectionItem, set_symbol_style, STYLES
from vsm.dialogs import NodeEditDialog, ConnectionNoteDialog
from vsm.engine import compute_metrics


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_catalogo_apunta_a_simbolos_reales():
    for name, src, typ, key in CATALOG:
        if typ == "node":
            assert key in ALL_NODE_KINDS and key in palette_kinds(), name
        else:
            assert key in CONN_KINDS, name


def test_todo_nodo_esta_en_la_paleta_y_en_el_catalogo():
    catalogued = {k for _, _, t, k in CATALOG if t == "node"}
    assert set(ALL_NODE_KINDS) == palette_kinds() == catalogued
    assert set(CONN_KINDS) == {k for _, _, t, k in CATALOG if t == "conn"}
    assert all(k in KIND_LABELS for k in ALL_NODE_KINDS)


def test_cada_simbolo_se_dibuja_edita_y_serializa(app):
    img = QImage(400, 300, QImage.Format_ARGB32)
    for kind in ALL_NODE_KINDS:
        node = make_node(kind)
        assert node_from_dict(node.to_dict()).kind == kind
        item = create_item(node)
        p = QPainter(img)
        item.paint(p, QStyleOptionGraphicsItem(), None)
        p.end()
        assert item.boundingRect().width() > 0
        NodeEditDialog(node).accept()          # el formulario se construye y aplica sin errores
        assert not make_icon(kind).isNull()


def test_cada_conexion_se_dibuja(app):
    a, b = make_node("process", 0, 0), make_node("process", 400, 100)
    from vsm.canvas_items import ProcessItem
    ia, ib = ProcessItem(a), ProcessItem(b)
    img = QImage(600, 300, QImage.Format_ARGB32)
    for kind in CONN_KINDS:
        c = Connection("c", a.id, b.id, kind, note="200 uds")
        item = ConnectionItem(c, ia, ib)
        p = QPainter(img)
        item.paint(p, QStyleOptionGraphicsItem(), None)
        p.end()
        assert not make_conn_icon(kind).isNull()
    ConnectionNoteDialog(Connection("c", "a", "b", "fifo")).accept()


def test_mapa_con_todos_los_simbolos_roundtrip_y_motor():
    m = VSMMap()
    for i, kind in enumerate(ALL_NODE_KINDS):
        m.add_node(make_node(kind, i * 50, 0))
    ids = list(m.nodes)
    for k in CONN_KINDS:
        m.add_connection(ids[0], ids[1], k, note="x")
    back = VSMMap.from_dict(m.to_dict())
    assert len(back.nodes) == len(ALL_NODE_KINDS) and len(back.connections) == len(CONN_KINDS)
    assert all(c.note == "x" for c in back.connections)
    compute_metrics(back)


def test_familias_cuentan_en_el_motor():
    m = VSMMap()
    sh = make_node("shared_process", 0, 0); sh.cycle_time_s = 10
    cell = make_node("work_cell", 200, 0); cell.cycle_time_s = 20
    sm = make_node("supermarket", 100, 0); sm.quantity = 900        # 1 día a 900 u/día
    for n in (sh, sm, cell):
        m.add_node(n)
    r = compute_metrics(m)
    assert r.va_time_s == 30 and r.lead_time_days == pytest.approx(1 + 30 / 54000)
    assert [e.label for e in r.timeline] == ["Proceso compartido", "Supermercado", "Celda de trabajo"]


@pytest.mark.parametrize("style", STYLES)
def test_ambos_estilos_dibujan_todo(app, style):
    set_symbol_style(style)
    try:
        img = QImage(500, 300, QImage.Format_ARGB32)
        for kind in ALL_NODE_KINDS:
            item = create_item(make_node(kind))
            p = QPainter(img)
            item.paint(p, QStyleOptionGraphicsItem(), None)
            p.end()
            assert not make_icon(kind).isNull()
        for k in CONN_KINDS:
            assert not make_conn_icon(k).isNull()
    finally:
        set_symbol_style("tabla")


def test_carril_fifo_suma_al_lead_time():
    m = VSMMap()
    lane = make_node("fifo_lane", 0, 0); lane.quantity = 450; lane.capacity = 500
    m.add_node(lane)
    assert compute_metrics(m).lead_time_days == pytest.approx(0.5)
