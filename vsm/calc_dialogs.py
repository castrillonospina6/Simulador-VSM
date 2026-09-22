"""Diálogos del estado futuro: calculadora de Kanban / supermercado y vista económica."""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QGroupBox, QLabel, QTabWidget, QWidget,
                             QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
                             QMessageBox, QApplication, QDoubleSpinBox, QCheckBox, QAbstractItemView)

from .dialogs import _dspin
from .economics import analyze, scale_inventories, compare, summary_text, money
from .metrics_panel import MetricCard
from .models import VSMMap
from .persistence import load_map, EXTENSION
from .pull_calc import kanban_cards, supermarket_size, hours_to_days

GRAY = "color:#607d8b;"
RED = "color:#c0392b;"


def _note(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(GRAY)
    return lab


def _out() -> QLabel:
    lab = QLabel()
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.RichText)
    return lab


def _money_spin(value: float) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(0, 1e12)
    sb.setDecimals(2)
    sb.setPrefix("$ ")
    sb.setGroupSeparatorShown(True)
    sb.setValue(value)
    return sb


def _rows(pairs) -> str:
    body = "".join(f"<tr><td>{a}</td><td style='padding-left:14px'>{b}</td></tr>" for a, b in pairs)
    return f"<table cellpadding='2'>{body}</table>"


# =============================================================================
# Calculadora de Kanban y tamaño de supermercado
# =============================================================================
class PullCalcDialog(QDialog):
    """Calcula el número de Kanban y el tamaño del supermercado, y los puede colocar en el mapa."""

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        params = canvas.map.params
        self.day_s = params.available_seconds_per_day
        self._kanban = self._market = None
        self._placed = 0
        self.setWindowTitle("Calculadora de Kanban y supermercado")
        self.resize(760, 780)

        common = QGroupBox("Datos del lazo de reposición")
        self.demand = _dspin(params.customer_demand, 0, 1e9, 0, " u/día")
        self.container = _dspin(50, 0, 1e9, 0, " u")
        self.lead = _dspin(8, 0, 1e6, 2)
        self.lead_unit = QComboBox()
        self.lead_unit.addItem("horas", "h")
        self.lead_unit.addItem("días laborales", "d")
        lead_row = QHBoxLayout()
        lead_row.addWidget(self.lead, 1)
        lead_row.addWidget(self.lead_unit)
        grid = QGridLayout(common)
        for col, (text, w) in enumerate((("Demanda del cliente (D)", self.demand),
                                         ("Unidades por contenedor (C)", self.container))):
            grid.addWidget(QLabel(text), 0, col)
            grid.addWidget(w, 1, col)
        grid.addWidget(QLabel("Tiempo de reposición (L)"), 0, 2)
        grid.addLayout(lead_row, 1, 2)
        grid.addWidget(_note("L = desde que se libera la tarjeta (o se pide) hasta que el material vuelve al "
                             "supermercado: espera + producción + transporte."), 2, 0, 1, 3)

        # ---- pestaña Kanban
        self.safety_pct = _dspin(10, 0, 1000, 1, " %")
        k_form = QFormLayout()
        k_form.addRow("Factor de seguridad (α)", self.safety_pct)
        self.k_out = _out()
        self.k_btn = QPushButton("Colocar Kanban en el mapa")
        self.k_btn.clicked.connect(self._place_kanban)
        k_tab = QWidget()
        k_lay = QVBoxLayout(k_tab)
        k_lay.addLayout(k_form)
        k_lay.addWidget(_note("N = ⌈ D × L × (1 + α) / C ⌉"))
        k_lay.addWidget(self.k_out)
        k_lay.addWidget(self.k_btn)
        k_lay.addStretch(1)

        # ---- pestaña supermercado
        self.interval = _dspin(1, 0, 1e4, 2, " días")
        self.buffer_d = _dspin(0.5, 0, 1e4, 2, " días")
        self.safety_d = _dspin(0.25, 0, 1e4, 2, " días")
        s_form = QFormLayout()
        s_form.addRow("Intervalo de reposición (R)", self.interval)
        s_form.addRow("Buffer: variación de la demanda", self.buffer_d)
        s_form.addRow("Seguridad: paradas y calidad", self.safety_d)
        self.s_out = _out()
        self.s_btn = QPushButton("Colocar supermercado en el mapa (cantidad = nivel promedio)")
        self.s_btn.clicked.connect(self._place_market)
        s_tab = QWidget()
        s_lay = QVBoxLayout(s_tab)
        s_lay.addLayout(s_form)
        s_lay.addWidget(_note("Máximo = ciclo (D × R) + buffer + seguridad · Mínimo = buffer + seguridad · "
                              "Reposición = D × L + mínimo"))
        s_lay.addWidget(self.s_out)
        s_lay.addWidget(self.s_btn)
        s_lay.addStretch(1)

        tabs = QTabWidget()
        tabs.addTab(k_tab, "Número de Kanban")
        tabs.addTab(s_tab, "Tamaño del supermercado")
        self.msg = QLabel()
        self.msg.setStyleSheet("color:#1e8449;")
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(common)
        lay.addWidget(tabs, 1)
        lay.addWidget(self.msg)
        lay.addWidget(close)

        for w in (self.demand, self.container, self.lead, self.safety_pct, self.interval, self.buffer_d,
                  self.safety_d):
            w.valueChanged.connect(self._recalc)
        self.lead_unit.currentIndexChanged.connect(self._recalc)
        self._recalc()

    # ------------------------------------------------------------- cálculo
    def _lead_days(self) -> float:
        v = self.lead.value()
        return hours_to_days(v, self.day_s) if self.lead_unit.currentData() == "h" else v

    def _recalc(self, *_):
        d, c = self.demand.value(), self.container.value()
        self._kanban = self._market = None
        self.msg.clear()
        try:
            lead = self._lead_days()
            self._kanban = kanban_cards(d, lead, c, self.safety_pct.value(), self.day_s)
            k = self._kanban
            self.k_out.setText(_rows([
                ("Número de Kanban (tarjetas)", f"<b>{k.cards}</b>"),
                ("Unidades máximas en el lazo", f"{k.units_in_loop:,.0f} u ({k.days_cover:.2f} días de demanda)"),
                ("Demanda durante la reposición", f"{k.demand_during_lead:,.0f} u"),
                ("Colchón resultante (seguridad + redondeo)", f"{k.safety_units:,.0f} u"),
                ("Contenedores consumidos por día", f"{k.withdrawals_per_day:,.1f}"),
                ("Pitch: se consume un contenedor cada", f"{k.pitch_s / 60:.1f} min" if k.pitch_s else "—")]))
        except ValueError as exc:
            self.k_out.setText(f"<span style='{RED}'>{exc}</span>")
        try:
            lead = self._lead_days()
            self._market = supermarket_size(d, c, self.interval.value(), lead, self.buffer_d.value(),
                                            self.safety_d.value())
            s = self._market
            html = _rows([
                ("Stock de ciclo", f"{s.cycle:,.0f} u"), ("Buffer", f"{s.buffer:,.0f} u"),
                ("Stock de seguridad", f"{s.safety:,.0f} u"),
                ("Nivel máximo", f"<b>{s.max_level:,.0f} u</b> ({s.days_max:.2f} días)"),
                ("Nivel mínimo", f"{s.min_level:,.0f} u"),
                ("Nivel promedio", f"{s.avg_level:,.0f} u ({s.days_avg:.2f} días)"),
                ("Punto de reposición", f"{s.reorder_point:,.0f} u"),
                ("Ubicaciones (contenedores) para el máximo", f"{s.locations}")])
            html += "".join(f"<p style='{RED}'>⚠ {w}</p>" for w in s.warnings)
            self.s_out.setText(html)
        except ValueError as exc:
            self.s_out.setText(f"<span style='{RED}'>{exc}</span>")
        self.k_btn.setEnabled(self._kanban is not None)
        self.s_btn.setEnabled(self._market is not None)

    # ------------------------------------------------------- colocar en el mapa
    def _place(self, kind: str, preset: dict, text: str) -> None:
        c = self.canvas
        pos = c.mapToScene(c.viewport().rect().center()) + QPointF(30, 30) * self._placed
        self._placed += 1
        c.push_undo()                                   # se puede deshacer con Ctrl+Z
        c.add_node_at(kind, pos, preset)
        self.msg.setText(f"✓ {text} (Ctrl+Z para deshacer)")

    def _place_kanban(self):
        if self._kanban:
            self._place("kanban_production", {"value": float(self.container.value()),
                                              "name": f"{self._kanban.cards} tarjetas"},
                        f"Kanban colocado: {self._kanban.cards} tarjetas de {self.container.value():g} u")

    def _place_market(self):
        if self._market:
            self._place("supermarket", {"quantity": float(round(self._market.avg_level)), "name": "Supermercado",
                                       "max_level": float(round(self._market.max_level)),
                                       "min_level": float(round(self._market.min_level))},
                        f"Supermercado colocado: promedio {self._market.avg_level:,.0f} u, máx "
                        f"{self._market.max_level:,.0f}, mín {self._market.min_level:,.0f}. "
                        f"Pulsa F5 para simular si aguanta")


# =============================================================================
# Vista económica
# =============================================================================
class EconomicDialog(QDialog):
    """Capital de trabajo y costo de mantener del mapa, y justificación económica de una mejora."""

    HEADERS = ["Elemento", "Tipo", "Unidades", "Días", "Valor/unidad", "Capital", "% del total"]

    def __init__(self, vmap: VSMMap, parent=None):
        super().__init__(parent)
        self.map = vmap
        self.econ = vmap.econ
        self._future: Optional[VSMMap] = None
        self._summary = ""
        self.setWindowTitle("Vista económica: capital de trabajo y costo de mantener")
        self.resize(980, 900)
        e = self.econ

        # ---- supuestos
        self.material = _money_spin(e.material_cost)
        self.conversion = _money_spin(e.conversion_cost)
        self.transit = QCheckBox("La mercancía en tránsito es de la empresa")
        self.transit.setChecked(e.include_transit)
        self.cap_rate = _dspin(e.capital_rate, 0, 100, 1, " %")
        self.sto_rate = _dspin(e.storage_rate, 0, 100, 1, " %")
        self.obs_rate = _dspin(e.obsolescence_rate, 0, 100, 1, " %")
        self.days_year = _dspin(e.work_days_per_year, 1, 366, 0, " días")
        left, right = QFormLayout(), QFormLayout()
        left.addRow("Materia prima por unidad", self.material)
        left.addRow("Conversión por unidad", self.conversion)
        left.addRow("", self.transit)
        right.addRow("Costo de capital (anual)", self.cap_rate)
        right.addRow("Almacenaje y manejo (anual)", self.sto_rate)
        right.addRow("Obsolescencia y merma (anual)", self.obs_rate)
        right.addRow("Días laborales por año", self.days_year)
        assume = QGroupBox("Supuestos (se guardan con el mapa; los valores iniciales son de ejemplo)")
        row = QHBoxLayout(assume)
        row.addLayout(left)
        row.addLayout(right)

        # ---- indicadores y tabla
        self.k_capital = MetricCard("CAPITAL INMOVILIZADO")
        self.k_holding = MetricCard("COSTO DE MANTENERLO (AÑO)")
        self.k_unit = MetricCard("COSTO DE MANTENER / UNIDAD")
        self.k_lead = MetricCard("LEAD TIME")
        self.k_turns = MetricCard("ROTACIÓN (VECES/AÑO)")
        cards = QHBoxLayout()
        for c in (self.k_capital, self.k_holding, self.k_unit, self.k_lead, self.k_turns):
            cards.addWidget(c)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setMinimumHeight(230)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for j in range(1, len(self.HEADERS)):
            self.table.horizontalHeader().setSectionResizeMode(j, QHeaderView.ResizeToContents)
        self.breakdown = _note("")

        # ---- justificar una mejora
        self.reduction = _dspin(0, 0, 100, 0, " %")
        self.invest = _money_spin(0)
        self.btn_future = QPushButton("Comparar con un mapa de estado futuro…")
        self.btn_clear = QPushButton("Quitar comparación")
        self.btn_clear.hide()
        self.lbl_future = _note("")
        sc = QGroupBox("Justificar una mejora")
        sc_form = QFormLayout()
        sc_form.addRow("Reducir todos los inventarios en", self.reduction)
        sc_form.addRow("Inversión necesaria", self.invest)
        btns = QHBoxLayout()
        btns.addWidget(self.btn_future)
        btns.addWidget(self.btn_clear)
        btns.addStretch(1)
        self.result = _out()
        self.result.setMinimumHeight(120)
        self.result.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        sc_lay = QVBoxLayout(sc)
        sc_lay.addLayout(sc_form)
        sc_lay.addLayout(btns)
        sc_lay.addWidget(self.lbl_future)
        sc_lay.addWidget(self.result)

        copy_btn = QPushButton("Copiar resumen")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self._summary))
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(copy_btn)
        foot.addWidget(close)

        lay = QVBoxLayout(self)
        lay.addWidget(assume)
        lay.addLayout(cards)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.breakdown)
        lay.addWidget(sc)
        lay.addLayout(foot)

        for w in (self.material, self.conversion, self.cap_rate, self.sto_rate, self.obs_rate, self.days_year,
                  self.reduction, self.invest):
            w.valueChanged.connect(self._refresh)
        self.transit.toggled.connect(self._refresh)
        self.btn_future.clicked.connect(self._load_future)
        self.btn_clear.clicked.connect(self._clear_future)
        self._refresh()

    # ------------------------------------------------------------- comparación
    def _load_future(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir mapa de estado futuro", "",
                                              f"Mapa VSM (*{EXTENSION} *.json)")
        if not path:
            return
        try:
            self._future = load_map(path)
        except Exception as exc:
            QMessageBox.warning(self, "No se pudo abrir", f"El archivo no es un mapa VSM válido:\n{exc}")
            return
        self.lbl_future.setText(f"Comparando con: {path}")
        self.reduction.setEnabled(False)
        self.btn_clear.show()
        self._refresh()

    def _clear_future(self):
        self._future = None
        self.lbl_future.clear()
        self.reduction.setEnabled(True)
        self.btn_clear.hide()
        self._refresh()

    # ------------------------------------------------------------- refresco
    def _refresh(self, *_):
        e = self.econ                                   # es el mismo objeto que guarda el mapa
        e.material_cost, e.conversion_cost = self.material.value(), self.conversion.value()
        e.capital_rate, e.storage_rate = self.cap_rate.value(), self.sto_rate.value()
        e.obsolescence_rate, e.work_days_per_year = self.obs_rate.value(), self.days_year.value()
        e.include_transit = self.transit.isChecked()

        cur = analyze(self.map)
        self.k_capital.set_value(money(cur.capital_total))
        self.k_holding.set_value(money(cur.holding_year))
        self.k_unit.set_value(f"{cur.holding_per_unit:,.2f}")
        self.k_lead.set_value(f"{cur.lead_time_days:.2f} días")
        self.k_turns.set_value(f"{cur.turns:,.1f}" if cur.turns else "—")
        self._fill_table(cur)
        self.breakdown.setText(
            f"Costo anual de mantener = capital {money(cur.cost_capital_year)} + almacenaje "
            f"{money(cur.cost_storage_year)} + obsolescencia {money(cur.cost_obsolescence_year)}. "
            f"El valor por unidad sube a lo largo del flujo (materia prima + conversión acumulada). "
            f"No incluye el material dentro de las máquinas.")

        fut = None
        if self._future is not None:
            fut = analyze(self._future, e)
        elif self.reduction.value() > 0:
            fut = analyze(scale_inventories(self.map, 1 - self.reduction.value() / 100.0), e)
        comp = compare(cur, fut, self.invest.value()) if fut is not None else None
        self._summary = summary_text(cur, comp)
        if comp is None:
            self.result.setText(f"<span style='{GRAY}'>Elige una reducción de inventarios, o compara con el mapa "
                                f"del estado futuro, para ver el capital liberado y el ahorro.</span>")
        else:
            self.result.setText(self._summary.split("\n", 1)[1].replace("\n", "<br><br>"))

    def _fill_table(self, cur) -> None:
        total = cur.capital_total
        self.table.setRowCount(len(cur.lines) + 1)
        bold = QFont()
        bold.setBold(True)

        def put(i, j, text, b=False):
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if j < 2 else Qt.AlignRight))
            if b:
                it.setFont(bold)
            self.table.setItem(i, j, it)

        for i, l in enumerate(cur.lines):
            share = l.capital / total * 100 if total > 0 else 0.0
            b = share >= 20
            for j, v in enumerate((l.label, "Tránsito" if l.kind == "transport" else "Inventario",
                                   f"{l.units:,.0f}", f"{l.days:.2f}", f"{l.unit_value:,.2f}", money(l.capital),
                                   f"{share:.0f} %")):
                put(i, j, v, b)
        n = len(cur.lines)
        for j, v in enumerate(("Total", "", "", f"{sum(l.days for l in cur.lines):.2f}", "", money(total),
                               "100 %" if total > 0 else "—")):
            put(n, j, v, True)
