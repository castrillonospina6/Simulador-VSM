"""Gráfico de balance (Yamazumi): tiempo de ciclo efectivo de cada proceso frente al Takt Time.

Cada barra apila el tiempo de ciclo (TC) y la pérdida por disponibilidad (TC/disp. − TC), de modo
que la altura total es el tiempo de ciclo efectivo, la misma cifra que usa el motor para decidir si un
proceso supera el takt. La línea punteada es el Takt Time: las barras que la cruzan (en rojo) son el
cuello de botella; las muy por debajo tienen holgura (desbalance).

`paint_balance` dibuja sobre cualquier QPainter (widget, imagen, PDF), así que el mismo código sirve
para la pantalla y para las exportaciones.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QFontMetricsF, QImage
from PyQt5.QtWidgets import QWidget, QSizePolicy

from .engine import Metrics

C_CT = QColor("#4a86c5")
C_OVER = QColor("#c0392b")
C_LOSS = QColor("#f0b14a")
C_TAKT = QColor("#1e8449")
INK = QColor("#2c3e50")
GRID = QColor("#e3e8ec")
MUTED = QColor("#607d8b")


# ------------------------------------------------------------------ datos
@dataclass
class BalanceBar:
    name: str
    ct_s: float          # tiempo de ciclo
    eff_s: float         # tiempo de ciclo efectivo = TC / disponibilidad
    over: bool           # supera el takt

    @property
    def loss_s(self) -> float:
        return max(0.0, self.eff_s - self.ct_s)


@dataclass
class BalanceData:
    takt_s: float = 0.0
    bars: List[BalanceBar] = field(default_factory=list)

    @property
    def max_eff(self) -> float:
        return max((b.eff_s for b in self.bars), default=0.0)

    @property
    def balance_efficiency(self) -> float:
        """Eficiencia de balance de línea = Σ tiempos efectivos / (N × tiempo del proceso más lento)."""
        mx = self.max_eff
        if not self.bars or mx <= 0:
            return 0.0
        return sum(b.eff_s for b in self.bars) / (len(self.bars) * mx)


def balance_data(m: Metrics) -> BalanceData:
    bars = [BalanceBar(r.name, r.cycle_time_s, r.effective_ct_s, r.exceeds_takt) for r in m.process_results]
    return BalanceData(m.takt_time_s, bars)


# ------------------------------------------------------------------ dibujo
def _axis(vmax: float):
    """Paso y tope 'bonitos' para el eje Y."""
    raw = max(vmax, 1e-9) / 4
    exp = 10 ** math.floor(math.log10(raw))
    step = 10 * exp
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * exp:
            step = mult * exp
            break
    return step, math.ceil(vmax / step - 1e-9) * step


def paint_balance(p: QPainter, rect: QRectF, data: BalanceData, k: float = 1.0) -> None:
    """Dibuja el Yamazumi dentro de `rect`. `k` escala tipografía y márgenes (1.0 = pantalla)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)

    def font(px: float, bold: bool = False) -> QFont:
        f = QFont()
        f.setPixelSize(max(1, int(round(px * k))))
        f.setBold(bold)
        return f

    if not data.bars:
        p.setPen(QColor("#90a4ae"))
        p.setFont(font(12))
        p.drawText(rect, Qt.AlignCenter, "Agrega procesos al canvas para ver el balance (Yamazumi)")
        p.restore()
        return

    left, right, top, bottom = 46 * k, 14 * k, 30 * k, 40 * k
    plot = QRectF(rect.left() + left, rect.top() + top, rect.width() - left - right,
                  rect.height() - top - bottom)
    if plot.width() < 20 or plot.height() < 20:
        p.restore()
        return

    step, ytop = _axis(max(data.max_eff, data.takt_s, 1.0) * 1.12)   # el 1.0 evita ejes de altura 0

    def y_of(v: float) -> float:
        return plot.bottom() - v / ytop * plot.height()

    # cuadrícula y eje Y
    p.setFont(font(9))
    for i in range(int(round(ytop / step)) + 1):
        v = i * step
        y = y_of(v)
        p.setPen(QPen(GRID, max(1.0, k)))
        p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        p.setPen(MUTED)
        p.drawText(QRectF(rect.left(), y - 8 * k, left - 6 * k, 16 * k), Qt.AlignRight | Qt.AlignVCenter, f"{v:g}")
    p.setPen(MUTED)
    p.drawText(QRectF(rect.left(), plot.top() - 20 * k, left - 6 * k, 14 * k), Qt.AlignRight | Qt.AlignVCenter, "s")

    # barras
    n = len(data.bars)
    slot = plot.width() / n
    bw = min(slot * 0.62, 90 * k)
    for i, b in enumerate(data.bars):
        cx = plot.left() + slot * (i + 0.5)
        x = cx - bw / 2
        y_ct, y_eff = y_of(b.ct_s), y_of(b.eff_s)
        p.setPen(Qt.NoPen)
        p.setBrush(C_OVER if b.over else C_CT)
        p.drawRect(QRectF(x, y_ct, bw, plot.bottom() - y_ct))
        if b.loss_s > 0:
            p.setBrush(C_LOSS)
            p.drawRect(QRectF(x, y_eff, bw, y_ct - y_eff))
        if b.over:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(C_OVER, max(1.5, 2 * k)))
            p.drawRect(QRectF(x, y_eff, bw, plot.bottom() - y_eff))
        p.setPen(INK)
        p.setFont(font(9))
        p.drawText(QRectF(cx - slot / 2 + 2 * k, plot.bottom() + 4 * k, slot - 4 * k, bottom - 6 * k),
                   Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, b.name)

    # línea del takt
    if data.takt_s > 0:
        y = y_of(data.takt_s)
        pen = QPen(C_TAKT, max(1.5, 2 * k))
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        lab = QRectF(plot.right() - 120 * k, y - 16 * k, 120 * k, 14 * k)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 210))
        p.drawRect(lab)
        p.setPen(C_TAKT)
        p.setFont(font(9, True))
        p.drawText(lab, Qt.AlignRight | Qt.AlignVCenter, f"Takt = {data.takt_s:.1f} s")

    # valor de cada barra (después de la línea del takt y con fondo blanco, para que la línea no los tache)
    p.setFont(font(10, True))
    fm_v = QFontMetricsF(p.font())
    for i, b in enumerate(data.bars):
        cx = plot.left() + slot * (i + 0.5)
        txt = f"{b.eff_s:.1f} s"
        tw = fm_v.horizontalAdvance(txt) + 6 * k
        lab = QRectF(cx - tw / 2, y_of(b.eff_s) - 17 * k, tw, 15 * k)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRect(lab)
        p.setPen(C_OVER if b.over else INK)
        p.drawText(lab, Qt.AlignCenter, txt)

    # leyenda + eficiencia de balance
    p.setFont(font(9))
    fm = QFontMetricsF(p.font())
    x = plot.left()
    ly = rect.top() + 8 * k
    for text, color in (("Tiempo de ciclo", C_CT), ("Pérdida por disponibilidad", C_LOSS),
                        ("Supera el takt", C_OVER)):
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRect(QRectF(x, ly + 2 * k, 10 * k, 10 * k))
        p.setPen(INK)
        w = fm.horizontalAdvance(text)
        p.drawText(QRectF(x + 14 * k, ly, w + 6 * k, 14 * k), Qt.AlignLeft | Qt.AlignVCenter, text)
        x += 14 * k + w + 18 * k
    eff = data.balance_efficiency * 100
    p.setFont(font(9, True))
    p.setPen(C_TAKT if eff >= 85 else (QColor("#b9770e") if eff >= 65 else C_OVER))
    p.drawText(QRectF(plot.right() - 220 * k, ly, 220 * k, 14 * k), Qt.AlignRight | Qt.AlignVCenter,
               f"Eficiencia de balance: {eff:.0f} %")
    p.restore()


def render_balance_image(data: BalanceData, width: int = 1600, height: int = 760) -> QImage:
    img = QImage(width, height, QImage.Format_RGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    paint_balance(p, QRectF(0, 0, width, height), data, k=width / 800.0)
    p.end()
    return img


class BalanceChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = BalanceData()
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_metrics(self, m: Metrics) -> None:
        self.data = balance_data(m)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))
        paint_balance(p, QRectF(self.rect()), self.data, 1.0)
