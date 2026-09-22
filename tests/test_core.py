import json, math, copy
import pytest
from vsm.models import VSMMap, CaseParams, Process, Inventory, make_node
from vsm.engine import compute_metrics
from vsm.cases import CASES, get_case, generate_case, brief_html, LEVELS
from vsm.evaluation import evaluate, LEVEL_TOL


def test_takt_basico():
    assert CaseParams(900, 2, 8, 30).takt_time_s == pytest.approx(60.0)


def test_taburetes_metricas():
    case = CASES["taburetes"]
    m = compute_metrics(case.reference_map())
    assert m.takt_time_s == pytest.approx(60.0)
    assert m.va_time_s == pytest.approx(130.0)
    # 19 días de inventario + 130 s de proceso
    assert m.lead_time_days == pytest.approx(19 + 130 / 54000, rel=1e-6)
    assert m.pce == pytest.approx(130 / (19 * 54000 + 130), rel=1e-6)
    assert m.bottleneck_name == "Pintura"
    assert [p.name for p in m.processes_over_takt] == ["Pintura"]


def test_farma_y_autopartes_tienen_un_cuello_sobre_takt():
    for cid, bott in (("farma", "Blisteado"), ("autopartes", "Soldadura")):
        m = compute_metrics(CASES[cid].reference_map())
        assert m.bottleneck_name == bott
        assert [p.name for p in m.processes_over_takt] == [bott]


def test_demanda_cero_no_rompe():
    m = VSMMap(params=CaseParams(customer_demand=0))
    m.add_node(make_node("process", 0, 0))
    r = compute_metrics(m)
    assert r.takt_time_s == 0 and r.warnings


def test_orden_por_x():
    m = VSMMap(params=CaseParams(900, 2, 8, 30))
    a = make_node("process", 500, 0); a.name = "B"; a.cycle_time_s = 10
    b = make_node("inventory", 250, 0); b.quantity = 900
    c = make_node("process", 0, 0); c.name = "A"; c.cycle_time_s = 5
    for n in (a, b, c):
        m.add_node(n)
    r = compute_metrics(m)
    assert [t.label for t in r.timeline] == ["A", "Inventario", "B"]


def test_serializacion_roundtrip():
    ref = CASES["farma"].reference_map()
    d = json.loads(json.dumps(ref.to_dict()))
    back = VSMMap.from_dict(d)
    assert len(back.nodes) == len(ref.nodes) and len(back.connections) == len(ref.connections)
    assert compute_metrics(back).lead_time_s == pytest.approx(compute_metrics(ref).lead_time_s)


@pytest.mark.parametrize("cid", list(CASES))
def test_referencia_saca_100(cid):
    case = CASES[cid]
    res = evaluate(case.reference_map(), case)
    assert res.score == pytest.approx(100.0), [s.messages for s in res.sections]
    assert res.passed


def test_mapa_vacio_saca_muy_poco():
    case = CASES["taburetes"]
    res = evaluate(VSMMap(params=copy.deepcopy(case.params)), case)
    assert res.score < 15 and not res.passed


def test_error_de_unidades_se_penaliza():
    case = CASES["farma"]
    m = case.reference_map()
    # el estudiante confunde piezas/hora con segundos: Blisteado con TC=400
    for n in m.nodes.values():
        if n.name == "Blisteado":
            n.cycle_time_s = 400
    res = evaluate(m, case)
    assert 55 < res.score < 90
    txt = " ".join(t for s in res.sections for _, t in s.messages)
    assert "Blisteado" in txt and "tiempo de ciclo" in txt


def test_falta_un_inventario_baja_lead_time():
    case = CASES["taburetes"]
    m = case.reference_map()
    inv = max(m.nodes_of("inventory"), key=lambda n: n.quantity)   # 9000 = PT
    m.remove_node(inv.id)
    res = evaluate(m, case)
    assert res.score < 100
    assert res.user_metrics.lead_time_days < 19


def test_nombres_con_tildes_y_mayusculas():
    case = CASES["taburetes"]
    m = case.reference_map()
    for n in m.nodes.values():
        if n.name == "Expedición":
            n.name = "EXPEDICION"
    assert evaluate(m, case).score == pytest.approx(100.0)


@pytest.mark.parametrize("level", LEVELS)
def test_generador_consistente(level):
    for seed in (1, 7, 42, 2026, 99999):
        c = generate_case(seed, level)
        assert generate_case(seed, level).title == c.title            # reproducible
        assert get_case(c.id).title == c.title                       # recuperable por id
        ref = c.reference_map()
        m = compute_metrics(ref)
        assert m.takt_time_s > 0 and m.lead_time_days > 0
        assert len(m.processes_over_takt) >= 1                       # hay algo que mejorar
        assert evaluate(ref, c).score == pytest.approx(100.0)
        assert "<table" in brief_html(c)
