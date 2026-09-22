"""Ventana principal: ensambla canvas, paleta, métricas en vivo y panel de caso."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Dict, Optional, Set

from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QMainWindow, QAction, QActionGroup, QDockWidget, QTextBrowser, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QMessageBox, QDialog, QToolBar, QApplication,
                             QLabel)

from .canvas_items import set_symbol_style, symbol_style
from .calc_dialogs import PullCalcDialog, EconomicDialog
from .canvas_view import CanvasView
from .cases import CASES, CASES_BY_LEVEL, LEVEL_INFO, Case, LEVELS, brief_html, generate_case, get_case
from .dialogs import ParamsDialog
from .engine import compute_metrics
from .evaluation import evaluate, result_html
from .hints import hints_cost
from .exporter import (ExportError, default_filename, export_png, export_balance_png, export_pdf,
                       export_pptx)
from .metrics_panel import MetricsPanel
from .models import VSMMap, CONN_LABELS, CONN_KINDS, Process, Inventory
from .persistence import save_map, load_map, EXTENSION
from .sim_dialogs import SimulationDialog
from .sim_player import SimPlayer, SimPlayerBar
from .progress import Progress, adjust_result, attempt_html, daily_case
from .progress_dialogs import HintDialog, ProgressDialog
from .toolbox import ToolboxList, make_conn_icon

CONN_SHORT = {"push": "Push", "fifo": "FIFO", "pull": "Pull", "info_manual": "Info manual",
              "info_electronic": "Info electrónica", "info_phone": "Teléfono"}

FREE_MODE_HTML = """
<h2>Modo libre</h2>
<p>Estás en el lienzo vacío. Puedes dibujar cualquier VSM y ver sus métricas en vivo, o
<b>elegir un caso</b> en el menú <b>Casos</b> (23 casos en 6 niveles, de Junior a Negro, más casos aleatorios) para practicar con datos de una empresa y recibir una evaluación.</p>
<h4>Cómo se usa</h4>
<ol>
<li>Arrastra símbolos desde el panel izquierdo al canvas (33 símbolos VSM en 6 categorías).</li>
<li><b>Doble clic</b> sobre un símbolo para editar sus datos; doble clic sobre una flecha para ponerle una etiqueta (p. ej. «máx 20 uds» en un carril FIFO).</li>
<li>Usa los botones de la barra de herramientas (Push, FIFO, Pull, Info manual, Info electrónica, Teléfono)
y haz clic en el origen y luego en el destino. <b>Esc</b> cancela.</li>
<li><b>Archivo → Parámetros del caso</b>: demanda, turnos y horas (determinan el Takt Time).</li>
<li><b>Supr</b> borra lo seleccionado. <b>Ctrl + rueda</b> hace zoom.</li>
<li>Menú <b>Progreso</b>: cinturones y XP, pistas (restan puntos) y el <b>caso del día</b>.</li>
<li>Menú <b>Simulación</b> (F5): simulación dinámica con variabilidad; muestra colas, bloqueos e inanición que el VSM estático no ve.</li>
<li>Menú <b>Estado futuro</b>: calculadora de Kanban y supermercado, y vista económica (capital inmovilizado y costo de mantener).</li>
</ol>
<p><i>Alcance del MVP: el motor lee el flujo como una secuencia lineal, de izquierda a derecha según la
posición X de cada símbolo.</i></p>
"""


class MainWindow(QMainWindow):
    def __init__(self, progress: Optional[Progress] = None):
        super().__init__()
        self.case: Optional[Case] = None
        self._fitted = False
        self.progress = progress if progress is not None else Progress.default()
        self._hints_used: Dict[str, Set[str]] = {}       # pistas reveladas en el intento actual, por caso
        self._solution_seen: Set[str] = set()            # casos cuya solución se vio en el intento actual
        self._daily_banner = False
        self.player = None                               # animación de la última simulación
        self._last_sim = None
        self.rank_label = QLabel()
        self.statusBar().addPermanentWidget(self.rank_label)

        self.canvas = CanvasView(VSMMap())
        self.setCentralWidget(self.canvas)
        self.metrics_panel = MetricsPanel()
        self.toolbox = ToolboxList()
        self.case_view = QTextBrowser()
        self.conn_actions = {}

        self._build_docks()
        self._build_menus()
        self._build_toolbar()
        self.sim_bar = SimPlayerBar(self)
        self.addToolBar(Qt.BottomToolBarArea, self.sim_bar)

        self.canvas.mapChanged.connect(self.recalc)
        self.canvas.statusMessage.connect(lambda t: self.statusBar().showMessage(t, 6000))
        self.canvas.connectionModeCancelled.connect(self._uncheck_conn_actions)
        self._show_free_mode()
        self._refresh_rank()
        self.recalc()

    # ------------------------------------------------------------------ UI
    def _build_docks(self):
        d1 = QDockWidget("Símbolos", self)
        d1.setWidget(self.toolbox)
        d1.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, d1)

        d2 = QDockWidget("Métricas en vivo", self)
        d2.setWidget(self.metrics_panel)
        d2.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.BottomDockWidgetArea, d2)

        d3 = QDockWidget("Caso", self)
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(4, 4, 4, 4)
        self.case_view.setOpenExternalLinks(False)
        self.case_view.document().setDefaultStyleSheet(
            "body { font-size: 10pt; } h2 { font-size: 15pt; } h4 { font-size: 11pt; } "
            "td, th { font-size: 9pt; }")
        lay.addWidget(self.case_view, 1)
        self.eval_btn = QPushButton("Evaluar mi mapa")
        self.eval_btn.setStyleSheet("padding:8px; font-weight:bold;")
        self.eval_btn.clicked.connect(self.evaluate_map)
        self.hint_btn = QPushButton("Pedir pista")
        self.hint_btn.setStyleSheet("padding:8px;")
        self.hint_btn.clicked.connect(self.open_hints)
        row = QHBoxLayout()
        row.addWidget(self.eval_btn, 2)
        row.addWidget(self.hint_btn, 1)
        lay.addLayout(row)
        d3.setWidget(holder)
        d3.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        d3.setMinimumWidth(400)
        self.addDockWidget(Qt.RightDockWidgetArea, d3)
        self.resizeDocks([d3], [430], Qt.Horizontal)
        self.resizeDocks([d2], [250], Qt.Vertical)
        self.docks = (d1, d2, d3)

    def _act(self, text, slot, shortcut=None) -> QAction:
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(shortcut)
        return a

    def _build_menus(self):
        mb = self.menuBar()
        m_file = mb.addMenu("&Archivo")
        m_file.addAction(self._act("Nuevo mapa (modo libre)", self.new_map, QKeySequence.New))
        m_file.addAction(self._act("Abrir…", self.open_map, QKeySequence.Open))
        m_file.addAction(self._act("Guardar…", self.save_map, QKeySequence.Save))
        m_file.addSeparator()
        m_exp = m_file.addMenu("Exportar")
        m_exp.addAction(self._act("Mapa como imagen PNG…", self.export_map_png))
        m_exp.addAction(self._act("Gráfico de balance (Yamazumi) como PNG…", self.export_balance_png))
        m_exp.addAction(self._act("Informe PDF (mapa + métricas)…", self.export_pdf))
        m_exp.addAction(self._act("Presentación PowerPoint (.pptx)…", self.export_pptx))
        m_file.addSeparator()
        m_file.addAction(self._act("Parámetros del caso…", self.edit_params, "Ctrl+P"))
        m_file.addSeparator()
        m_file.addAction(self._act("Salir", self.close, QKeySequence.Quit))

        m_edit = mb.addMenu("&Editar")
        self.undo_action = self._act("Deshacer", self.canvas.undo, QKeySequence.Undo)
        self.redo_action = self._act("Rehacer", self.canvas.redo, QKeySequence.Redo)
        m_edit.addAction(self.undo_action)
        m_edit.addAction(self.redo_action)
        m_edit.addSeparator()
        m_edit.addAction(self._act("Copiar", self.canvas.copy_selected, QKeySequence.Copy))
        m_edit.addAction(self._act("Pegar", self.canvas.paste_clipboard, QKeySequence.Paste))
        m_edit.addSeparator()
        m_edit.addAction(self._act("Eliminar", self.canvas.delete_selected, QKeySequence.Delete))
        m_edit.addSeparator()
        m_edit.addAction(self._act("Autoconectar", self.canvas.auto_connect, "Ctrl+Shift+A"))

        m_cases = mb.addMenu("&Casos")
        for lvl in LEVELS:
            info = LEVEL_INFO[lvl]
            sub = m_cases.addMenu(f"{lvl}  {'★' * info['stars']}")
            sub.setToolTipsVisible(True)
            sub.setToolTip(info["blurb"])
            for c in CASES_BY_LEVEL[lvl]:
                a = self._act(f"{c.title}  ·  {c.sector}", lambda _=False, c=c: self.load_case(c))
                a.setToolTip(info["blurb"])
                sub.addAction(a)
        m_cases.addSeparator()
        m_rand = m_cases.addMenu("Caso aleatorio")
        for lvl in LEVELS:
            m_rand.addAction(self._act(f"Nivel {lvl}", lambda _=False, l=lvl: self.load_case(generate_case(None, l))))
        m_cases.addSeparator()
        m_cases.addAction(self._act("Evaluar mi mapa", self.evaluate_map, "Ctrl+E"))
        m_cases.addAction(self._act("Ver solución de referencia", self.show_reference))

        m_prog = mb.addMenu("&Progreso")
        m_prog.addAction(self._act("Caso del día", self.open_daily_case, "Ctrl+D"))
        m_prog.addAction(self._act("Pedir una pista… (cuesta puntos)", self.open_hints, "Ctrl+H"))
        m_prog.addSeparator()
        m_prog.addAction(self._act("Mi progreso (cinturón, XP y racha)…", self.open_progress))

        m_future = mb.addMenu("E&stado futuro")
        m_future.addAction(self._act("Calculadora de Kanban y supermercado…", self.open_pull_calc, "Ctrl+K"))
        m_future.addAction(self._act("Vista económica (capital y costo de mantener)…", self.open_economics,
                                     "Ctrl+Shift+E"))

        m_sim = mb.addMenu("Si&mulación")
        m_sim.addAction(self._act("Simulación dinámica (SimPy)…", self.open_simulation, "F5"))
        m_sim.addAction(self._act("Reproducir la última simulación en el mapa", self.replay_simulation, "F6"))

        m_view = mb.addMenu("&Ver")
        m_view.addAction(self._act("Ajustar vista al contenido", self.canvas.fit_content, "Ctrl+0"))
        m_view.addSeparator()
        self.snap_action = QAction("Alinear a rejilla", self, checkable=True)
        self.snap_action.setChecked(self.canvas.snap_to_grid_enabled())
        self.snap_action.toggled.connect(self.canvas.set_snap_to_grid)
        m_view.addAction(self.snap_action)
        m_view.addSeparator()
        m_style = m_view.addMenu("Estilo de símbolos")
        grp = QActionGroup(self)
        self.style_actions = {}
        for key, label in (("tabla", "Tabla de símbolos VSM (por defecto)"), ("libro", "Libro (Dumser)")):
            a = QAction(label, self, checkable=True)
            a.setChecked(symbol_style() == key)
            a.triggered.connect(lambda _=False, k=key: self.set_style(k))
            grp.addAction(a)
            m_style.addAction(a)
            self.style_actions[key] = a
        m_view.addSeparator()
        for d in self.docks:
            m_view.addAction(d.toggleViewAction())

        m_help = mb.addMenu("A&yuda")
        m_help.addAction(self._act("Acerca de", self.about))

    def _build_toolbar(self):
        tb = QToolBar("Conexiones", self)
        tb.setMovable(False)
        tb.setIconSize(QSize(56, 22))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        for kind in CONN_KINDS:
            a = QAction(make_conn_icon(kind), CONN_SHORT[kind], self)
            a.setToolTip(CONN_LABELS[kind] + " — doble clic sobre la flecha para añadir una etiqueta")
            a.setCheckable(True)
            a.toggled.connect(lambda checked, k=kind: self._on_conn_toggled(k, checked))
            tb.addAction(a)
            self.conn_actions[kind] = a
        tb.addSeparator()
        tb.addAction(self._act("Eliminar", self.canvas.delete_selected))
        tb.addAction(self._act("Ajustar vista", self.canvas.fit_content))
        tb.addSeparator()
        tb.addAction(self.undo_action)
        tb.addAction(self.redo_action)
        tb.addSeparator()
        tb.addAction(self._act("Copiar", self.canvas.copy_selected))
        tb.addAction(self._act("Pegar", self.canvas.paste_clipboard))
        tb.addSeparator()
        tb.addAction(self._act("Autoconectar", self.canvas.auto_connect))
        tb.addAction(self.snap_action)

    def set_style(self, name: str):
        """Cambia entre el estilo de la tabla de símbolos y el del libro."""
        set_symbol_style(name)
        self.canvas.refresh_style()
        self.toolbox.rebuild_icons()
        for kind, action in self.conn_actions.items():
            action.setIcon(make_conn_icon(kind))

    # ------------------------------------------------------- modo conexión
    def _on_conn_toggled(self, kind: str, checked: bool):
        if checked:
            for k, a in self.conn_actions.items():
                if k != kind and a.isChecked():
                    a.blockSignals(True)
                    a.setChecked(False)
                    a.blockSignals(False)
            self.canvas.set_connection_mode(kind)
        elif self.canvas.connection_mode == kind:
            self.canvas.cancel_connection_mode()

    def _uncheck_conn_actions(self):
        for a in self.conn_actions.values():
            a.blockSignals(True)
            a.setChecked(False)
            a.blockSignals(False)

    # ------------------------------------------------------------- cálculo
    def recalc(self):
        self.undo_action.setEnabled(self.canvas.can_undo())
        self.redo_action.setEnabled(self.canvas.can_redo())
        m = compute_metrics(self.canvas.map)
        self.metrics_panel.update_metrics(m)
        over = {r.node_id for r in m.processes_over_takt}
        days = {e.node_id: e.days for e in m.timeline}
        for node in self.canvas.map.nodes.values():
            item = self.canvas.item_for(node.id)
            if item is None:
                continue
            if isinstance(node, Process):
                item.set_alert(node.id in over)
            elif isinstance(node, Inventory):
                item.set_subtitle(f"≈ {days.get(node.id, 0):.1f} d")
            elif node.kind == "total_time":
                item.set_lines([f"Lead time = {m.lead_time_days:.2f} d", f"Tiempo VA = {m.va_time_s:g} s"])

    # ------------------------------------------------------------- acciones
    def _has_content(self) -> bool:
        return bool(self.canvas.map.nodes)

    def _confirm_discard(self) -> bool:
        if not self._has_content():
            return True
        r = QMessageBox.question(self, "Reemplazar mapa",
                                 "El mapa actual se perderá si no lo has guardado. ¿Continuar?")
        return r == QMessageBox.Yes

    def _show_free_mode(self):
        self.case = None
        self.case_view.setHtml(FREE_MODE_HTML)
        self.setWindowTitle("Simulador VSM — modo libre")
        self._update_hint_button()

    def new_map(self):
        if not self._confirm_discard():
            return
        self.canvas.set_map(VSMMap())
        self._show_free_mode()

    def load_case(self, case: Case, daily: bool = False):
        if not self._confirm_discard():
            return
        self.case = case
        self._start_attempt(case)
        self.canvas.set_map(VSMMap(params=replace(case.params), case_id=case.id))
        self._show_brief(case, daily)
        self.setWindowTitle(f"Simulador VSM — {case.title}")
        self.statusBar().showMessage("Caso cargado: dibuja el mapa del estado actual con los datos del enunciado.", 8000)

    def show_reference(self):
        if self.case is None:
            QMessageBox.information(self, "Sin caso", "Primero elige un caso en el menú Casos.")
            return
        r = QMessageBox.question(self, "Ver solución",
                                 "Se reemplazará tu mapa por el mapa de referencia. ¿Continuar?")
        if r == QMessageBox.Yes:
            self._solution_seen.add(self.case.id)       # este intento ya no suma XP
            self.canvas.set_map(self.case.reference_map())
            self.statusBar().showMessage("Viste la solución: este intento no suma XP.", 8000)

    def edit_params(self):
        dlg = ParamsDialog(self.canvas.map.params, self)
        if dlg.exec_():
            self.recalc()

    def evaluate_map(self):
        if self.case is None:
            QMessageBox.information(self, "Sin caso",
                                    "Para evaluar necesitas elegir un caso en el menú Casos.")
            return
        res = evaluate(self.canvas.map, self.case)
        penalty = hints_cost(self.case, self._hints_used.get(self.case.id, ()))
        att = self.progress.record(self.case, res.score, penalty,
                                   count=self.case.id not in self._solution_seen)
        res = adjust_result(res, att.net)               # puntaje neto = evaluación − pistas
        self._refresh_rank()
        dlg = QDialog(self)
        dlg.setWindowTitle("Evaluación del mapa")
        lay = QVBoxLayout(dlg)
        tb = QTextBrowser()
        tb.setHtml(attempt_html(att) + result_html(res, self.case))
        lay.addWidget(tb)
        btn = QPushButton("Cerrar")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.resize(560, 680)
        dlg.exec_()

    def save_map(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar mapa", "", f"Mapa VSM (*{EXTENSION})")
        if not path:
            return
        if not path.endswith(EXTENSION):
            path += EXTENSION
        save_map(self.canvas.map, path)
        self.statusBar().showMessage(f"Guardado en {path}", 5000)

    def open_map(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir mapa", "", f"Mapa VSM (*{EXTENSION} *.json)")
        if not path:
            return
        try:
            vmap = load_map(path)
        except Exception as exc:  # archivo corrupto o de otra versión
            QMessageBox.warning(self, "No se pudo abrir", f"El archivo no es un mapa VSM válido:\n{exc}")
            return
        if not self._confirm_discard():
            return
        self.canvas.set_map(vmap)
        case = get_case(vmap.case_id)
        if case:
            self.case = case
            self._start_attempt(case)
            self._show_brief(case)
            self.setWindowTitle(f"Simulador VSM — {case.title}")
        else:
            self._show_free_mode()

    # ---------------------------------------------------------- progresión
    def _start_attempt(self, case: Case) -> None:
        """Un caso recién cargado es un intento nuevo: sin pistas usadas ni solución vista."""
        self._hints_used[case.id] = set()
        self._solution_seen.discard(case.id)
        self._update_hint_button()

    def _show_brief(self, case: Case, daily: bool = False) -> None:
        html = brief_html(case)
        if daily:
            html = ("<p style='background:#fff3a8; padding:6px'>⭐ <b>Caso del día</b>: apruébalo hoy para ganar "
                    "un bono de XP y sumar a tu racha.</p>" + html)
        self.case_view.setHtml(html)
        self.setWindowTitle(f"Simulador VSM — {case.title}")
        self._update_hint_button()

    def _update_hint_button(self) -> None:
        if not hasattr(self, "hint_btn"):
            return
        has_case = self.case is not None
        self.hint_btn.setEnabled(has_case)
        cost = hints_cost(self.case, self._hints_used.get(self.case.id, ())) if has_case else 0
        self.hint_btn.setText(f"Pedir pista (−{cost} pts)" if cost else "Pedir pista")

    def _refresh_rank(self) -> None:
        p = self.progress
        streak = p.current_streak(date.today())
        txt = f"Cinturón {p.belt.name} · {p.xp} XP"
        if streak:
            txt += f" · racha {streak} d"
        self.rank_label.setText(txt)
        self.rank_label.setStyleSheet(f"padding:0 8px; border-left:10px solid {p.belt.color};")

    def open_hints(self):
        if self.case is None:
            QMessageBox.information(self, "Sin caso", "Las pistas son por caso: primero elige uno en el menú Casos.")
            return
        used = self._hints_used.setdefault(self.case.id, set())
        HintDialog(self.case, used, self).exec_()
        self._update_hint_button()

    def open_progress(self):
        ProgressDialog(self.progress, open_daily=self.open_daily_case, on_change=self._refresh_rank, parent=self).exec_()
        self._refresh_rank()

    def open_daily_case(self):
        self.load_case(daily_case(date.today()), daily=True)

    # ---------------------------------------------------------- exportar
    def _export_title(self) -> str:
        return self.case.title if self.case else "Mapa de flujo de valor"

    def _export(self, dlg_title: str, name_suffix: str, ext: str, file_filter: str, writer) -> None:
        """Pide la ruta y ejecuta `writer(path)`; muestra los errores de forma legible."""
        if not self._has_content():
            QMessageBox.information(self, "Nada que exportar", "El mapa está vacío: agrega símbolos primero.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, dlg_title, default_filename(self._export_title() + name_suffix, ext), file_filter)
        if not path:
            return
        if not path.lower().endswith(ext):
            path += ext
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            writer(path)
        except ExportError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "No se pudo exportar", str(exc))
            return
        except Exception as exc:  # p. ej. archivo abierto en otro programa
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error al exportar", f"{type(exc).__name__}: {exc}")
            return
        QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"Exportado: {path}", 6000)

    def export_map_png(self):
        self._export("Exportar mapa como PNG", "", ".png", "Imagen PNG (*.png)",
                     lambda path: export_png(self.canvas, path))

    def export_balance_png(self):
        self._export("Exportar gráfico de balance", "_balance", ".png", "Imagen PNG (*.png)",
                     lambda path: export_balance_png(compute_metrics(self.canvas.map), path))

    def export_pdf(self):
        self._export("Exportar informe PDF", "", ".pdf", "Documento PDF (*.pdf)",
                     lambda path: export_pdf(self.canvas, compute_metrics(self.canvas.map),
                                             self._export_title(), path))

    def export_pptx(self):
        self._export("Exportar a PowerPoint", "", ".pptx", "Presentación PowerPoint (*.pptx)",
                     lambda path: export_pptx(self.canvas, compute_metrics(self.canvas.map),
                                              self._export_title(), path))

    # ------------------------------------------------------- estado futuro
    def open_pull_calc(self):
        PullCalcDialog(self.canvas, self).exec_()

    def open_economics(self):
        EconomicDialog(self.canvas.map, self).exec_()

    # ---------------------------------------------------------- simulación
    def open_simulation(self):
        if not self._has_content():
            QMessageBox.information(self, "Nada que simular", "El mapa está vacío: agrega procesos primero.")
            return
        dlg = SimulationDialog(self.canvas.map, self)
        dlg.exec_()
        if dlg.result is not None:
            self._last_sim = dlg.result
        if dlg.animate and dlg.result is not None:
            self.start_animation(dlg.result)

    def replay_simulation(self):
        if self._last_sim is None or not self._last_sim.frames:
            QMessageBox.information(self, "Sin simulación", "Primero simula el mapa (Simulación → F5).")
            return
        self.start_animation(self._last_sim)

    def start_animation(self, result):
        """Anima el resultado sobre el mapa: estado de cada proceso y nivel de cada inventario."""
        if self.player is not None:
            self.player.stop()
        self.player = SimPlayer(self.canvas, result, self)
        self.sim_bar.bind(self.player)
        self.player.start()
        self.player.play()
        self.statusBar().showMessage("Animación: los inventarios se llenan y vacían; el color de cada proceso "
                                     "es su estado.", 8000)

    def about(self):
        QMessageBox.about(self, "Simulador VSM",
                          "<b>Simulador VSM — MVP</b><br>Motor de cálculo + canvas visual + casos "
                          "y evaluación por reglas.<br>Ver README para la hoja de ruta.")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            QTimer.singleShot(0, self.canvas.fit_content)