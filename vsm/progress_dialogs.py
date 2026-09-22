"""Diálogos de progresión: pistas con costo y panel de cinturón / XP / racha."""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QFrame)

from .hints import available_hints, hint_text, hints_cost
from .progress import Progress, next_belt, daily_case


def _rich(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setTextFormat(Qt.RichText)
    lab.setWordWrap(True)
    return lab


# =============================================================================
# Pistas
# =============================================================================
class HintDialog(QDialog):
    """Lista las pistas del caso. `used` es el conjunto (compartido con la ventana) de ids ya reveladas."""

    def __init__(self, case, used: set, parent=None):
        super().__init__(parent)
        self.case, self.used = case, used
        self.buttons = {}
        self.setWindowTitle(f"Pistas · {case.title}")
        self.resize(560, 520)
        self.body = QVBoxLayout()
        self.total = _rich()
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        note = _rich("Cada pista revelada se <b>resta de tu puntaje</b> al pulsar «Evaluar mi mapa» "
                     "(y por tanto reduce el XP). Úsalas solo si estás atascado.")
        note.setStyleSheet("color:#607d8b;")
        lay.addWidget(note)
        lay.addLayout(self.body)
        lay.addStretch(1)
        lay.addWidget(self.total)
        lay.addWidget(close)
        self._rebuild()

    def _rebuild(self):
        while self.body.count():
            w = self.body.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.buttons.clear()
        for h in available_hints(self.case):
            box = QFrame()
            box.setFrameShape(QFrame.StyledPanel)
            v = QVBoxLayout(box)
            v.addWidget(_rich(f"<b>{h.title}</b>"))
            if h.id in self.used:
                v.addWidget(_rich(hint_text(self.case, h.id)))
            else:
                b = QPushButton(f"Revelar  (−{h.cost} pts)")
                b.clicked.connect(lambda _=False, hid=h.id: self._reveal(hid))
                v.addWidget(b)
                self.buttons[h.id] = b
            self.body.addWidget(box)
        self.total.setText(f"Pistas usadas: <b>−{hints_cost(self.case, self.used)} pts</b>")

    def _reveal(self, hint_id: str):
        self.used.add(hint_id)
        self._rebuild()


# =============================================================================
# Panel de progreso
# =============================================================================
class ProgressDialog(QDialog):
    HEADERS = ["Nivel", "Casos superados", "XP ganada", "XP posible"]

    def __init__(self, progress: Progress, open_daily: Optional[Callable[[], None]] = None,
                 on_change: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self.progress, self._open_daily, self._on_change = progress, open_daily, on_change
        self.setWindowTitle("Mi progreso")
        self.resize(560, 560)
        self.belt_lbl, self.xp_lbl, self.daily_lbl = _rich(), _rich(), _rich()
        self.bar = QProgressBar()
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.btn_daily = QPushButton("Ir al caso del día")
        self.btn_daily.clicked.connect(self._go_daily)
        reset = QPushButton("Reiniciar progreso…")
        reset.clicked.connect(self._reset)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        foot = QHBoxLayout()
        foot.addWidget(reset)
        foot.addStretch(1)
        foot.addWidget(self.btn_daily)
        foot.addWidget(close)

        lay = QVBoxLayout(self)
        lay.addWidget(self.belt_lbl)
        lay.addWidget(self.bar)
        lay.addWidget(self.xp_lbl)
        lay.addWidget(self.daily_lbl)
        lay.addWidget(self.table, 1)
        lay.addLayout(foot)
        self.refresh()

    def refresh(self):
        p = self.progress
        b, nxt = p.belt, next_belt(p.xp)
        chip = f"<span style='background:{b.color}'>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>"
        self.belt_lbl.setText(f"<span style='font-size:18px'>{chip} <b>Cinturón {b.name}</b></span>")
        if nxt is None:
            self.bar.setRange(0, 1)
            self.bar.setValue(1)
            self.bar.setFormat("Cinturón máximo")
            self.xp_lbl.setText(f"<b>{p.xp} XP</b> · has alcanzado el máximo cinturón.")
        else:
            self.bar.setRange(0, nxt.min_xp - b.min_xp)
            self.bar.setValue(p.xp - b.min_xp)
            self.bar.setFormat("%v / %m XP")
            self.xp_lbl.setText(f"<b>{p.xp} XP</b> · te faltan <b>{nxt.min_xp - p.xp}</b> para el Cinturón "
                                f"{nxt.name}.")
        today = date.today()
        dc = daily_case(today)
        state = "✓ completado hoy" if p.daily_done(today) else "pendiente"
        streak = p.current_streak(today)
        self.daily_lbl.setText(f"⭐ <b>Caso del día:</b> {dc.title} ({dc.level}) — {state}. "
                               f"Racha: <b>{streak}</b> día(s) · mejor racha: {p.daily['best_streak']}.")
        self.btn_daily.setEnabled(self._open_daily is not None)
        rows = p.level_summary()
        self.table.setRowCount(len(rows))
        for i, (lvl, done, total, xp, xp_max) in enumerate(rows):
            for j, v in enumerate((lvl, f"{done} / {total}", str(xp), str(xp_max))):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if j == 0 else Qt.AlignRight))
                self.table.setItem(i, j, it)

    def _go_daily(self):
        self.accept()
        if self._open_daily:
            self._open_daily()

    def _reset(self):
        r = QMessageBox.question(self, "Reiniciar progreso",
                                 "Se borrarán tu XP, tu cinturón y tu racha. ¿Continuar?")
        if r == QMessageBox.Yes:
            self.progress.reset()
            self.refresh()
            if self._on_change:
                self._on_change()
