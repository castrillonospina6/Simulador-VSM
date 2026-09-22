"""Formularios de edición: datos de un símbolo, nota de conexión y parámetros del caso."""
from __future__ import annotations

from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox,
                             QPlainTextEdit, QDialogButtonBox, QVBoxLayout, QLabel)

from .models import (CaseParams, KIND_LABELS, SYMBOL_SPECS, PROCESS_KINDS, INVENTORY_KINDS,
                     CONN_LABELS)

TRANSPORT_MODES = [("camion", "Camión"), ("avion", "Avión"), ("barco", "Barco")]


def _dspin(value: float, lo: float, hi: float, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setDecimals(decimals)
    sb.setValue(value)
    if suffix:
        sb.setSuffix(suffix)
    return sb


def _ispin(value: int, lo: int, hi: int) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(value)
    return sb


class NodeEditDialog(QDialog):
    """Edita los datos del nodo según su tipo. `accept()` escribe en el modelo."""

    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle(f"Editar · {KIND_LABELS.get(node.kind, 'símbolo')}")
        self.setMinimumWidth(380)
        form = QFormLayout()
        self.name = QLineEdit(node.name)
        form.addRow("Nombre", self.name)
        self.w = {}          # atributo -> widget

        if node.kind in PROCESS_KINDS:
            self.w["cycle_time_s"] = _dspin(node.cycle_time_s, 0, 1e7, 2, " s")
            self.w["changeover_s"] = _dspin(node.changeover_s, 0, 1e7, 2, " s")
            self.w["uptime_pct"] = _dspin(node.uptime_pct, 0, 100, 1, " %")
            self.w["operators"] = _ispin(node.operators, 0, 999)
            self.w["shifts"] = _ispin(node.shifts, 1, 3)
            form.addRow("Tiempo de ciclo (TC) por pieza", self.w["cycle_time_s"])
            form.addRow("Tiempo de cambio (C/O)", self.w["changeover_s"])
            form.addRow("Disponibilidad", self.w["uptime_pct"])
            form.addRow("Operarios", self.w["operators"])
            form.addRow("Turnos", self.w["shifts"])
            self.w["mttr_s"] = _dspin(node.mttr_s, 0, 1e7, 0, " s")
            form.addRow("Reparación media por falla (simulación; 0 = por defecto)", self.w["mttr_s"])
        elif node.kind in INVENTORY_KINDS:
            self.w["quantity"] = _dspin(node.quantity, 0, 1e9, 0, " u")
            form.addRow("Cantidad almacenada", self.w["quantity"])
            if node.kind == "supermarket":
                self.w["max_level"] = _dspin(node.max_level, 0, 1e9, 0, " u")
                self.w["min_level"] = _dspin(node.min_level, 0, 1e9, 0, " u")
                form.addRow("Nivel máximo (0 = 2 × cantidad)", self.w["max_level"])
                form.addRow("Nivel mínimo de seguridad", self.w["min_level"])
            if node.kind == "fifo_lane":
                self.w["capacity"] = _dspin(node.capacity, 0, 1e9, 0, " uds")
                form.addRow("Capacidad máxima del carril", self.w["capacity"])
        elif node.kind in ("supplier", "customer"):
            self.w["note"] = QLineEdit(node.note)
            form.addRow("Nota (frecuencia / modo de entrega)", self.w["note"])
        elif node.kind == "transport":
            self.mode = QComboBox()
            for key, label in TRANSPORT_MODES:
                self.mode.addItem(label, key)
            self.mode.setCurrentIndex(max(0, self.mode.findData(node.mode)))
            form.addRow("Medio de transporte", self.mode)
            self.w["transit_days"] = _dspin(node.transit_days, 0, 1000, 2, " días")
            form.addRow("Tiempo en tránsito", self.w["transit_days"])
        elif node.kind in SYMBOL_SPECS:
            for f in SYMBOL_SPECS[node.kind].get("fields", []):
                attr, typ = f["attr"], f["type"]
                cur = getattr(node, attr)
                if typ == "multiline":
                    w = QPlainTextEdit(str(cur))
                    w.setMinimumHeight(90)
                elif typ == "text":
                    w = QLineEdit(str(cur))
                elif typ == "int":
                    w = _ispin(int(cur), int(f.get("min", 0)), int(f.get("max", 999999)))
                else:
                    w = _dspin(float(cur), f.get("min", 0), f.get("max", 1e9), 2, f.get("suffix", ""))
                self.w[attr] = w
                form.addRow(f["label"], w)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def accept(self):
        self.node.name = self.name.text().strip() or self.node.name
        for attr, widget in self.w.items():
            if isinstance(widget, QLineEdit):
                value = widget.text().strip()
            elif isinstance(widget, QPlainTextEdit):
                value = widget.toPlainText()
            elif isinstance(widget, QSpinBox):
                value = int(widget.value())
            else:
                value = widget.value()
            setattr(self.node, attr, value)
        if hasattr(self, "mode"):
            self.node.mode = self.mode.currentData()
        super().accept()


class ConnectionNoteDialog(QDialog):
    """Nota/etiqueta de una conexión (frecuencia, capacidad máx. de un carril FIFO…)."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(f"Conexión · {CONN_LABELS.get(conn.kind, conn.kind)}")
        self.setMinimumWidth(360)
        self.note = QLineEdit(conn.note)
        hint = "máx 20 uds" if conn.kind == "fifo" else "p. ej. diaria, semanal, 200 uds"
        self.note.setPlaceholderText(hint)
        form = QFormLayout()
        form.addRow("Etiqueta / nota", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def accept(self):
        self.conn.note = self.note.text().strip()
        super().accept()


class ParamsDialog(QDialog):
    """Parámetros del caso: determinan el Takt Time."""

    def __init__(self, params: CaseParams, parent=None):
        super().__init__(parent)
        self.params = params
        self.setWindowTitle("Parámetros del caso")
        form = QFormLayout()
        self.demand = _dspin(params.customer_demand, 0, 1e9, 0, " u/día")
        self.shifts = _ispin(params.shifts, 1, 3)
        self.hours = _dspin(params.hours_per_shift, 0, 24, 2, " h")
        self.unavail = _dspin(params.unavailable_min_per_shift, 0, 1440, 0, " min")
        form.addRow("Demanda del cliente", self.demand)
        form.addRow("Turnos por día", self.shifts)
        form.addRow("Horas por turno", self.hours)
        form.addRow("Tiempo no disponible por turno", self.unavail)
        self.preview = QLabel()
        for w in (self.demand, self.shifts, self.hours, self.unavail):
            w.valueChanged.connect(self._update_preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.preview)
        lay.addWidget(buttons)
        self._update_preview()

    def _current(self) -> CaseParams:
        return CaseParams(self.demand.value(), self.shifts.value(), self.hours.value(),
                          self.unavail.value())

    def _update_preview(self):
        p = self._current()
        self.preview.setText(f"<b>Takt Time = {p.takt_time_s:.2f} s</b> "
                             f"(tiempo disponible/día: {p.available_seconds_per_day:,.0f} s)")

    def accept(self):
        c = self._current()
        self.params.customer_demand = c.customer_demand
        self.params.shifts = c.shifts
        self.params.hours_per_shift = c.hours_per_shift
        self.params.unavailable_min_per_shift = c.unavailable_min_per_shift
        super().accept()
