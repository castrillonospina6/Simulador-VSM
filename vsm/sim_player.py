"""Animación de la simulación sobre el propio mapa: estado de cada proceso y nivel de cada inventario.

`SimOverlay` es un elemento hijo de cada símbolo del flujo (no toca su dibujo ni el modelo); `SimPlayer` avanza
los fotogramas grabados por `simulation.simulate` con un temporizador; `SimPlayerBar` son los controles.
"""
from __future__ import annotations

from typing import Dict, Optional

from PyQt5.QtCore import Qt, QObject, QPointF, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
from PyQt5.QtWidgets import (QGraphicsItem, QToolBar, QAction, QComboBox, QSlider, QLabel)

from .models import PROCESS_KINDS, INVENTORY_KINDS
from .simulation import SimResult

STATE_COLOR = {"busy": "#4a86c5", "down": "#e08e0b", "blocked": "#c0392b", "starved": "#7f8c8d",
               "idle": "#27ae60"}
STATE_TEXT = {"busy": "Trabajando", "down": "En falla", "blocked": "Bloqueado", "starved": "Sin material",
              "idle": "Espera señal"}
FLOW_KINDS = set(PROCESS_KINDS) | set(INVENTORY_KINDS) | {"transport"}


def _font(px: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(px)
    f.setBold(bold)
    return f


class SimOverlay(QGraphicsItem):
    """Capa de animación de un símbolo: insignia de estado (procesos) o barra de nivel (inventarios)."""

    def __init__(self, parent_item):
        super().__init__(parent_item)
        self.node = parent_item.node
        self.state: Optional[str] = None
        self.level: Optional[float] = None
        self.cap = self.mn = 0.0
        self.done: Optional[float] = None
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        return self.parentItem().body_rect().adjusted(-45, -40, 45, 60)

    def set_frame(self, state, level, cap, mn, done) -> None:
        self.state, self.level, self.cap, self.mn, self.done = state, level, cap, mn, done
        self.update()

    def paint(self, p: QPainter, option, widget=None):
        r = self.parentItem().body_rect()
        kind = self.node.kind
        p.setRenderHint(QPainter.Antialiasing)
        if kind in PROCESS_KINDS and self.state:
            col = QColor(STATE_COLOR[self.state])
            p.setPen(QPen(col, 3.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 4, 4)
            badge = QRectF(r.left(), r.top() - 18, r.width(), 16)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(badge, 3, 3)
            p.setPen(QColor("#ffffff"))
            p.setFont(_font(10, True))
            p.drawText(badge, Qt.AlignCenter, STATE_TEXT[self.state])
            if self.done is not None:
                p.setPen(QColor("#455a64"))
                p.setFont(_font(10))
                p.drawText(QRectF(r.left(), r.bottom() + 3, r.width(), 14), Qt.AlignCenter,
                           f"producido: {self.done:,.0f} u")
        elif kind == "transport" and self.level is not None:
            p.setPen(QColor("#1f3a6b"))
            p.setFont(_font(10, True))
            p.drawText(QRectF(r.left() - 20, r.top() - 18, r.width() + 40, 14), Qt.AlignCenter,
                       f"en camino: {self.level:,.0f} u")
        elif kind in INVENTORY_KINDS and self.level is not None and self.cap > 0:
            frac = max(0.0, min(1.0, self.level / self.cap))
            bar = QRectF(r.left(), r.top() - 14, max(r.width(), 40), 9)
            if self.level <= 0:
                col = QColor("#c0392b")                                   # vacío: deja sin material al siguiente
            elif kind != "supermarket" and frac >= 0.999:
                col = QColor("#c0392b")                                   # lleno: bloquea al anterior
            elif kind == "supermarket" and self.mn and self.level < self.mn:
                col = QColor("#e08e0b")                                   # bajo el mínimo de seguridad
            elif frac < 0.25:
                col = QColor("#e08e0b")
            else:
                col = QColor("#27ae60")
            p.setPen(QPen(QColor("#90a4ae"), 1))
            p.setBrush(QColor("#ffffff"))
            p.drawRect(bar)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRect(QRectF(bar.left(), bar.top(), bar.width() * frac, bar.height()))
            if kind == "supermarket" and self.mn:
                x = bar.left() + bar.width() * min(1.0, self.mn / self.cap)
                p.setPen(QPen(QColor("#2c3e50"), 1.5))
                p.drawLine(QPointF(x, bar.top() - 2), QPointF(x, bar.bottom() + 2))
            p.setPen(QColor("#2c3e50"))
            p.setFont(_font(10, True))
            p.drawText(QRectF(bar.left() - 20, bar.top() - 16, bar.width() + 40, 14), Qt.AlignCenter,
                       f"{self.level:,.0f} / {self.cap:,.0f}")


class SimPlayer(QObject):
    """Reproduce los fotogramas de una simulación sobre el canvas."""

    frameChanged = pyqtSignal(int, str)
    playingChanged = pyqtSignal(bool)
    stopped = pyqtSignal()

    FPS = 20.0                                  # fotogramas por segundo a velocidad 1×

    def __init__(self, canvas, result: SimResult, parent=None):
        super().__init__(parent)
        self.canvas, self.result = canvas, result
        self.frames = result.frames
        self.overlays: Dict[str, SimOverlay] = {}
        self.pos, self.speed, self.playing = 0.0, 1.0, False
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        canvas.mapReplaced.connect(self.stop)

    def start(self) -> None:
        self.stop_overlays()
        for nid, item in self.canvas.node_items().items():
            if item.node.kind in FLOW_KINDS:
                self.overlays[nid] = SimOverlay(item)
        self.seek(0)

    # -- control
    def play(self) -> None:
        if not self.frames:
            return
        if self.pos >= len(self.frames) - 1:
            self.pos = 0.0
        self.playing = True
        self.timer.start()
        self.playingChanged.emit(True)

    def pause(self) -> None:
        self.playing = False
        self.timer.stop()
        self.playingChanged.emit(False)

    def set_speed(self, x: float) -> None:
        self.speed = max(0.1, float(x))

    def seek(self, i: int) -> None:
        if not self.frames:
            return
        self.pos = float(max(0, min(len(self.frames) - 1, i)))
        self._show()

    def _tick(self) -> None:
        self.pos += self.speed * self.FPS * self.timer.interval() / 1000.0
        if self.pos >= len(self.frames) - 1:
            self.pos = float(len(self.frames) - 1)
            self.pause()
        self._show()

    def _show(self) -> None:
        i = int(self.pos)
        f, res = self.frames[i], self.result
        for nid, ov in self.overlays.items():
            try:
                ov.set_frame(f.state.get(nid), f.level.get(nid), res.node_cap.get(nid, 0.0),
                             res.node_min.get(nid, 0.0), f.done.get(nid))
            except RuntimeError:                # el símbolo ya no existe (mapa reemplazado)
                pass
        tag = "calentamiento" if f.day < res.warmup_days else "medido"
        self.frameChanged.emit(i, f"Día {f.day:.1f} de {self.frames[-1].day:.0f} · {tag}")

    def stop_overlays(self) -> None:
        for ov in self.overlays.values():
            try:
                if ov.scene() is not None:
                    ov.scene().removeItem(ov)
            except RuntimeError:
                pass
        self.overlays.clear()

    def stop(self) -> None:
        self.pause()
        self.stop_overlays()
        try:
            self.canvas.mapReplaced.disconnect(self.stop)
        except (TypeError, RuntimeError):
            pass
        self.stopped.emit()


class SimPlayerBar(QToolBar):
    """Controles de la animación: ▶/⏸, velocidad, línea de tiempo y cerrar."""

    def __init__(self, parent=None):
        super().__init__("Animación", parent)
        self.setMovable(False)
        self.player: Optional[SimPlayer] = None
        self.act_play = QAction("▶ Reproducir", self)
        self.act_play.triggered.connect(self._toggle)
        self.addAction(self.act_play)
        self.speed = QComboBox()
        for label, v in (("0.5×", 0.5), ("1×", 1.0), ("2×", 2.0), ("4×", 4.0), ("8×", 8.0)):
            self.speed.addItem(label, v)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(lambda *_: self.player and self.player.set_speed(
            self.speed.currentData()))
        self.addWidget(self.speed)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimumWidth(320)
        self.slider.valueChanged.connect(self._slid)
        self.addWidget(self.slider)
        self.label = QLabel("")
        self.label.setMinimumWidth(200)
        self.addWidget(self.label)
        self.act_close = QAction("✕ Cerrar animación", self)
        self.act_close.triggered.connect(lambda: self.player and self.player.stop())
        self.addAction(self.act_close)
        self.hide()

    def bind(self, player: SimPlayer) -> None:
        self.player = player
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(player.frames) - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        player.set_speed(self.speed.currentData())
        player.frameChanged.connect(self._frame)
        player.playingChanged.connect(lambda on: self.act_play.setText("⏸ Pausa" if on else "▶ Reproducir"))
        player.stopped.connect(self.hide)
        self.show()

    def _toggle(self) -> None:
        if self.player:
            self.player.pause() if self.player.playing else self.player.play()

    def _slid(self, v: int) -> None:
        if self.player and int(self.player.pos) != v:
            self.player.seek(v)

    def _frame(self, i: int, text: str) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(i)
        self.slider.blockSignals(False)
        self.label.setText(text)
