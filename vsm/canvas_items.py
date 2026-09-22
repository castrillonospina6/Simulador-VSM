"""Símbolos gráficos (QGraphicsObject) y flechas de conexión del canvas VSM.

Cubre el 100 % de la iconografía de las fuentes (libro de Dumser + tabla de
símbolos VSM). El mismo código de dibujo se reutiliza para los íconos de la
paleta (`icon_mode=True` omite los textos).
"""
from __future__ import annotations

import math

from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import (QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QPolygonF,
                         QPainterPath, QPainterPathStroker)
from PyQt5.QtWidgets import QGraphicsObject, QGraphicsPathItem, QGraphicsItem

from .models import KIND_LABELS

INK = QColor("#2c3e50")
ALERT = QColor("#c0392b")
SELECT = QColor("#2980b9")
PENDING = QColor("#e67e22")
YELLOW = QColor("#fff3a8")
LIGHT_BLUE = QColor("#dfe9f5")
BLUE_FILL = QColor("#bcd0f5")
NAVY = QColor("#1f3a6b")
GRAY = QColor("#7f8c8d")


# =============================================================================
# Estilo de símbolos: «tabla» (tabla de símbolos VSM) o «libro» (Dumser)
# =============================================================================
STYLES = ("tabla", "libro")
_STYLE = {"name": "tabla"}
ORANGE = QColor("#c55a11")


def set_symbol_style(name: str) -> None:
    if name in STYLES:
        _STYLE["name"] = name


def symbol_style() -> str:
    return _STYLE["name"]


def _tabla() -> bool:
    return _STYLE["name"] == "tabla"


# =============================================================================
# Alinear a rejilla (snap to grid)
# =============================================================================
_SNAP = {"enabled": False, "size": 20.0}


def set_snap_grid(enabled: bool, size: float = 20.0) -> None:
    _SNAP["enabled"] = bool(enabled)
    if size > 0:
        _SNAP["size"] = float(size)


def snap_grid_enabled() -> bool:
    return _SNAP["enabled"]


def snap_grid_size() -> float:
    return _SNAP["size"]


def _snap_point(pt: QPointF) -> QPointF:
    g = _SNAP["size"]
    return QPointF(round(pt.x() / g) * g, round(pt.y() / g) * g)


# =============================================================================
# Utilidades de dibujo
# =============================================================================
def _font(size: int = 8, bold: bool = False, italic: bool = False) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    f.setItalic(italic)
    return f


def _elide(painter: QPainter, text: str, width: float) -> str:
    return QFontMetrics(painter.font()).elidedText(text, Qt.ElideRight, int(width))


def _poly(points) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


def _arrow_points(r: QRectF, d: str) -> QPolygonF:
    """Flecha 'de bloque' dentro de `r` apuntando a left/right/up/down."""
    cy, cx = r.center().y(), r.center().x()
    if d in ("left", "right"):
        hl, sh = min(r.width() * 0.4, r.height()), r.height() * 0.5
        if d == "right":
            xh = r.right() - hl
            pts = [(r.left(), cy - sh / 2), (xh, cy - sh / 2), (xh, r.top()), (r.right(), cy),
                   (xh, r.bottom()), (xh, cy + sh / 2), (r.left(), cy + sh / 2)]
        else:
            xh = r.left() + hl
            pts = [(r.right(), cy - sh / 2), (xh, cy - sh / 2), (xh, r.top()), (r.left(), cy),
                   (xh, r.bottom()), (xh, cy + sh / 2), (r.right(), cy + sh / 2)]
    else:
        hl, sw = min(r.height() * 0.4, r.width()), r.width() * 0.5
        if d == "down":
            yh = r.bottom() - hl
            pts = [(cx - sw / 2, r.top()), (cx - sw / 2, yh), (r.left(), yh), (cx, r.bottom()),
                   (r.right(), yh), (cx + sw / 2, yh), (cx + sw / 2, r.top())]
        else:
            yh = r.top() + hl
            pts = [(cx - sw / 2, r.bottom()), (cx - sw / 2, yh), (r.left(), yh), (cx, r.top()),
                   (r.right(), yh), (cx + sw / 2, yh), (cx + sw / 2, r.bottom())]
    return _poly(pts)


def draw_operator(p: QPainter, cx: float, cy: float, s: float = 1.0, color: QColor = INK) -> None:
    """Pictograma del operario: cabeza (círculo) sobre los hombros (copa en U)."""
    p.save()
    p.setPen(QPen(color, 1.6 * s))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy - 3 * s), 4.5 * s, 4.5 * s)
    p.drawArc(QRectF(cx - 9 * s, cy - 4 * s, 18 * s, 16 * s), 180 * 16, 180 * 16)
    p.restore()


def _card_path(r: QRectF, dx: float = 0.0, dy: float = 0.0, cut: float = 14.0) -> QPolygonF:
    """Tarjeta Kanban: rectángulo con la esquina superior derecha cortada."""
    l, t, rr, b = r.left() + dx, r.top() + dy, r.right() + dx, r.bottom() + dy
    return _poly([(l, t), (rr - cut, t), (rr, t + cut), (rr, b), (l, b)])


# =============================================================================
# Nodos
# =============================================================================
class NodeItem(QGraphicsObject):
    """Base de todos los símbolos. Mantiene sincronizado el modelo (`node`)."""

    moved = pyqtSignal()
    WIDTH = 100.0
    HEIGHT = 60.0
    EXTRA_BOTTOM = 0.0

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.connections = []
        self.alert = False
        self.pending = False
        self.subtitle = ""
        self.lines = []
        self.icon_mode = False
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(node.x, node.y)
        self.setZValue(1)
        self.refresh()

    # -- geometría
    def body_rect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def boundingRect(self) -> QRectF:
        return self.body_rect().adjusted(-6, -6, 6, 6 + self.EXTRA_BOTTOM)

    def icon_rect(self) -> QRectF:
        """Zona que se muestra en el ícono de la paleta."""
        return self.body_rect()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and _SNAP["enabled"]:
            return _snap_point(value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.node.x, self.node.y = self.pos().x(), self.pos().y()
            for c in self.connections:
                c.update_path()
            self.moved.emit()
        return super().itemChange(change, value)

    # -- estado visual
    def set_alert(self, alert: bool):
        if alert != self.alert:
            self.alert = alert
            self.update()

    def set_pending(self, pending: bool):
        self.pending = pending
        self.update()

    def set_subtitle(self, text: str):
        if text != self.subtitle:
            self.subtitle = text
            self.update()

    def set_lines(self, lines):
        if list(lines) != self.lines:
            self.lines = list(lines)
            self.update()

    def refresh(self):
        self.prepareGeometryChange()
        self.setToolTip(f"{KIND_LABELS.get(self.node.kind, '')}: {self.node.name}")
        if self.node.kind == "goods_arrow":
            self.setTransformOriginPoint(self.body_rect().center())
            self.setRotation(float(self.node.value))
        for c in self.connections:
            c.update_path()
        self.update()

    # -- helpers de pintura
    def _pen(self, base: QColor = INK) -> QPen:
        if self.isSelected():
            return QPen(SELECT, 2.5)
        if self.pending:
            pen = QPen(PENDING, 3)
            pen.setStyle(Qt.DashLine)
            return pen
        if self.alert:
            return QPen(ALERT, 2.5)
        return QPen(base, 1.5)

    def _t(self, p: QPainter, rect: QRectF, flags, text: str) -> None:
        """drawText que se omite en modo ícono."""
        if not self.icon_mode and text:
            p.drawText(rect, flags, text)

    def _label_below(self, p: QPainter, r: QRectF, text: str, dy: float = 3.0, gray: bool = False):
        p.setFont(_font(8))
        p.setPen(GRAY if gray else INK)
        self._t(p, QRectF(r.left() - 30, r.bottom() + dy, r.width() + 60, 15), Qt.AlignCenter,
                _elide(p, text, r.width() + 56))


def _dash_pen() -> QPen:
    pen = QPen(INK, 1.4)
    pen.setStyle(Qt.DashLine)
    return pen


def _solid_head(p: QPainter, tip: QPointF, ux: float, uy: float, size: float = 8.0) -> None:
    nx, ny = -uy, ux
    p.save()
    p.setPen(QPen(INK, 1))
    p.setBrush(QBrush(INK))
    p.drawPolygon(QPolygonF([tip, QPointF(tip.x() - ux * size + nx * size * 0.5, tip.y() - uy * size + ny * size * 0.5),
                             QPointF(tip.x() - ux * size - nx * size * 0.5, tip.y() - uy * size - ny * size * 0.5)]))
    p.restore()


def _kanban_stubs(p: QPainter, r: QRectF, y: float, batch: bool = False) -> None:
    """Líneas punteadas de conexión de los símbolos Kanban (estilo tabla)."""
    p.save()
    p.setPen(_dash_pen())
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(r.right(), y), QPointF(r.right() + 38, y))
    if batch:
        p.drawLine(QPointF(r.left(), y), QPointF(r.left() - 20, y))
        p.restore()
        _solid_head(p, QPointF(r.left() - 30, y), -1, 0)
        return
    x = r.left() - 16
    p.drawLine(QPointF(r.left(), y), QPointF(x, y))
    p.drawLine(QPointF(x, y), QPointF(x, y + 28))
    p.restore()
    _solid_head(p, QPointF(x, y + 36), 0, 1)


# ---------------------------------------------------------------- procesos
class ProcessItem(NodeItem):
    WIDTH, HEIGHT = 165.0, 118.0

    def _draw_frame(self, p: QPainter, r: QRectF, header: QRectF):
        p.setPen(self._pen())
        p.setBrush(QColor("#fdecea") if self.alert else QColor("#ffffff"))
        p.drawRect(r)
        p.setBrush(QColor("#f5b7b1") if self.alert else LIGHT_BLUE)
        p.drawRect(header)

    def _draw_name(self, p: QPainter, header: QRectF):
        p.setFont(_font(9, bold=True))
        p.setPen(INK)
        self._t(p, header.adjusted(4, 0, -4, 0), Qt.AlignCenter, _elide(p, self.node.name, header.width() - 8))

    def _draw_data(self, p: QPainter, x: float, y: float, w: float) -> float:
        n = self.node
        p.setFont(_font(8))
        p.setPen(INK)
        for line in (f"TC = {n.cycle_time_s:g} s", f"C/O = {n.changeover_s:g} s",
                     f"Disp. = {n.uptime_pct:g} %", f"{n.operators} oper. · {n.shifts} turno(s)"):
            self._t(p, QRectF(x, y, w, 16), Qt.AlignVCenter | Qt.AlignLeft, line)
            y += 17
        return y

    def _draw_operators(self, p: QPainter, r: QRectF, y: float):
        n = self.node.operators
        shown = min(n, 6)
        for i in range(shown):
            draw_operator(p, r.left() + 18 + i * 21, y, 0.9)
        if n > 6:
            p.setFont(_font(8, bold=True))
            p.setPen(INK)
            self._t(p, QRectF(r.left() + 18 + 6 * 21 - 8, y - 8, 30, 16), Qt.AlignVCenter, f"+{n - 6}")

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        header = QRectF(r.left(), r.top(), r.width(), 26)
        self._draw_frame(p, r, header)
        self._draw_name(p, header)
        y = self._draw_data(p, r.left() + 8, header.bottom() + 4, r.width() - 16)
        self._draw_operators(p, r, y + 6)


class SharedProcessItem(ProcessItem):
    """Proceso compartido: hoja apilada detrás + encabezado dividido en columnas."""

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        p.setPen(QPen(INK, 1))
        p.setBrush(QColor("#ecf0f1"))
        p.drawRect(r.translated(5, -5))                     # hoja de atrás (compartido)
        header = QRectF(r.left(), r.top(), r.width(), 26)
        self._draw_frame(p, r, header)
        p.setPen(QPen(QColor("#9fb3cc"), 1))
        for i in range(1, 5):
            x = r.left() + r.width() * i / 5
            p.drawLine(QPointF(x, header.top()), QPointF(x, header.bottom()))
        # nombre sobre una cinta blanca para que se lea sobre las columnas
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 215) if not self.alert else QColor(253, 236, 234, 230))
        p.drawRect(header.adjusted(14, 4, -14, -4))
        self._draw_name(p, header)
        y = self._draw_data(p, r.left() + 8, header.bottom() + 4, r.width() - 16)
        self._draw_operators(p, r, y + 6)


class WorkCellItem(ProcessItem):
    """Celda de trabajo: contorno en U que agrupa varios procesos."""

    WIDTH, HEIGHT = 165.0, 150.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        top = 24.0
        w, h = r.width(), r.height()
        u = QPolygonF([QPointF(0, top), QPointF(w * 0.30, top), QPointF(w * 0.30, top + 34),
                       QPointF(w * 0.70, top + 34), QPointF(w * 0.70, top), QPointF(w, top),
                       QPointF(w, h), QPointF(0, h)])
        pen = self._pen(NAVY)
        pen.setWidthF(max(pen.widthF(), 2.2))
        p.setPen(pen)
        p.setBrush(QColor("#fdecea") if self.alert else QColor("#ffffff"))
        p.drawPolygon(u)
        p.setFont(_font(9, bold=True))
        p.setPen(INK)
        self._t(p, QRectF(0, 2, w, 20), Qt.AlignCenter, _elide(p, self.node.name, w - 8))
        y = self._draw_data(p, 10, top + 38, w - 20)
        self._draw_operators(p, r, y + 6)


class DataBoxItem(NodeItem):
    """Tabla de datos: filas azules apiladas (una por línea de texto)."""

    WIDTH, ROW = 150.0, 20.0

    def _rows(self):
        return (self.node.text or "").split("\n")[:12] or [""]

    def body_rect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.ROW * len(self._rows()))

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#ffffff") if _tabla() else BLUE_FILL)
        p.setFont(_font(8))
        for i, row in enumerate(self._rows()):
            rr = QRectF(0, i * self.ROW, self.WIDTH, self.ROW)
            p.setPen(self._pen())
            p.drawRect(rr)
            p.setPen(INK)
            self._t(p, rr.adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, _elide(p, row, self.WIDTH - 10))


class OperatorItem(NodeItem):
    WIDTH, HEIGHT = 56.0, 42.0
    EXTRA_BOTTOM = 16.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        if self.isSelected():
            p.setPen(QPen(SELECT, 1.5, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.body_rect())
        draw_operator(p, self.WIDTH / 2, 18, 1.7, SELECT if self.isSelected() else INK)
        n = int(self.node.value)
        if n > 1:
            p.setFont(_font(8, bold=True))
            p.setPen(INK)
            self._t(p, QRectF(0, self.HEIGHT + 1, self.WIDTH, 14), Qt.AlignCenter, f"× {n}")


# ---------------------------------------------------------------- externos
class ExternalItem(NodeItem):
    """Proveedor o cliente (símbolo de fábrica)."""

    WIDTH, HEIGHT = 130.0, 84.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        n = self.node
        w, roof, h = self.WIDTH, 22.0, self.HEIGHT
        tooth = w / 3
        p.setPen(self._pen())
        p.setBrush(YELLOW)
        teeth = _poly([(0, roof)] + [pt for i in range(3) for pt in
                       ((tooth * i + tooth, 0), (tooth * (i + 1), roof))])
        p.drawPolygon(teeth)
        p.drawRect(QRectF(0, roof, w, h - roof))
        p.setPen(INK)
        box = QRectF(4, roof + 2, w - 8, 32)
        for size in (8, 7, 6):                       # reduce la letra hasta que el nombre quepa
            p.setFont(_font(size, bold=True))
            need = QFontMetrics(p.font()).boundingRect(box.toRect(), int(Qt.AlignCenter | Qt.TextWordWrap), n.name)
            if need.height() <= box.height():
                break
        self._t(p, box, Qt.AlignCenter | Qt.TextWordWrap, n.name)
        if n.note:
            p.setFont(_font(7))
            p.setPen(GRAY)
            self._t(p, QRectF(4, roof + 34, w - 8, 26), Qt.AlignCenter | Qt.TextWordWrap, n.note)


class TransportItem(NodeItem):
    """Transporte: camión, avión o barco según `mode`."""

    WIDTH, HEIGHT = 90.0, 40.0
    EXTRA_BOTTOM = 32.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        n = self.node
        dark, light = QColor("#34495e"), QColor("#ecf0f1")
        p.setPen(self._pen())
        p.setBrush(dark)
        mode = getattr(n, "mode", "camion")
        if mode == "avion":
            p.drawEllipse(QRectF(6, 15, 80, 10))                         # fuselaje
            p.drawPolygon(_poly([(40, 18), (54, 18), (38, 1), (30, 1)]))  # alas
            p.drawPolygon(_poly([(40, 22), (54, 22), (38, 39), (30, 39)]))
            p.drawPolygon(_poly([(10, 17), (20, 17), (12, 6), (6, 6)]))   # cola
            p.drawPolygon(_poly([(10, 23), (20, 23), (12, 34), (6, 34)]))
        elif mode == "barco":
            p.drawPolygon(_poly([(4, 24), (86, 24), (76, 38), (14, 38)]))  # casco
            p.setBrush(light)
            p.drawRect(QRectF(28, 12, 28, 12))                             # puente
            p.drawRect(QRectF(36, 4, 8, 8))                                # chimenea
            p.setBrush(dark)
            p.drawRect(QRectF(60, 16, 12, 8))                              # contenedor
        else:
            p.drawRect(QRectF(0, 0, 56, 32))                              # caja de carga
            p.drawPolygon(_poly([(58, 8), (76, 8), (90, 20), (90, 32), (58, 32)]))
            p.setBrush(light)
            p.drawEllipse(QPointF(16, 34), 6, 6)
            p.drawEllipse(QPointF(72, 34), 6, 6)
        p.setFont(_font(8))
        p.setPen(INK)
        self._t(p, QRectF(-20, 43, 130, 14), Qt.AlignCenter, _elide(p, n.name, 130))
        if n.transit_days:
            p.setPen(GRAY)
            self._t(p, QRectF(-20, 57, 130, 14), Qt.AlignCenter, f"{n.transit_days:g} d en tránsito")


class GoodsArrowItem(NodeItem):
    """Flecha de transporte / movimiento de mercancías (flecha hueca)."""

    WIDTH, HEIGHT = 120.0, 40.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(self._pen())
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(_arrow_points(self.body_rect(), "left"))


class MpPtFlowItem(NodeItem):
    """Flujo de MP y PT: flecha gris hacia abajo (entrada) y hacia arriba (salida)."""

    WIDTH, HEIGHT = 72.0, 84.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(self._pen(GRAY))
        p.setBrush(QColor("#d5d8dc"))
        p.drawPolygon(_arrow_points(QRectF(0, 0, 30, self.HEIGHT), "down"))
        p.setBrush(QColor("#eaecee"))
        p.drawPolygon(_arrow_points(QRectF(42, 0, 30, self.HEIGHT), "up"))


class PullPhysicalItem(NodeItem):
    """Pull físico: flecha circular (retirada de material de un supermercado)."""

    WIDTH, HEIGHT = 54.0, 54.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(SELECT if self.isSelected() else INK, 2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(6, 6, 42, 42), 90 * 16, 290 * 16)
        # punta de flecha al final del arco (90 + 290 = 380° → 20°)
        ang = math.radians(20)
        cx, cy, rr = 27, 27, 21
        tip = QPointF(cx + rr * math.cos(ang), cy - rr * math.sin(ang))
        tang = ang + math.pi / 2                         # sentido antihorario
        ux, uy = math.cos(tang), -math.sin(tang)
        nx, ny = -uy, ux
        p.setBrush(QBrush(INK))
        p.drawPolygon(QPolygonF([QPointF(tip.x() + ux * 7, tip.y() + uy * 7),
                                 QPointF(tip.x() + nx * 5, tip.y() + ny * 5),
                                 QPointF(tip.x() - nx * 5, tip.y() - ny * 5)]))


class PullBallItem(NodeItem):
    """Secuencia de tiro / pull ball: círculos concéntricos."""

    WIDTH, HEIGHT = 46.0, 46.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(SELECT if self.isSelected() else INK, 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(2, 2, 42, 42))
        p.drawEllipse(QRectF(12, 12, 22, 22))


# ---------------------------------------------------------------- inventarios
class InventoryBase(NodeItem):
    EXTRA_BOTTOM = 36.0

    def _draw_labels(self, p: QPainter, r: QRectF):
        p.setFont(_font(8))
        p.setPen(INK)
        self._t(p, QRectF(r.left() - 25, r.bottom() + 3, r.width() + 50, 16), Qt.AlignCenter,
                f"{self.node.quantity:,.0f} u")
        if self.subtitle:
            p.setPen(GRAY)
            self._t(p, QRectF(r.left() - 25, r.bottom() + 18, r.width() + 50, 16), Qt.AlignCenter,
                    self.subtitle)


class InventoryItem(InventoryBase):
    WIDTH, HEIGHT = 80.0, 60.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        p.setPen(self._pen())
        p.setBrush(ORANGE if _tabla() else YELLOW)
        p.drawPolygon(_poly([(r.width() / 2, 0), (0, r.height()), (r.width(), r.height())]))
        if not _tabla():
            p.setFont(_font(11, bold=True))
            p.setPen(INK)
            p.drawText(QRectF(0, 22, r.width(), 34), Qt.AlignCenter, "I")
        self._draw_labels(p, r)


class SupermarketItem(InventoryBase):
    """Supermercado: estantería de 3 niveles abierta a la izquierda."""

    WIDTH, HEIGHT = 64.0, 64.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        p.setPen(self._pen())
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(r.right() - 4, 0), QPointF(r.right() - 4, r.height()))
        for i in range(4):
            y = i * r.height() / 3
            p.drawLine(QPointF(0, y), QPointF(r.right() - 4, y))
        self._draw_labels(p, r)


class FifoLaneItem(InventoryBase):
    """Carril PEPS (FIFO): caja gris con la línea de flujo; la capacidad máxima va debajo."""

    WIDTH, HEIGHT = 136.0, 36.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        cy = r.center().y()
        p.setPen(self._pen())
        p.setBrush(QColor("#d5d8dc"))
        p.drawRect(QRectF(14, 3, r.width() - 40, r.height() - 6))
        p.setPen(QPen(INK, 1.6))
        p.drawLine(QPointF(0, cy), QPointF(r.right() - 8, cy))
        _solid_head(p, QPointF(r.right(), cy), 1, 0, 9)
        f = _font(12, bold=True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        p.setFont(f)
        p.setPen(QColor("#566573"))
        p.drawText(QRectF(14, 3, r.width() - 40, r.height() - 6), Qt.AlignCenter, "FIFO")
        p.setFont(_font(8))
        p.setPen(INK)
        self._t(p, QRectF(r.left(), r.bottom() + 3, r.width(), 15), Qt.AlignCenter,
                f"máx {self.node.capacity:g} uds")
        detail = f"{self.node.quantity:,.0f} u" + (f" · {self.subtitle}" if self.subtitle else "")
        p.setPen(GRAY)
        self._t(p, QRectF(r.left() - 10, r.bottom() + 18, r.width() + 20, 15), Qt.AlignCenter, detail)


class SafetyStockItem(InventoryBase):
    """Buffer / existencias de seguridad: tres casillas apiladas."""

    WIDTH, HEIGHT = 40.0, 84.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        p.setPen(self._pen())
        p.setBrush(LIGHT_BLUE)
        h = r.height() / 3
        for i in range(3):
            p.drawRect(QRectF(0, i * h, r.width(), h))
        self._draw_labels(p, r)


class _AccumulationPoint(InventoryBase):
    """Punto de acumulación: dos casillas apiladas con una letra (B / S)."""

    WIDTH, HEIGHT = 40.0, 70.0
    LETTER = "B"

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        p.setPen(self._pen())
        p.setBrush(QColor("#ffffff"))
        h = r.height() / 2
        p.drawRect(QRectF(0, 0, r.width(), h))
        p.setBrush(LIGHT_BLUE)
        p.drawRect(QRectF(0, h, r.width(), h))
        p.setFont(_font(11, bold=True))
        p.setPen(INK)
        p.drawText(QRectF(0, 0, r.width(), h), Qt.AlignCenter, self.LETTER)
        self._draw_labels(p, r)


class BufferPointItem(_AccumulationPoint):
    LETTER = "B"


class SafetyPointItem(_AccumulationPoint):
    LETTER = "S"


# ---------------------------------------------------------------- control / información
class ControlItem(NodeItem):
    WIDTH, HEIGHT = 190.0, 56.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        if _tabla():          # banda celeste arriba, cuerpo blanco con el nombre
            band = QRectF(r.left(), r.top(), r.width(), r.height() * 0.38)
            p.setPen(self._pen(GRAY))
            p.setBrush(QColor("#ffffff"))
            p.drawRect(r)
            p.setBrush(QColor("#66c2ff"))
            p.drawRect(band)
            p.setFont(_font(8, bold=True))
            p.setPen(INK)
            self._t(p, QRectF(r.left() + 4, band.bottom(), r.width() - 8, r.height() - band.height()),
                    Qt.AlignCenter | Qt.TextWordWrap, self.node.name)
            return
        p.setPen(self._pen())
        p.setBrush(QColor("#2c3e50"))
        p.drawRect(r)
        p.setFont(_font(9, bold=True))
        p.setPen(QColor("#ffffff"))
        self._t(p, r.adjusted(6, 0, -6, 0), Qt.AlignCenter | Qt.TextWordWrap, self.node.name)


class DatabaseItem(NodeItem):
    """Base de datos / sistema MRP-ERP: cilindro."""

    WIDTH, HEIGHT = 92.0, 84.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        w, h, e = self.WIDTH, self.HEIGHT, 14.0
        p.setPen(self._pen())
        p.setBrush(QColor("#e3ebf7"))
        path = QPainterPath()
        path.moveTo(0, e / 2)
        path.lineTo(0, h - e / 2)
        path.arcTo(QRectF(0, h - e, w, e), 180, 180)
        path.lineTo(w, e / 2)
        path.arcTo(QRectF(0, 0, w, e), 0, 180)
        p.drawPath(path)
        p.setBrush(QColor("#f4f7fc"))
        p.drawEllipse(QRectF(0, 0, w, e))
        p.setFont(_font(8, bold=True))
        p.setPen(INK)
        self._t(p, QRectF(4, e + 2, w - 8, h - 2 * e), Qt.AlignCenter | Qt.TextWordWrap, self.node.name)


class InfoBoxItem(NodeItem):
    """Caja de información: campo de texto."""

    WIDTH, HEIGHT = 150.0, 44.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        p.setPen(self._pen(NAVY))
        p.setBrush(QColor("#ffffff"))
        p.drawRect(r)
        p.setFont(_font(8))
        p.setPen(INK)
        self._t(p, r.adjusted(6, 2, -6, -2), Qt.AlignCenter | Qt.TextWordWrap, self.node.text)


# ---------------------------------------------------------------- Kanban / pull
class _KanbanCard(NodeItem):
    WIDTH, HEIGHT = 96.0, 46.0
    EXTRA_BOTTOM = 38.0
    STYLE = "production"      # production | withdrawal | batch

    def boundingRect(self) -> QRectF:
        b = super().boundingRect()
        return b.adjusted(-36, 0, 46, 0) if _tabla() else b

    def icon_rect(self) -> QRectF:
        r = self.body_rect()
        return r.adjusted(-34, 0, 40, 14) if _tabla() else r

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        if _tabla():
            _kanban_stubs(p, r, r.center().y(), batch=self.STYLE == "batch")
        p.setPen(self._pen())
        if self.STYLE == "batch":
            for k in (2, 1):                       # tarjetas de atrás
                p.setBrush(QColor("#ffffff"))
                p.drawPolygon(_card_path(r, 6 * k, -6 * k))
        p.setBrush(LIGHT_BLUE if self.STYLE != "withdrawal" else QColor("#ffffff"))
        p.drawPolygon(_card_path(r))
        if self.STYLE == "withdrawal":
            p.setBrush(QBrush(QColor("#95a5a6"), Qt.BDiagPattern))
            p.drawPolygon(_card_path(r))
            if not self.icon_mode:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#ffffff"))
                p.drawRect(QRectF(r.center().x() - 16, r.center().y() - 10, 32, 20))
        p.setFont(_font(11, bold=True))
        p.setPen(INK)
        self._t(p, r, Qt.AlignCenter, f"{self.node.value:g}")
        self._label_below(p, r, self.node.name, dy=20 if _tabla() else 3, gray=True)


class KanbanProductionItem(_KanbanCard):
    STYLE = "production"


class KanbanWithdrawalItem(_KanbanCard):
    STYLE = "withdrawal"


class KanbanBatchItem(_KanbanCard):
    STYLE = "batch"
    WIDTH = 90.0


class KanbanSignalItem(NodeItem):
    """Señal Kanban: triángulo invertido."""

    WIDTH, HEIGHT = 70.0, 60.0
    EXTRA_BOTTOM = 34.0

    def boundingRect(self) -> QRectF:
        b = super().boundingRect()
        return b.adjusted(-36, 0, 46, 0) if _tabla() else b

    def icon_rect(self) -> QRectF:
        r = self.body_rect()
        return r.adjusted(-34, 0, 40, 0) if _tabla() else r

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        if _tabla():
            _kanban_stubs(p, r, r.top() + 12)
        p.setPen(self._pen())
        p.setBrush(LIGHT_BLUE)
        p.drawPolygon(_poly([(0, 0), (r.width(), 0), (r.width() / 2, r.height())]))
        p.setFont(_font(9, bold=True))
        p.setPen(INK)
        self._t(p, QRectF(0, 6, r.width(), 24), Qt.AlignCenter, f"{self.node.value:g}")
        self._label_below(p, r, self.node.name, dy=16 if _tabla() else 3, gray=True)


class KanbanPostItem(NodeItem):
    """Tarjeta Kanban / poste: lugar donde se retiran las señales Kanban."""

    WIDTH, HEIGHT = 60.0, 66.0
    EXTRA_BOTTOM = 18.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(SELECT if self.isSelected() else INK, 2))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(10, 0), QPointF(10, 30))
        p.drawLine(QPointF(50, 0), QPointF(50, 30))
        p.drawLine(QPointF(10, 30), QPointF(50, 30))
        p.drawLine(QPointF(30, 30), QPointF(30, 62))
        p.drawLine(QPointF(14, 62), QPointF(46, 62))
        self._label_below(p, self.body_rect(), self.node.name, gray=True)


class HeijunkaItem(NodeItem):
    """Nivelación de carga (heijunka box): O X O X."""

    WIDTH, HEIGHT = 124.0, 40.0
    EXTRA_BOTTOM = 18.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        r = self.body_rect()
        p.setPen(self._pen())
        p.setBrush(LIGHT_BLUE)
        p.drawRect(r)
        f = _font(14, bold=True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        p.setFont(f)
        p.setPen(INK)
        p.drawText(r, Qt.AlignCenter, "OXOX")
        self._label_below(p, r, self.node.name, gray=True)


# ---------------------------------------------------------------- tiempo
class TimeSegmentItem(NodeItem):
    """Línea de tiempo (segmento): arriba espera (días), abajo proceso (s)."""

    WIDTH, HEIGHT = 160.0, 56.0

    def boundingRect(self) -> QRectF:
        return self.body_rect().adjusted(-6, -22, 6, 26)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.WIDTH, self.HEIGHT
        p.setPen(QPen(SELECT if self.isSelected() else ALERT, 2))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(0, 4))
        path.lineTo(w * 0.5, 4)
        path.lineTo(w * 0.5, h - 4)
        path.lineTo(w, h - 4)
        path.lineTo(w, 4)
        p.drawPath(path)
        p.setFont(_font(8))
        p.setPen(INK)
        self._t(p, QRectF(0, -16, w * 0.5, 16), Qt.AlignCenter, f"{self.node.value:g} d")
        self._t(p, QRectF(w * 0.5, h - 2, w * 0.5, 16), Qt.AlignCenter, f"{self.node.value2:g} s")


class TotalTimeItem(NodeItem):
    """Tiempo total / duración total: caja con lead time y tiempo VA (se actualiza en vivo)."""

    WIDTH, HEIGHT = 190.0, 50.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.WIDTH, self.HEIGHT
        box = QRectF(34, 0, w - 34, h)
        p.setPen(self._pen())
        p.drawLine(QPointF(0, h / 2), QPointF(34, h / 2))
        p.setBrush(LIGHT_BLUE)
        p.drawRect(box)
        p.drawLine(QPointF(box.left(), h / 2), QPointF(box.right(), h / 2))
        lines = self.lines or ["Lead time = —", "Tiempo VA = —"]
        p.setFont(_font(8, bold=True))
        p.setPen(INK)
        self._t(p, QRectF(box.left(), 0, box.width(), h / 2), Qt.AlignCenter, lines[0])
        self._t(p, QRectF(box.left(), h / 2, box.width(), h / 2), Qt.AlignCenter, lines[1])


class ClockItem(NodeItem):
    """Reloj: retraso o restricción de tiempo."""

    WIDTH, HEIGHT = 46.0, 46.0
    EXTRA_BOTTOM = 18.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(self._pen())
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(2, 2, 42, 42))
        p.setPen(QPen(INK, 1.5))
        for a in range(0, 360, 90):                      # marcas
            rad = math.radians(a)
            p.drawLine(QPointF(23 + 17 * math.cos(rad), 23 - 17 * math.sin(rad)),
                       QPointF(23 + 20 * math.cos(rad), 23 - 20 * math.sin(rad)))
        p.setPen(QPen(INK, 2))
        p.drawLine(QPointF(23, 23), QPointF(23, 9))      # minutero
        p.drawLine(QPointF(23, 23), QPointF(31, 23))     # horario
        self._label_below(p, self.body_rect(), self.node.text or self.node.name, gray=True)


class ReworkItem(NodeItem):
    """Reelaboración: dos flechas circulares."""

    WIDTH, HEIGHT = 56.0, 44.0
    EXTRA_BOTTOM = 18.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(SELECT if self.isSelected() else INK, 2.4))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(8, 4, 40, 36), 200 * 16, 150 * 16)   # arco superior
        p.drawArc(QRectF(8, 4, 40, 36), 20 * 16, 150 * 16)    # arco inferior
        p.setBrush(QBrush(INK))
        p.drawPolygon(_poly([(5, 24), (17, 21), (10, 12)]))   # punta izquierda
        p.drawPolygon(_poly([(51, 20), (39, 23), (46, 32)]))  # punta derecha
        txt = f"{self.node.value:g} %" if self.node.value else self.node.name
        self._label_below(p, self.body_rect(), txt, gray=True)


# ---------------------------------------------------------------- mejora
class KaizenItem(NodeItem):
    """Estallido Kaizen."""

    WIDTH, HEIGHT = 150.0, 96.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.WIDTH / 2, self.HEIGHT / 2
        pts = []
        n = 8 if _tabla() else 18
        for i in range(2 * n):
            rr = 1.0 if i % 2 == 0 else (0.62 if _tabla() else 0.72)
            a = math.pi * i / n
            pts.append((cx + cx * rr * math.cos(a), cy + cy * rr * math.sin(a)))
        p.setPen(self._pen(QColor("#b7950b")))
        p.setBrush(QColor("#ffff00") if _tabla() else QColor("#f9e11a"))
        p.drawPolygon(_poly(pts))
        p.setFont(_font(8, bold=True))
        p.setPen(INK)
        self._t(p, QRectF(cx - 46, cy - 26, 92, 52), Qt.AlignCenter | Qt.TextWordWrap, self.node.name)


class ObservationItem(NodeItem):
    """Observación: anteojos (ajuste de programas según el nivel de inventarios)."""

    WIDTH, HEIGHT = 66.0, 34.0
    EXTRA_BOTTOM = 32.0

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(SELECT if self.isSelected() else INK, 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(6, 8, 22, 22))
        p.drawEllipse(QRectF(38, 8, 22, 22))
        p.drawArc(QRectF(26, 10, 14, 10), 0, 180 * 16)        # puente
        p.drawLine(QPointF(6, 16), QPointF(0, 8))              # patillas
        p.drawLine(QPointF(60, 16), QPointF(66, 8))
        self._label_below(p, self.body_rect(), self.node.name, gray=False)
        if self.node.text:
            self._label_below(p, self.body_rect(), self.node.text, dy=17, gray=True)


_ITEM_CLASSES = {
    "process": ProcessItem, "shared_process": SharedProcessItem, "work_cell": WorkCellItem,
    "operator": OperatorItem, "data_box": DataBoxItem,
    "supplier": ExternalItem, "customer": ExternalItem,
    "inventory": InventoryItem, "supermarket": SupermarketItem, "safety_stock": SafetyStockItem,
    "fifo_lane": FifoLaneItem, "buffer_point": BufferPointItem, "safety_point": SafetyPointItem,
    "transport": TransportItem, "goods_arrow": GoodsArrowItem, "mp_pt_flow": MpPtFlowItem,
    "pull_physical": PullPhysicalItem,
    "control": ControlItem, "database": DatabaseItem, "info_box": InfoBoxItem,
    "kanban_production": KanbanProductionItem, "kanban_withdrawal": KanbanWithdrawalItem,
    "kanban_batch": KanbanBatchItem, "kanban_signal": KanbanSignalItem,
    "kanban_post": KanbanPostItem, "heijunka": HeijunkaItem, "pull_ball": PullBallItem,
    "time_segment": TimeSegmentItem, "total_time": TotalTimeItem, "clock": ClockItem,
    "rework": ReworkItem, "kaizen": KaizenItem, "observation": ObservationItem,
}


def create_item(node) -> NodeItem:
    return _ITEM_CLASSES[node.kind](node)


# =============================================================================
# Conexiones
# =============================================================================
def _edge_point(rect: QRectF, toward: QPointF) -> QPointF:
    """Punto donde un rayo desde el centro de `rect` hacia `toward` sale del rectángulo."""
    c = rect.center()
    dx, dy = toward.x() - c.x(), toward.y() - c.y()
    if dx == 0 and dy == 0:
        return c
    hw, hh = rect.width() / 2, rect.height() / 2
    sx = hw / abs(dx) if dx else math.inf
    sy = hh / abs(dy) if dy else math.inf
    s = min(sx, sy)
    return QPointF(c.x() + dx * s, c.y() + dy * s)


class ConnectionItem(QGraphicsPathItem):
    """Flecha entre dos nodos. El estilo depende del tipo de conexión."""

    def __init__(self, conn, src: NodeItem, dst: NodeItem):
        super().__init__()
        self.conn = conn
        self.src = src
        self.dst = dst
        self._pts = []
        self.icon_mode = False
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(0)
        src.connections.append(self)
        dst.connections.append(self)
        self.update_path()

    def detach(self):
        for it in (self.src, self.dst):
            if self in it.connections:
                it.connections.remove(self)

    def update_path(self):
        self.prepareGeometryChange()
        a = self.src.mapRectToScene(self.src.body_rect())
        b = self.dst.mapRectToScene(self.dst.body_rect())
        pa = _edge_point(a, b.center())
        pb = _edge_point(b, a.center())
        pts = [pa, pb]
        curve = None
        if self.conn.kind == "info_electronic" and _tabla():          # curva (tabla)
            dx, dy = pb.x() - pa.x(), pb.y() - pa.y()
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length                        # normal
            c1 = QPointF(pa.x() + dx * 0.50, pa.y() + dy * 0.50)
            c2 = QPointF(pb.x() - dx * 0.30 - nx * length * 0.20, pb.y() - dy * 0.30 - ny * length * 0.20)
            curve = (c1, c2)
            pts = [pa, c2, pb]
        elif self.conn.kind == "info_electronic":                     # rayo (libro)
            dx, dy = pb.x() - pa.x(), pb.y() - pa.y()
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length
            amp = min(9.0, length / 6)
            pts = [pa,
                   QPointF(pa.x() + dx * 0.40 + nx * amp, pa.y() + dy * 0.40 + ny * amp),
                   QPointF(pa.x() + dx * 0.60 - nx * amp, pa.y() + dy * 0.60 - ny * amp),
                   pb]
        self._pts = pts
        path = QPainterPath(pts[0])
        if curve:
            path.cubicTo(curve[0], curve[1], pts[-1])
        else:
            for q in pts[1:]:
                path.lineTo(q)
        self.setPath(path)

    def boundingRect(self) -> QRectF:
        return self.path().boundingRect().adjusted(-50, -34, 50, 26)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        return stroker.createStroke(self.path())

    # ------------------------------------------------------------- pintura
    def _arrow_head(self, p: QPainter, color: QColor, size: float):
        tip, prev = self._pts[-1], self._pts[-2]
        dx, dy = tip.x() - prev.x(), tip.y() - prev.y()
        length = math.hypot(dx, dy)
        if length <= 1:
            return
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        p.setPen(QPen(color, 1))
        p.setBrush(QBrush(color))
        p.drawPolygon(QPolygonF([tip,
                                 QPointF(tip.x() - ux * size + nx * size * 0.45, tip.y() - uy * size + ny * size * 0.45),
                                 QPointF(tip.x() - ux * size - nx * size * 0.45, tip.y() - uy * size - ny * size * 0.45)]))

    def _paint_fifo(self, p: QPainter, color: QColor):
        """Carril FIFO: dos líneas paralelas, flecha y la etiqueta FIFO en el centro."""
        a, b = self._pts[0], self._pts[-1]
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        off = 5.0
        p.setPen(QPen(color, 1.8))
        end = max(0.0, length - 10)
        for s in (-off, off):
            p.drawLine(QPointF(a.x() + nx * s, a.y() + ny * s),
                       QPointF(a.x() + ux * end + nx * s, a.y() + uy * end + ny * s))
        self._arrow_head(p, color, 11.0)
        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        if not self.icon_mode:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#fafafa"))
            p.drawRect(QRectF(mid.x() - 17, mid.y() - 6, 34, 12))
            p.setFont(_font(7, bold=True))
            p.setPen(color)
            p.drawText(QRectF(mid.x() - 17, mid.y() - 7, 34, 14), Qt.AlignCenter, "FIFO")

    def _paint_phone(self, p: QPainter, color: QColor):
        """Teléfono sobre la línea: información recogida por teléfono."""
        a, b = self._pts[0], self._pts[-1]
        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        p.setPen(QPen(color, 1.2))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(mid.x() - 10, mid.y() - 12, 20, 24), 4, 4)
        p.setPen(QPen(color, 3.2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(mid.x() - 6, mid.y() - 7, 12, 14), 100 * 16, 160 * 16)   # auricular

    def paint(self, p: QPainter, option, widget=None):
        if len(self._pts) < 2:
            return
        p.setRenderHint(QPainter.Antialiasing)
        kind = self.conn.kind
        color = SELECT if self.isSelected() else QColor("#1b1b1b")

        if kind == "fifo":
            self._paint_fifo(p, color)
        else:
            pen = QPen(color)
            head = 11.0
            if kind == "push":
                pen.setWidthF(5)
                pen.setDashPattern([1.0, 1.0])
                pen.setCapStyle(Qt.FlatCap)
                head = 16.0
            elif kind == "pull":
                pen.setWidthF(2)
                pen.setStyle(Qt.DashLine)
            elif kind == "info_manual":
                pen.setWidthF(1.6)
            elif kind == "info_phone":
                pen.setWidthF(1.6)
                pen.setStyle(Qt.DotLine)
            else:
                pen.setWidthF(1.8)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(self.path())
            self._arrow_head(p, color, head)
            if kind == "info_phone":
                self._paint_phone(p, color)

        if self.conn.note and not self.icon_mode:
            a, b = self._pts[0], self._pts[-1]
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            p.setFont(_font(8, italic=True))
            p.setPen(GRAY)
            p.drawText(QRectF(mid.x() - 50, mid.y() - 30, 100, 16), Qt.AlignCenter, self.conn.note)