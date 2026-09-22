"""Panel de métricas en vivo + escalera de tiempo (timeline) del VSM."""
from __future__ import annotations

from typing import List

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QPainterPath, QFontMetrics
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy, QTabWidget)

from .balance_chart import BalanceChart
from .engine import Metrics, TimelineEntry


class MetricCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("MetricCard { background: white; border: 1px solid #cfd8dc; border-radius: 6px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(0)
        self.title = QLabel(title)
        self.title.setStyleSheet("color:#607d8b; font-size:10px;")
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size:17px; font-weight:bold; color:#2c3e50;")
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set_value(self, text: str, alert: bool = False):
        self.value.setText(text)
        color = "#c0392b" if alert else "#2c3e50"
        self.value.setStyleSheet(f"font-size:17px; font-weight:bold; color:{color};")


class TimeLadder(QWidget):
    """Escalera de tiempo clásica: arriba los tiempos de espera (días), abajo los de proceso (s)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: List[TimelineEntry] = []
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_entries(self, entries: List[TimelineEntry]):
        self.entries = list(entries)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#ffffff"))
        if not self.entries:
            p.setPen(QColor("#90a4ae"))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Arrastra procesos e inventarios al canvas para ver la escalera de tiempo")
            return
        margin = 14
        n = len(self.entries)
        seg = (w - 2 * margin) / n
        y_top, y_bot = h * 0.36, h * 0.66

        path = QPainterPath(QPointF(margin, y_top))
        cur = y_top
        for i, e in enumerate(self.entries):
            x = margin + i * seg
            y = y_bot if e.kind == "process" else y_top
            if y != cur:
                path.lineTo(x, y)
                cur = y
            path.lineTo(x + seg, y)
        p.setPen(QPen(QColor("#c0392b"), 2))
        p.drawPath(path)

        small = QFont()
        small.setPointSize(8)
        p.setFont(small)
        fm = QFontMetrics(small)
        for i, e in enumerate(self.entries):
            x = margin + i * seg
            if e.kind == "process":
                p.setPen(QColor("#2c3e50"))
                p.drawText(QRectF(x, y_bot + 4, seg, 16), Qt.AlignCenter, f"{e.seconds:g} s")
                name = fm.elidedText(e.label, Qt.ElideRight, int(seg) - 2)
                p.setPen(QColor("#90a4ae"))
                p.drawText(QRectF(x, y_bot + 20, seg, 16), Qt.AlignCenter, name)
            else:
                p.setPen(QColor("#2c3e50"))
                p.drawText(QRectF(x, y_top - 22, seg, 16), Qt.AlignCenter, f"{e.days:.1f} d")


class MetricsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        cards = QHBoxLayout()
        self.takt = MetricCard("TAKT TIME")
        self.va = MetricCard("TIEMPO DE VALOR AGREGADO")
        self.lead = MetricCard("LEAD TIME TOTAL")
        self.pce = MetricCard("PCE (EFICIENCIA DEL CICLO)")
        self.bottleneck = MetricCard("CUELLO DE BOTELLA")
        for c in (self.takt, self.va, self.lead, self.pce, self.bottleneck):
            cards.addWidget(c)
        lay.addLayout(cards)
        self.ladder = TimeLadder()
        self.balance = BalanceChart()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.ladder, "Escalera de tiempo")
        self.tabs.addTab(self.balance, "Balance (Yamazumi)")
        lay.addWidget(self.tabs, 1)
        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setTextFormat(Qt.RichText)
        self.notes.setStyleSheet("color:#455a64;")
        lay.addWidget(self.notes)

    def update_metrics(self, m: Metrics) -> None:
        self.takt.set_value(f"{m.takt_time_s:.1f} s" if m.takt_time_s else "—")
        self.va.set_value(f"{m.va_time_s:g} s")
        self.lead.set_value(f"{m.lead_time_days:.2f} días")
        if m.lead_time_s > 0:
            pct = m.pce * 100
            self.pce.set_value(f"{pct:.3f} %" if pct < 1 else f"{pct:.1f} %")
        else:
            self.pce.set_value("—")
        self.bottleneck.set_value(m.bottleneck_name or "—", alert=bool(m.processes_over_takt))
        self.ladder.set_entries(m.timeline)
        self.balance.set_metrics(m)

        lines = []
        for w in m.warnings:
            lines.append(f"<span style='color:#b9770e'>⚠ {w}</span>")
        over = m.processes_over_takt
        if over:
            names = ", ".join(f"{r.name} ({r.effective_ct_s:.1f} s)" for r in over)
            lines.append(f"<span style='color:#c0392b'>Superan el takt ({m.takt_time_s:.1f} s): {names}</span>")
        elif m.process_results:
            lines.append("<span style='color:#1e8449'>Ningún proceso supera el takt.</span>")
        if m.lead_time_s > 0:
            lines.append(f"{m.wait_share * 100:.2f} % del lead time es espera (sin valor agregado).")
        self.notes.setText("<br>".join(lines))
