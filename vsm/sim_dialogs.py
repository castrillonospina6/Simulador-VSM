"""Diálogo de la simulación dinámica (SimPy): parámetros, indicadores, estados de cada proceso, colas y niveles."""
from __future__ import annotations

import html
from typing import Optional

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPolygonF
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel, QPushButton,
                             QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QComboBox, QSpinBox, QTextBrowser, QWidget, QSizePolicy, QApplication)

from .dialogs import _dspin
from .metrics_panel import MetricCard
from .models import VSMMap
from .simulation import (SimConfig, SimResult, SimulationError, simulate, insights, supermarket_checks,
                         sweep_supermarket)

C_BUSY, C_DOWN = QColor("#4a86c5"), QColor("#f0b14a")
C_BLOCK, C_STARVE = QColor("#c0392b"), QColor("#b0bec5")
C_IDLE = QColor("#81c784")
VERDICT = {"ok": ("Aguanta", "#1e8449"), "justo": ("Justo", "#b9770e"), "no": ("NO aguanta", "#c0392b")}
INK, MUTED, GRID = QColor("#2c3e50"), QColor("#607d8b"), QColor("#e3e8ec")


def _font(px: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(px)
    f.setBold(bold)
    return f


# =============================================================================
# Gráficos
# =============================================================================
class StateBars(QWidget):
    """Una barra apilada por proceso: trabajando / en falla / bloqueado / sin material (suma 100 %)."""
    ROW = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stations = []
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

    def set_stations(self, stations) -> None:
        self.stations = list(stations)
        self.setMinimumHeight(48 + self.ROW * max(1, len(self.stations)))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        if not self.stations:
            p.setPen(MUTED)
            p.drawText(self.rect(), Qt.AlignCenter, "Pulsa «Simular» para ver en qué gasta el tiempo cada proceso")
            return
        x = 10.0
        p.setFont(_font(11))
        for text, color in (("Trabajando", C_BUSY), ("En falla", C_DOWN), ("Bloqueado (salida llena)", C_BLOCK),
                            ("Sin material (inanición)", C_STARVE), ("Espera señal Kanban", C_IDLE)):
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRect(QRectF(x, 10, 11, 11))
            p.setPen(INK)
            w = p.fontMetrics().horizontalAdvance(text)
            p.drawText(QRectF(x + 16, 6, w + 8, 18), Qt.AlignVCenter | Qt.AlignLeft, text)
            x += 16 + w + 22
        label_w = min(190.0, self.width() * 0.32)
        left, right = 10 + label_w, self.width() - 16
        for i, s in enumerate(self.stations):
            y = 36 + i * self.ROW
            p.setPen(INK)
            p.setFont(_font(11))
            p.drawText(QRectF(10, y, label_w - 6, self.ROW - 6), Qt.AlignRight | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(s.name, Qt.ElideRight, int(label_w - 8)))
            cx = left
            for frac, color in ((s.busy, C_BUSY), (s.down, C_DOWN), (s.blocked, C_BLOCK), (s.starved, C_STARVE),
                                (s.idle, C_IDLE)):
                w = max(0.0, frac) * (right - left)
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawRect(QRectF(cx, y, w, self.ROW - 8))
                if frac >= 0.08:
                    p.setPen(QColor("#ffffff") if color in (C_BUSY, C_BLOCK) else INK)
                    p.setFont(_font(10, True))
                    p.drawText(QRectF(cx, y, w, self.ROW - 8), Qt.AlignCenter, f"{frac * 100:.0f} %")
                cx += w


class LevelChart(QWidget):
    """Nivel de un inventario en el tiempo (réplica 1), con su capacidad y la zona de calentamiento."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pts, self.cap, self.warm, self.title = [], 0.0, 0.0, ""
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_series(self, title: str, pts, cap: float, warm_days: float) -> None:
        self.title, self.pts, self.cap, self.warm = title, list(pts), cap, warm_days
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        if len(self.pts) < 2:
            p.setPen(MUTED)
            p.drawText(self.rect(), Qt.AlignCenter, "Sin datos: pulsa «Simular»")
            return
        l, r, t, b = 62.0, 16.0, 26.0, 30.0
        plot = QRectF(l, t, self.width() - l - r, self.height() - t - b)
        xmax = self.pts[-1][0] or 1.0
        ymax = max(self.cap, max(v for _, v in self.pts), 1.0) * 1.08
        X = lambda d: plot.left() + d / xmax * plot.width()
        Y = lambda v: plot.bottom() - v / ymax * plot.height()
        p.fillRect(QRectF(plot.left(), plot.top(), X(self.warm) - plot.left(), plot.height()), QColor("#f4f6f8"))
        p.setFont(_font(10))
        for i in range(5):
            v = ymax * i / 4
            p.setPen(QPen(GRID, 1))
            p.drawLine(QPointF(plot.left(), Y(v)), QPointF(plot.right(), Y(v)))
            p.setPen(MUTED)
            p.drawText(QRectF(0, Y(v) - 8, l - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{v:,.0f}")
        step = max(1, int(round(xmax / 10)))
        for d in range(0, int(xmax) + 1, step):
            p.setPen(MUTED)
            p.drawText(QRectF(X(d) - 20, plot.bottom() + 4, 40, 14), Qt.AlignCenter, f"{d}")
        p.drawText(QRectF(plot.left(), plot.bottom() + 16, plot.width(), 14), Qt.AlignCenter,
                   "días laborales (zona gris = calentamiento, no se mide)")
        if self.cap > 0:
            pen = QPen(C_BLOCK, 1.5, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(plot.left(), Y(self.cap)), QPointF(plot.right(), Y(self.cap)))
            p.drawText(QRectF(plot.right() - 150, Y(self.cap) - 16, 150, 14), Qt.AlignRight, "capacidad")
        p.setPen(QPen(C_BUSY, 2))
        p.drawPolyline(QPolygonF([QPointF(X(d), Y(v)) for d, v in self.pts]))
        p.setPen(INK)
        p.setFont(_font(11, True))
        p.drawText(QRectF(l, 4, plot.width(), 18), Qt.AlignLeft | Qt.AlignVCenter, f"{self.title} (unidades)")


# =============================================================================
# Diálogo
# =============================================================================
def _table(headers) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.NoSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    for j in range(1, len(headers)):
        t.horizontalHeader().setSectionResizeMode(j, QHeaderView.ResizeToContents)
    return t


def _fill(table: QTableWidget, rows, alerts=None) -> None:
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            it = QTableWidgetItem(v)
            it.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if j == 0 else Qt.AlignRight))
            if alerts and alerts[i]:
                it.setForeground(QColor("#c0392b"))
            table.setItem(i, j, it)


class SimulationDialog(QDialog):
    """Simula el mapa actual con variabilidad y muestra colas, bloqueos e inanición."""

    def __init__(self, vmap: VSMMap, parent=None):
        super().__init__(parent)
        self.map = vmap
        self.result: Optional[SimResult] = None
        self.setWindowTitle("Simulación dinámica de eventos discretos (SimPy)")
        self.animate = False                       # la ventana principal reproduce la animación al cerrar
        self.resize(1040, 860)

        d = SimConfig()
        self.days = _dspin(d.days, 1, 365, 0, " días")
        self.warm = _dspin(d.warmup_days, 0, 100, 0, " días")
        self.reps = QSpinBox()
        self.reps.setRange(1, 50)
        self.reps.setValue(d.replications)
        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.seed.setValue(d.seed)
        self.ct_cv = _dspin(d.ct_cv * 100, 0, 300, 0, " %")
        self.dem_cv = _dspin(d.demand_cv * 100, 0, 300, 0, " %")
        self.mttr = _dspin(d.mttr_min, 0, 1440, 1, " min")
        self.capf = _dspin(d.cap_factor, 0.5, 20, 1, " ×")
        self.release = QComboBox()
        self.release.addItem("Al ritmo de la demanda", "demand")
        self.release.addItem("Empuje: sin límite hasta llenar", "unlimited")

        left, right = QFormLayout(), QFormLayout()
        left.addRow("Días medidos", self.days)
        left.addRow("Calentamiento (se descarta)", self.warm)
        left.addRow("Réplicas", self.reps)
        left.addRow("Semilla", self.seed)
        right.addRow("Variabilidad del tiempo de ciclo (CV)", self.ct_cv)
        right.addRow("Variabilidad de los pedidos (CV)", self.dem_cv)
        right.addRow("Reparación media por defecto (MTTR)", self.mttr)
        right.addRow("Capacidad de cada inventario", self.capf)
        right.addRow("Suministro del proveedor", self.release)
        box = QGroupBox("Parámetros (la disponibilidad de cada proceso sale del mapa)")
        row = QHBoxLayout(box)
        row.addLayout(left)
        row.addLayout(right)

        self.btn = QPushButton("Simular")
        self.btn.setStyleSheet("padding:8px; font-weight:bold;")
        self.btn.clicked.connect(self.run)
        self.btn_anim = QPushButton("Animar en el mapa")
        self.btn_anim.setEnabled(False)
        self.btn_anim.clicked.connect(self._animate)
        self.status = QLabel("CV = 0 % → sin variabilidad. Con 1 réplica no hay intervalo de confianza.")
        self.status.setStyleSheet("color:#607d8b;")
        self.status.setWordWrap(True)

        self.k_thr = MetricCard("ENTREGADO / PEDIDO (u/día)")
        self.k_fill = MetricCard("NIVEL DE SERVICIO")
        self.k_lead = MetricCard("LEAD TIME DINÁMICO")
        self.k_pce = MetricCard("PCE DINÁMICO")
        self.k_wip = MetricCard("INVENTARIO PROMEDIO (u)")
        cards = QHBoxLayout()
        for c in (self.k_thr, self.k_fill, self.k_lead, self.k_pce, self.k_wip):
            cards.addWidget(c)

        self.bars = StateBars()
        self.t_buf = _table(["Inventario / tránsito", "Promedio", "Mín", "Máx", "Capacidad", "Lleno %", "Vacío %",
                             "Espera (d)", "Estático (d)"])
        self.chart = LevelChart()
        self.pick = QComboBox()
        self.pick.currentIndexChanged.connect(self._show_level)
        lv = QWidget()
        lay_lv = QVBoxLayout(lv)
        lay_lv.addWidget(self.pick)
        lay_lv.addWidget(self.chart, 1)
        self.notes = QTextBrowser()
        self.t_sm = _table(["Supermercado", "Veredicto", "Máx (u)", "Mín obs.", "Vacío %", "Bajo mín. %",
                            "Réplicas con quiebre", "Consume"])
        self.sm_note = QTextBrowser()
        self.sm_note.setMaximumHeight(110)
        self.sm_pick = QComboBox()
        self.btn_sweep = QPushButton("Probar otros tamaños")
        self.btn_sweep.clicked.connect(self._sweep)
        self.t_sweep = _table(["Nivel máximo (u)", "Vacío % del tiempo", "Réplicas con quiebre",
                               "Nivel de servicio", "Inventario prom. (u)", "Veredicto"])
        sw = QHBoxLayout()
        sw.addWidget(QLabel("Si el máximo fuera distinto:"))
        sw.addWidget(self.sm_pick, 1)
        sw.addWidget(self.btn_sweep)
        smw = QWidget()
        lay_sm = QVBoxLayout(smw)
        lay_sm.addWidget(self.t_sm)
        lay_sm.addWidget(self.sm_note)
        lay_sm.addLayout(sw)
        lay_sm.addWidget(self.t_sweep)
        tabs = QTabWidget()
        tabs.addTab(self.bars, "Estados de los procesos")
        tabs.addTab(self.t_buf, "Colas e inventarios")
        tabs.addTab(lv, "Niveles en el tiempo")
        tabs.addTab(smw, "¿Aguanta el supermercado?")
        tabs.addTab(self.notes, "Hallazgos")
        self.tabs = tabs

        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        foot = QHBoxLayout()
        foot.addWidget(self.btn)
        foot.addWidget(self.btn_anim)
        foot.addWidget(self.status, 1)
        foot.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(box)
        lay.addLayout(cards)
        lay.addWidget(tabs, 1)
        lay.addLayout(foot)

    # ------------------------------------------------------------- ejecutar
    def config(self) -> SimConfig:
        return SimConfig(days=self.days.value(), warmup_days=self.warm.value(), replications=self.reps.value(),
                         seed=self.seed.value(), ct_cv=self.ct_cv.value() / 100, demand_cv=self.dem_cv.value() / 100,
                         mttr_min=self.mttr.value(), cap_factor=self.capf.value(),
                         release=self.release.currentData())

    def _progress(self, i: int, n: int) -> None:
        self.status.setText(f"Simulando… réplica {min(i + 1, n)} de {n}")
        QApplication.processEvents()

    def run(self) -> None:
        self.btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = simulate(self.map, self.config(), self._progress)
        except SimulationError as exc:
            QApplication.restoreOverrideCursor()
            self.btn.setEnabled(True)
            self.status.setText(f"<span style='color:#c0392b'>{html.escape(str(exc))}</span>")
            return
        QApplication.restoreOverrideCursor()
        self.btn.setEnabled(True)
        self.show_result(res)

    # ------------------------------------------------------------ resultados
    def show_result(self, res: SimResult) -> None:
        self.result = res
        self.btn_anim.setEnabled(bool(res.frames))
        k, ci = res.kpi, res.ci

        def pm(key: str, fmt: str) -> str:
            return f"{fmt.format(getattr(k, key))}" + (f" ± {fmt.format(ci[key])}" if ci[key] > 0 else "")

        self.k_thr.set_value(f"{k.throughput_day:,.0f} / {k.demand_day:,.0f}", alert=k.fill_rate < 0.95)
        self.k_fill.set_value(pm("fill_rate", "{:.1%}"), alert=k.fill_rate < 0.95)
        self.k_lead.set_value(f"{pm('lead_time_days', '{:.1f}')} d (est. {res.static_lead_time_days:.1f})")
        self.k_pce.set_value(f"{k.pce * 100:.3f} % (est. {res.static_pce * 100:.3f})")
        self.k_wip.set_value(f"{k.wip_units:,.0f}")
        self.bars.set_stations(res.stations)

        rows, alerts = [], []
        for b in res.buffers:
            tr = b.kind == "transport"
            rows.append([b.name, f"{b.avg_u:,.0f}", f"{b.min_u:,.0f}", f"{b.max_u:,.0f}",
                         "—" if tr else f"{b.capacity_u:,.0f}", "—" if tr else f"{b.full_pct * 100:.0f} %",
                         "—" if tr else f"{b.empty_pct * 100:.0f} %", f"{b.wait_days:.2f}",
                         f"{b.static_days:.2f}" if b.kind in ("inventory", "transport") else "—"])
            alerts.append(not tr and b.kind != "edge" and (b.full_pct >= 0.3 or b.empty_pct >= 0.3))
        _fill(self.t_buf, rows, alerts)

        self.pick.blockSignals(True)
        self.pick.clear()
        best, spread = 0, -1.0
        for i, name in enumerate(res.series):
            self.pick.addItem(name)
            v = [y for _, y in res.series[name]] or [0.0]
            if max(v) - min(v) > spread:
                best, spread = i, max(v) - min(v)
        self.pick.setCurrentIndex(best)
        self.pick.blockSignals(False)
        self._show_level()

        self._show_supermarkets(res)
        items = "".join(f"<li>{html.escape(t)}</li>" for t in insights(res))
        self.notes.setHtml(f"<h3>Qué muestra la simulación que el VSM estático no ve</h3><ul>{items}</ul>"
                           f"<p style='color:#607d8b'>Se simularon {res.replications} réplica(s) de "
                           f"{res.config.days:g} días (más {res.config.warmup_days:g} de calentamiento), moviendo "
                           f"lotes de {res.batch} unidad(es). El lead time se calcula con la ley de Little; las "
                           f"ventas sin producto terminado se pierden. No se modelan cambios de referencia (C/O), "
                           f"operarios ni turnos individuales.</p>")
        self.status.setText(f"Listo: {res.replications} réplica(s), lotes de {res.batch} u.")

    def _show_level(self, *_):
        if self.result is None or not self.pick.count():
            return
        name = self.pick.currentText()
        self.chart.set_series(name, self.result.series.get(name, []), self.result.series_cap.get(name, 0.0),
                              self.result.warmup_days)

    # --------------------------------------------------------- supermercados
    def _show_supermarkets(self, res: SimResult) -> None:
        checks = supermarket_checks(res)
        rows, alerts = [], []
        for c in checks:
            rows.append([c.name, VERDICT[c.verdict][0], f"{c.max_u:,.0f}", f"{c.min_obs_u:,.0f}",
                         f"{c.empty_pct * 100:.1f} %", f"{c.below_min_pct * 100:.0f} %" if c.min_cfg_u else "—",
                         f"{c.empty_reps * 100:.0f} %", c.consumer])
            alerts.append(c.verdict != "ok")
        _fill(self.t_sm, rows, alerts)
        for i, c in enumerate(checks):
            it = self.t_sm.item(i, 1)
            it.setForeground(QColor(VERDICT[c.verdict][1]))
            f = it.font()
            f.setBold(True)
            it.setFont(f)
        self.sm_pick.clear()
        for c in checks:
            self.sm_pick.addItem(c.name, c.node_id)
        self.btn_sweep.setEnabled(bool(checks))
        self.t_sweep.setRowCount(0)
        if checks:
            self.sm_note.setHtml("".join(
                f"<p><b style='color:{VERDICT[c.verdict][1]}'>{html.escape(c.name)} · {VERDICT[c.verdict][0]}</b>"
                f"<br>{html.escape(c.advice)}</p>" for c in checks))
        else:
            self.sm_note.setHtml("<p>El mapa no tiene supermercados. Colócalos con la calculadora de "
                                 "<i>Estado futuro → Calculadora de Kanban y supermercado</i> (fija el nivel "
                                 "máximo y mínimo) o arrastra uno desde la paleta y edita su nivel máximo.</p>")

    def _sweep(self) -> None:
        nid = self.sm_pick.currentData()
        if not nid:
            return
        self.btn_sweep.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            pts = sweep_supermarket(self.map, nid, self.config(),
                                    progress=lambda i, n: (self.status.setText(f"Probando tamaños… {i + 1}/{n}"),
                                                           QApplication.processEvents()))
        except SimulationError as exc:
            self.status.setText(f"<span style='color:#c0392b'>{html.escape(str(exc))}</span>")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.btn_sweep.setEnabled(True)
        _fill(self.t_sweep, [[f"{p.max_u:,.0f}", f"{p.empty_pct * 100:.1f} %", f"{p.empty_reps * 100:.0f} %",
                              f"{p.fill_rate * 100:.1f} %", f"{p.wip_units:,.0f}", VERDICT[p.verdict][0]]
                             for p in pts], [p.verdict != "ok" for p in pts])
        ok = next((p for p in pts if p.verdict == "ok"), None)
        self.status.setText(f"El menor nivel probado que aguanta: {ok.max_u:,.0f} u." if ok else
                            "Ningún nivel probado aguanta: ataca las fallas, la variabilidad o el tiempo de reposición.")

    def _animate(self) -> None:
        self.animate = True
        self.accept()
