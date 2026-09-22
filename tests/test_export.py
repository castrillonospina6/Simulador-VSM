"""Exportación (PNG / PDF / PPTX) y gráfico de balance (Yamazumi). Modo headless (Qt 'offscreen')."""
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

from vsm.balance_chart import balance_data, render_balance_image
from vsm.canvas_view import CanvasView
from vsm.cases import CASES
from vsm.engine import compute_metrics, Metrics
from vsm.exporter import (ExportError, export_png, export_balance_png, export_pdf, export_pptx,
                          default_filename)
from vsm.main_window import MainWindow
from vsm.models import VSMMap, CaseParams, make_node


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def cv(app):
    return CanvasView(CASES["taburetes"].reference_map())


def _pages(path):
    return len(re.findall(rb"/Type\s*/Page\b", open(path, "rb").read()))


# ---------------------------------------------------------------- balance (Yamazumi)
def test_balance_datos_taburetes():
    d = balance_data(compute_metrics(CASES["taburetes"].reference_map()))
    assert d.takt_s == pytest.approx(60.0)
    assert [b.name for b in d.bars] == ["Pintura", "Montaje", "Embalaje", "Expedición"]
    assert [b.name for b in d.bars if b.over] == ["Pintura"]
    pintura = d.bars[0]
    assert pintura.eff_s == pytest.approx(60 / 0.90) and pintura.loss_s == pytest.approx(60 / 0.90 - 60)
    assert 0 < d.balance_efficiency <= 1


def test_balance_no_revienta_con_casos_extremos(app):
    render_balance_image(balance_data(Metrics()))                        # sin procesos
    m = VSMMap(params=CaseParams(customer_demand=0))                     # takt 0 y TC 0: eje de altura 0
    p = make_node("process", 0, 0)
    p.cycle_time_s = 0
    m.add_node(p)
    assert not render_balance_image(balance_data(compute_metrics(m))).isNull()


# ---------------------------------------------------------------- imagen del mapa
def test_export_image_no_altera_la_seleccion(cv):
    node = next(iter(cv.map.nodes))
    cv.item_for(node).setSelected(True)
    img = cv.export_image(1.0)
    assert img is not None and img.width() > 100 and img.height() > 100
    assert cv.item_for(node).isSelected()                                # se restaura tras exportar


def test_mapa_vacio_no_se_exporta(app, tmp_path):
    empty = CanvasView(VSMMap())
    assert empty.export_image() is None and empty.export_rect().isNull()
    with pytest.raises(ExportError):
        export_png(empty, str(tmp_path / "x.png"))


def test_export_png_y_balance_png(cv, tmp_path):
    a, b = tmp_path / "mapa.png", tmp_path / "balance.png"
    export_png(cv, str(a))
    export_balance_png(compute_metrics(cv.map), str(b))
    for f in (a, b):
        assert f.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(ExportError):                                     # sin procesos no hay balance
        export_balance_png(Metrics(), str(tmp_path / "vacio.png"))


def test_ruta_no_escribible(cv):
    with pytest.raises(ExportError):
        export_png(cv, "/no/existe/mapa.png")


# ---------------------------------------------------------------- PDF
def test_export_pdf_dos_paginas(cv, tmp_path):
    f = tmp_path / "informe.pdf"
    export_pdf(cv, compute_metrics(cv.map), "Laforêt SPRL — Taburetes", str(f))
    assert f.read_bytes()[:5] == b"%PDF-"
    assert _pages(f) == 2


def test_export_pdf_tabla_larga_se_reparte_en_paginas(app, tmp_path):
    m = VSMMap(params=CaseParams(500, 1, 8, 30))
    for i in range(45):
        n = make_node("process", i * 200, 0)
        n.name, n.cycle_time_s = f"Proceso {i + 1}", 20 + i
        m.add_node(n)
    view = CanvasView(m)
    f = tmp_path / "largo.pdf"
    export_pdf(view, compute_metrics(m), "Mapa largo", str(f))
    assert _pages(f) >= 3


# ---------------------------------------------------------------- PPTX
def test_export_pptx_cuatro_diapositivas(cv, tmp_path):
    pptx = pytest.importorskip("pptx")
    f = tmp_path / "mapa.pptx"
    export_pptx(cv, compute_metrics(cv.map), "Laforêt SPRL — Taburetes", str(f))
    prs = pptx.Presentation(str(f))
    assert len(prs.slides) == 4
    tabla = next(s for s in prs.slides[3].shapes if s.has_table).table
    assert len(tabla.rows) == 1 + 4 and tabla.cell(1, 0).text == "Pintura"


def test_nombre_de_archivo_por_defecto():
    assert default_filename("Laforêt SPRL — Taburetes", ".pdf") == "Laforêt_SPRL_Taburetes.pdf"
    assert default_filename("", ".png") == "mapa_vsm.png"


# ---------------------------------------------------------------- ventana principal (menú Exportar)
def test_menu_exportar_y_pestana_yamazumi(app, tmp_path, monkeypatch):
    pytest.importorskip("pptx")
    w = MainWindow()
    w.show()
    w.load_case(CASES["taburetes"])
    w.canvas.set_map(CASES["taburetes"].reference_map())
    assert w.metrics_panel.tabs.count() == 2
    assert len(w.metrics_panel.balance.data.bars) == 4                   # el gráfico en vivo se alimenta del motor

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("no debía fallar"))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail("no debía fallar"))
    for action, ext in ((w.export_map_png, ".png"), (w.export_balance_png, ".png"),
                        (w.export_pdf, ".pdf"), (w.export_pptx, ".pptx")):
        target = tmp_path / f"out_{action.__name__}"                     # sin extensión: la ventana debe añadirla
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, t=target, **k: (str(t), ""))
        action()
        assert os.path.getsize(str(target) + ext) > 1000


def test_exportar_mapa_vacio_avisa_y_no_pide_archivo(app, monkeypatch):
    w = MainWindow()
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[1]))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: pytest.fail("no debía abrir el diálogo"))
    w.export_pdf()
    assert avisos == ["Nada que exportar"]
