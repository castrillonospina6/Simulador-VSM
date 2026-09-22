"""Diálogo de simulación dinámica (Qt 'offscreen')."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")
pytest.importorskip("simpy")

from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog

from vsm.cases import CASES
from vsm.main_window import MainWindow
from vsm.models import VSMMap
from vsm.sim_dialogs import SimulationDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_dialogo_simula_y_llena_las_vistas(app):
    d = SimulationDialog(CASES["taburetes"].reference_map())
    d.days.setValue(6); d.warm.setValue(1); d.reps.setValue(2)
    d.run()
    r = d.result
    assert r is not None and len(d.bars.stations) == 4
    assert d.t_buf.rowCount() == len(r.buffers) and d.pick.count() == len(r.series)
    assert d.chart.pts
    assert "Qué muestra" in d.notes.toPlainText()
    for w in (d.bars, d.chart):
        assert not w.grab().isNull()


def test_dialogo_muestra_error_sin_romper(app):
    d = SimulationDialog(VSMMap())
    d.run()
    assert d.result is None and "procesos" in d.status.text() and d.btn.isEnabled()


def test_menu_simulacion(app, monkeypatch):
    monkeypatch.setattr(QDialog, "exec_", lambda self: 0)
    w = MainWindow()
    assert "Simulación" in [a.text().replace("&", "") for a in w.menuBar().actions()]
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[1]))
    w.open_simulation()
    assert avisos == ["Nada que simular"]
    w.canvas.set_map(CASES["taburetes"].reference_map())
    w.open_simulation()


# ---------------------------------------------------------------- animación y supermercado
from PyQt5.QtCore import QPointF
from vsm.canvas_view import CanvasView
from vsm.sim_player import SimPlayer, SimPlayerBar, SimOverlay
from vsm.simulation import SimConfig, simulate
from vsm.models import VSMMap, CaseParams, make_node


def pull_map(max_sm, min_sm=60):
    m = VSMMap(params=CaseParams(900, 2, 8, 30))
    x = 0
    for kind, v in (("inventory", 900), ("process", ("P1", 30, 80)), ("supermarket", 300),
                    ("process", ("P2", 50, 100)), ("inventory", 900)):
        n = make_node(kind, x, 0); x += 200
        if kind == "process":
            n.name, n.cycle_time_s, n.uptime_pct = v
        else:
            n.quantity = v
        m.add_node(n)
    m.nodes_of("process")[0].mttr_s = 1800
    sm = m.nodes_of("supermarket")[0]
    sm.max_level, sm.min_level = max_sm, min_sm
    return m, sm



def test_animacion_pinta_estados_y_niveles_y_no_sale_en_exportaciones(app):
    m, sm = pull_map(400)
    cv = CanvasView(m)
    res = simulate(m, SimConfig(days=6, warmup_days=1, replications=1, sample_points=60))
    pl = SimPlayer(cv, res)
    pl.start()
    assert len(pl.overlays) == 5                                        # 2 procesos + 3 inventarios
    pl.seek(30)
    ov = pl.overlays[sm.id]
    assert ov.level is not None and ov.cap == pytest.approx(res.node_cap[sm.id])
    p1 = pl.overlays[m.nodes_of("process")[0].id]
    assert p1.state in ("busy", "down", "blocked", "starved", "idle")
    pl._tick(); pl.play(); pl.pause()
    from PyQt5.QtGui import QImage, QPainter
    from PyQt5.QtWidgets import QStyleOptionGraphicsItem
    for o in pl.overlays.values():                                      # cada capa se dibuja sin errores
        for i in (0, 30, len(res.frames) - 1):
            pl.seek(i)
            img = QImage(300, 200, QImage.Format_ARGB32)
            p = QPainter(img); o.paint(p, QStyleOptionGraphicsItem()); p.end()
    img = cv.export_image(1.0)                                          # con overlays visibles: no rompe y los oculta
    assert img is not None and all(o.isVisible() for o in pl.overlays.values())
    pl.stop()
    assert not pl.overlays and not [i for i in cv._scene.items() if isinstance(i, SimOverlay)]


def test_animacion_se_detiene_al_reemplazar_el_mapa(app):
    m, _ = pull_map(400)
    cv = CanvasView(m)
    res = simulate(m, SimConfig(days=4, warmup_days=1, replications=1, sample_points=30))
    pl = SimPlayer(cv, res)
    pl.start(); pl.play()
    cv.set_map(CASES["taburetes"].reference_map())                      # los símbolos viejos se destruyen
    assert not pl.playing and not pl.overlays


def test_barra_de_reproduccion(app):
    m, _ = pull_map(400)
    cv = CanvasView(m)
    res = simulate(m, SimConfig(days=4, warmup_days=1, replications=1, sample_points=30))
    bar, pl = SimPlayerBar(), SimPlayer(cv, res)
    bar.bind(pl); pl.start()
    assert bar.slider.maximum() == len(res.frames) - 1
    bar.slider.setValue(10)
    assert int(pl.pos) == 10 and "Día" in bar.label.text()
    bar._toggle(); assert pl.playing
    bar._toggle(); assert not pl.playing
    bar.act_close.trigger()
    assert not bar.isVisible()


def test_dialogo_dictamina_supermercados_y_barre_tamanos(app):
    m, sm = pull_map(200)
    d = SimulationDialog(m)
    d.days.setValue(30); d.warm.setValue(2); d.reps.setValue(4)
    d.run()
    assert d.t_sm.rowCount() == 1 and d.t_sm.item(0, 1).text() == "NO aguanta"
    assert d.btn_anim.isEnabled() and "NO aguanta" in d.sm_note.toPlainText()
    d._sweep()
    assert d.t_sweep.rowCount() == 6
    assert d.t_sweep.item(0, 5).text() != "Aguanta" and d.t_sweep.item(5, 5).text() == "Aguanta"


def test_boton_animar_y_menu_de_la_ventana(app, monkeypatch):
    m, _ = pull_map(400)
    w = MainWindow()
    w.canvas.set_map(m)

    def fake_exec(self):
        self.days.setValue(4); self.warm.setValue(1); self.reps.setValue(1)
        self.run(); self._animate()
        return 1
    monkeypatch.setattr(SimulationDialog, "exec_", fake_exec)
    w.open_simulation()
    assert w.player is not None and w.player.playing and w.sim_bar.isVisibleTo(w)
    w.player.stop()
    assert not w.sim_bar.isVisibleTo(w)
    w.replay_simulation()                                               # reproduce la última guardada
    assert w.player.overlays
