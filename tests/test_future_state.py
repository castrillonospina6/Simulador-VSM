"""Calculadora de Kanban / supermercado y vista económica (estado futuro, etapa 5)."""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from vsm.cases import CASES
from vsm.economics import analyze, scale_inventories, compare, summary_text, money
from vsm.models import VSMMap, CaseParams, EconParams, make_node
from vsm.persistence import save_map, load_map
from vsm.pull_calc import kanban_cards, supermarket_size, hours_to_days


# ---------------------------------------------------------------- Kanban
def test_kanban_formula_clasica():
    r = kanban_cards(demand=1000, lead_days=0.5, container=50, safety_pct=10, day_s=54000)
    assert r.cards == 11                                    # 1000 × 0.5 × 1.1 / 50 = 11
    assert r.units_in_loop == 550 and r.demand_during_lead == 500 and r.safety_units == 50
    assert r.withdrawals_per_day == 20 and r.days_cover == pytest.approx(0.55)
    assert r.pitch_s == pytest.approx(2700)                 # takt (54 s) × 50 u


def test_kanban_ruido_de_coma_flotante_no_suma_una_tarjeta():
    assert kanban_cards(1000, 0.1, 10, 10).cards == 11      # 11.000000000000002 en coma flotante
    assert kanban_cards(12000, 0.5, 10, 10).cards == 660


def test_kanban_redondea_hacia_arriba_y_minimo_una_tarjeta():
    assert kanban_cards(1000, 0.51, 50).cards == 11         # 10.2 → 11
    assert kanban_cards(1000, 0.0, 50).cards == 1


@pytest.mark.parametrize("args", [(0, 1, 50), (1000, 1, 0), (1000, -1, 50)])
def test_kanban_datos_invalidos(args):
    with pytest.raises(ValueError):
        kanban_cards(*args)


def test_horas_a_dias_laborales():
    assert hours_to_days(7.5, 54000) == pytest.approx(0.5)  # 2 turnos de 7.5 h = 15 h/día
    with pytest.raises(ValueError):
        hours_to_days(4, 0)


# ---------------------------------------------------------------- supermercado
def test_supermercado_ciclo_buffer_seguridad():
    s = supermarket_size(demand=1000, container=50, replenish_days=1, lead_days=0.5, buffer_days=0.5,
                         safety_days=0.25)
    assert (s.cycle, s.buffer, s.safety) == (1000, 500, 250)
    assert s.max_level == 1750 and s.min_level == 750 and s.avg_level == 1250
    assert s.reorder_point == 1250                          # D × L + mínimo
    assert s.days_max == pytest.approx(1.75) and s.locations == 35 and s.warnings == []


def test_supermercado_avisa_si_la_reposicion_tarda_mas_que_el_intervalo():
    s = supermarket_size(1000, 50, replenish_days=0.5, lead_days=1, buffer_days=0, safety_days=0)
    assert s.warnings and s.reorder_point > s.max_level


def test_supermercado_datos_invalidos():
    with pytest.raises(ValueError):
        supermarket_size(1000, 50, 0, 1)


# ---------------------------------------------------------------- economía
def _mapa_simple(qty_before=900, qty_after=900):
    m = VSMMap(params=CaseParams(900, 2, 8, 30))
    a, p, b = make_node("inventory", 0, 0), make_node("process", 100, 0), make_node("inventory", 200, 0)
    a.quantity, b.quantity, p.cycle_time_s = qty_before, qty_after, 60
    for n in (a, p, b):
        m.add_node(n)
    return m


def test_capital_y_costo_de_mantener_a_mano():
    m = _mapa_simple()
    r = analyze(m)                                          # MP 10, conversión 5, tasas 12 + 5 + 3 = 20 %
    assert [l.unit_value for l in r.lines] == [10, 15]      # antes del proceso: solo MP; después: MP + conversión
    assert r.capital_total == pytest.approx(900 * 10 + 900 * 15)
    assert r.holding_year == pytest.approx(22500 * 0.20)
    assert r.turns == pytest.approx(900 * 250 * 15 / 22500)
    assert r.holding_per_unit == pytest.approx(4500 / (900 * 250))
    assert r.lead_time_days == pytest.approx(2 + 60 / 54000)


def test_transito_paga_capital_pero_no_bodega():
    m = _mapa_simple()
    t = make_node("transport", 300, 0)
    t.transit_days = 2
    m.add_node(t)
    r = analyze(m)
    assert r.capital_transit == pytest.approx(1800 * 15) and r.capital_inventory == pytest.approx(22500)
    assert r.cost_storage_year == pytest.approx(22500 * 0.05)          # el tránsito no entra
    m.econ.include_transit = False
    assert analyze(m).capital_transit == 0


def test_conversion_se_reparte_por_tiempo_de_ciclo():
    m = VSMMap(params=CaseParams(900, 2, 8, 30))
    for i, (kind, ct) in enumerate((("process", 30), ("inventory", 0), ("process", 90), ("inventory", 0))):
        n = make_node(kind, i * 100, 0)
        if kind == "process":
            n.cycle_time_s = ct
        else:
            n.quantity = 900
        m.add_node(n)
    r = analyze(m)
    assert r.lines[0].unit_value == pytest.approx(10 + 5 * 30 / 120)
    assert r.lines[1].unit_value == pytest.approx(15)


def test_escenario_reducir_inventarios_y_recuperacion():
    m = _mapa_simple()
    cur = analyze(m)
    fut = analyze(scale_inventories(m, 0.5))
    assert m.nodes[next(iter(m.nodes))].quantity == 900                 # el original no se toca
    c = compare(cur, fut, investment=5625)
    assert c.capital_freed == pytest.approx(11250) and c.annual_saving == pytest.approx(2250)
    assert c.payback_months == pytest.approx(30) and c.payback_net_months == 0
    assert compare(cur, fut, investment=22500).payback_net_months == pytest.approx((22500 - 11250) / 2250 * 12)
    assert compare(cur, fut).payback_months is None                     # sin inversión no hay recuperación
    assert compare(cur, cur, investment=1000).payback_months is None    # sin ahorro no hay recuperación


def test_resumen_menciona_cifras_clave():
    m = _mapa_simple()
    cur, fut = analyze(m), analyze(scale_inventories(m, 0.5))
    txt = summary_text(cur, compare(cur, fut, 5625))
    for frag in (money(22500), money(11250), money(2250), "30.0 meses", "ya cubre"):
        assert frag in txt
    assert "Estado propuesto" not in summary_text(cur)


def test_mapa_vacio_y_demanda_cero_no_rompen():
    assert analyze(VSMMap()).capital_total == 0 and analyze(VSMMap()).turns == 0
    m = _mapa_simple()
    m.params.customer_demand = 0
    r = analyze(m)
    assert r.capital_total > 0 and r.holding_per_unit == 0


def test_supuestos_se_guardan_con_el_mapa(tmp_path):
    m = CASES["taburetes"].reference_map()
    m.econ.material_cost, m.econ.capital_rate, m.econ.include_transit = 42.0, 18.0, False
    f = tmp_path / "x.vsm.json"
    save_map(m, str(f))
    back = load_map(str(f))
    assert (back.econ.material_cost, back.econ.capital_rate, back.econ.include_transit) == (42.0, 18.0, False)
    d = json.loads(f.read_text(encoding="utf-8"))
    del d["econ"]                                                        # archivo anterior a esta versión
    assert VSMMap.from_dict(d).econ == EconParams()


def test_referencia_de_todos_los_casos_es_analizable():
    for c in CASES.values():
        r = analyze(c.reference_map())
        assert r.capital_total > 0 and r.turns > 0
