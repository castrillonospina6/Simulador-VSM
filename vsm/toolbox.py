"""Paleta de símbolos arrastrables hacia el canvas, agrupada por categorías.

Los íconos se generan con el MISMO código de dibujo que el canvas (modo ícono),
así que lo que ves en la paleta es exactamente lo que se coloca.
"""
from __future__ import annotations

import json
from typing import Dict, Optional

from PyQt5.QtCore import Qt, QSize, QMimeData, QRectF
from PyQt5.QtGui import QDrag, QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QAbstractItemView, QStyleOptionGraphicsItem)

from .canvas_items import create_item, ConnectionItem, NodeItem
from .models import make_node, Connection, CONN_KINDS

MIME_TYPE = "application/x-vsm-symbol"

# (clave, tipo de nodo, etiqueta, preset de atributos)
CATEGORIES = [
    ("Flujo de proceso", [
        ("supplier", "supplier", "Proveedor", None),
        ("customer", "customer", "Cliente", None),
        ("process", "process", "Proceso (casilla de proceso)", None),
        ("shared_process", "shared_process", "Proceso compartido", None),
        ("work_cell", "work_cell", "Celda de trabajo", None),
        ("operator", "operator", "Operario", None),
        ("data_box", "data_box", "Tabla de datos", None),
    ]),
    ("Material", [
        ("inventory", "inventory", "Inventario", None),
        ("supermarket", "supermarket", "Supermercado", None),
        ("fifo_lane", "fifo_lane", "Carril PEPS / FIFO (capacidad máx.)", None),
        ("safety_stock", "safety_stock", "Buffer / existencias de seguridad", None),
        ("buffer_point", "buffer_point", "Punto de acumulación BUFFER (B)", None),
        ("safety_point", "safety_point", "Punto de acumulación STOCK DE SEGURIDAD (S)", None),
        ("transport_truck", "transport", "Transporte · camión", {"mode": "camion", "name": "Camión"}),
        ("transport_plane", "transport", "Transporte · avión", {"mode": "avion", "name": "Avión"}),
        ("transport_ship", "transport", "Transporte · barco", {"mode": "barco", "name": "Barco"}),
        ("goods_arrow", "goods_arrow", "Flecha de transporte de mercancías", None),
        ("mp_pt_flow", "mp_pt_flow", "Flujo de MP y PT", None),
        ("pull_physical", "pull_physical", "Pull físico (retirada de supermercado)", None),
    ]),
    ("Información", [
        ("control", "control", "Control / planificación de la producción", None),
        ("database", "database", "Base de datos / sistema MRP-ERP", None),
        ("info_box", "info_box", "Caja de información", None),
    ]),
    ("Kanban y pull", [
        ("kanban_production", "kanban_production", "Kanban de producción", None),
        ("kanban_withdrawal", "kanban_withdrawal", "Retirada Kanban", None),
        ("kanban_batch", "kanban_batch", "Lote de tarjetas Kanban", None),
        ("kanban_signal", "kanban_signal", "Señal Kanban", None),
        ("kanban_post", "kanban_post", "Tarjeta Kanban (poste)", None),
        ("heijunka", "heijunka", "Nivelación de carga (heijunka)", None),
        ("pull_ball", "pull_ball", "Secuencia de tiro / pull ball", None),
    ]),
    ("Tiempo", [
        ("time_segment", "time_segment", "Línea de tiempo (segmento)", None),
        ("total_time", "total_time", "Tiempo total / duración total", None),
        ("clock", "clock", "Reloj (retraso / restricción)", None),
        ("rework", "rework", "Reelaboración", None),
    ]),
    ("Mejora", [
        ("kaizen", "kaizen", "Estallido Kaizen", None),
        ("observation", "observation", "Observación", None),
    ]),
]

ICON_W, ICON_H = 60, 46


def palette_kinds():
    """Tipos de nodo que aparecen en la paleta (para auditar la cobertura)."""
    return {kind for _, items in CATEGORIES for _, kind, _, _ in items}


def _render(paint_fn, rect: QRectF) -> QIcon:
    scale_up = 2
    pm = QPixmap(ICON_W * scale_up, ICON_H * scale_up)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    sc = min((ICON_W * scale_up - 8) / rect.width(), (ICON_H * scale_up - 8) / rect.height())
    p.translate((ICON_W * scale_up - rect.width() * sc) / 2, (ICON_H * scale_up - rect.height() * sc) / 2)
    p.scale(sc, sc)
    p.translate(-rect.left(), -rect.top())
    paint_fn(p)
    p.end()
    return QIcon(pm)


def make_icon(kind: str, preset: Optional[Dict] = None) -> QIcon:
    node = make_node(kind)
    for k, v in (preset or {}).items():
        setattr(node, k, v)
    if kind == "total_time":
        node.name = "Duración total"
    item: NodeItem = create_item(node)
    item.icon_mode = True
    item.setRotation(0)
    opt = QStyleOptionGraphicsItem()
    return _render(lambda p: item.paint(p, opt, None), item.icon_rect().adjusted(-2, -2, 2, 2))


class _Dummy(NodeItem):
    WIDTH, HEIGHT = 4.0, 4.0

    def paint(self, p, option, widget=None):
        pass


def make_conn_icon(kind: str) -> QIcon:
    a, b = make_node("info_box"), make_node("info_box")
    a.x, a.y, b.x, b.y = 0, 20, 110, 20
    src, dst = _Dummy(a), _Dummy(b)
    conn = ConnectionItem(Connection(id="x", source="a", target="b", kind=kind), src, dst)
    conn.icon_mode = True
    opt = QStyleOptionGraphicsItem()
    rect = QRectF(-4, 2, 118, 38)
    return _render(lambda p: (p.translate(0, 0), conn.paint(p, opt, None)), rect)


class ToolboxList(QListWidget):
    """Lista de símbolos por categoría; al arrastrar se envía tipo + preset por MIME."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(ICON_W, ICON_H))
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSpacing(1)
        self.setMinimumWidth(250)
        self.setWordWrap(True)
        for title, items in CATEGORIES:
            header = QListWidgetItem(title.upper())
            header.setFlags(Qt.NoItemFlags)
            f = QFont()
            f.setBold(True)
            f.setPointSize(8)
            header.setFont(f)
            header.setBackground(QColor("#e8edf3"))
            header.setForeground(QColor("#455a64"))
            self.addItem(header)
            for key, kind, label, preset in items:
                it = QListWidgetItem(make_icon(kind, preset), label)
                it.setData(Qt.UserRole, json.dumps({"kind": kind, "preset": preset or {}}))
                it.setToolTip(f"Arrastra «{label}» al canvas")
                it.setSizeHint(QSize(240, ICON_H + 6))
                self.addItem(it)

    def rebuild_icons(self):
        """Regenera los íconos (p. ej. al cambiar el estilo de símbolos)."""
        for i in range(self.count()):
            it = self.item(i)
            payload = it.data(Qt.UserRole)
            if payload:
                d = json.loads(payload)
                it.setIcon(make_icon(d["kind"], d.get("preset")))

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None or item.data(Qt.UserRole) is None:
            return
        mime = QMimeData()
        mime.setData(MIME_TYPE, str(item.data(Qt.UserRole)).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(item.icon().pixmap(ICON_W, ICON_H))
        drag.exec_(Qt.CopyAction)
