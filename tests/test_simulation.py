"""Simulación dinámica (SimPy): validación contra casos que se pueden razonar a mano."""
import os

import pytest

pytest.importorskip("simpy")

from vsm.cases import CASES
from vsm.models import VSMMap, CaseParams, make_node
from vsm.simulation import SimConfig, SimulationError, simulate, insights

DET = dict(ct_cv=0.0, demand_cv=0.0, replications=1, days=20, warmup_days=3)


def _line(cts, qtys, uptimes=None):
    """inventario → proceso → inventario … (demanda 900/día, takt 60 s)."""
    m = VSMMap(params=CaseParams(900, 2, 8, 30))
    x = 0
    for i, ct in enumerate(cts):
        inv = make_node("inventory", x, 0); inv.quantity = qtys[i]; inv.name = f"Inv{i}"
        p = make_node("process", x + 100, 0); p.name, p.cycle_time_s = f"P{i + 1}", ct
        p.uptime_pct = (uptimes or [100] * len(cts))[i]
        m.add_node(inv); m.add_node(p)
        x += 200
    last = make_node("inventory", x, 0); last.quantity = qtys[len(cts)]; last.name = "PT"
    m.add_node(last)
    return m


def test_linea_balanceada_deterministica():
    r = simulate(_line([30], [900, 900]), SimConfig(**DET))
    s = r.stations[0]
    assert s.busy == pytest.approx(0.5, abs=0.03) and s.down == 0
    assert s.busy + s.blocked + s.starved + s.idle == pytest.approx(1.0, abs=1e-6)
    assert r.kpi.fill_rate == pytest.approx(1.0) and r.kpi.throughput_day == pytest.approx(900, rel=0.03)


def test_little_coincide_con_el_estatico_si_todo_es_estable():
    m = _line([30], [900, 900])
    r = simulate(m, SimConfig(**DET))
    assert r.kpi.lead_time_days == pytest.approx(2.0, rel=0.06)
    assert r.static_lead_time_days == pytest.approx(2 + 30 / 54000)


def test_cuello_de_botella_bloquea_aguas_arriba_y_agota_el_producto_terminado():
    r = simulate(_line([30, 90], [900, 100, 900]), SimConfig(**DET))
    p1, p2 = r.stations
    assert p2.occupancy > 0.97 and p1.blocked > 0.3          # el lento nunca para; el rápido queda bloqueado
    assert r.kpi.throughput_day == pytest.approx(54000 / 90, rel=0.08)
    assert r.kpi.fill_rate < 0.85
    txt = " ".join(insights(r))
    assert "Bloqueo" in txt and "«P1»" in txt and "Nivel de servicio" in txt


def test_inanicion_aguas_abajo_del_cuello():
    r = simulate(_line([90, 30], [900, 100, 900]), SimConfig(**DET))
    assert r.stations[1].starved > 0.4                       # el rápido espera lo que el lento le entrega
    assert any("Inanición" in t for t in insights(r))


def test_fallas_reproducen_la_disponibilidad():
    r = simulate(_line([50], [900, 900], [80]), SimConfig(ct_cv=0.0, demand_cv=0.0, replications=5, days=40))
    s = r.stations[0]
    assert s.down / (s.busy + s.down) == pytest.approx(0.20, abs=0.04)


def test_reproducible_y_semilla_distinta_cambia():
    m = _line([50, 55], [900, 300, 900], [90, 90])
    a = simulate(m, SimConfig(replications=2, seed=7)).kpi
    b = simulate(m, SimConfig(replications=2, seed=7)).kpi
    c = simulate(m, SimConfig(replications=2, seed=8)).kpi
    assert a == b and a != c


def test_intervalo_de_confianza():
    r = simulate(_line([50], [900, 900], [90]), SimConfig(replications=4))
    assert r.ci["throughput_day"] >= 0
    assert simulate(_line([50], [900, 900]), SimConfig(replications=1)).ci["fill_rate"] == 0


def test_transporte_y_traspaso_directo():
    m = _line([30, 30], [900, 0, 900])
    inv_mid = [n for n in m.nodes.values() if n.name == "Inv1"][0]
    m.remove_node(inv_mid.id)                                # P1 → P2 sin inventario
    t = make_node("transport", 50, 0); t.transit_days = 1; t.name = "Camión"
    m.add_node(t)
    r = simulate(m, SimConfig(**DET))
    tr = next(b for b in r.buffers if b.kind == "transport")
    assert tr.avg_u == pytest.approx(900, rel=0.1) and tr.wait_days == pytest.approx(1, rel=0.1)
    assert any(b.kind == "implicit" for b in r.buffers)


def test_errores_legibles():
    with pytest.raises(SimulationError):
        simulate(VSMMap(), SimConfig())
    m = _line([30], [900, 900]); m.params.customer_demand = 0
    with pytest.raises(SimulationError):
        simulate(m, SimConfig())
    with pytest.raises(SimulationError):
        simulate(_line([30], [900, 900]), SimConfig(days=0))
    with pytest.raises(SimulationError):
        simulate(_line([30], [900, 900]), SimConfig(release="x"))


def test_empuje_puro_llena_los_buffers():
    m = _line([30, 60], [900, 900, 900])
    a = simulate(m, SimConfig(**DET, release="demand"))
    b = simulate(m, SimConfig(**DET, release="unlimited"))
    assert b.stations[0].starved <= a.stations[0].starved


@pytest.mark.parametrize("cid", list(CASES))
def test_todos_los_casos_simulan_y_los_estados_suman_uno(cid):
    c = CASES[cid]
    r = simulate(c.reference_map(), SimConfig(days=6, warmup_days=1, replications=1))
    assert 0 <= r.kpi.fill_rate <= 1 and r.kpi.throughput_day >= 0
    assert len(r.stations) == len(c.processes)
    for s in r.stations:
        assert s.busy + s.down + s.blocked + s.starved + s.idle == pytest.approx(1.0, abs=0.02)
        assert min(s.busy, s.down, s.blocked, s.starved, s.idle) >= -1e-9
    assert insights(r) and r.series


# ---------------------------------------------------------------- supermercado pull (Kanban)
from vsm.simulation import supermarket_checks, sweep_supermarket
from vsm.persistence import save_map, load_map


def _pull_line(max_sm, min_sm=60, mttr_s=1800):
    """Inv → P1 (80 % disp., repara 30 min) → Supermercado → P2 → PT. Demanda 900/día."""
    m = VSMMap(params=CaseParams(900, 2, 8, 30))
    x = 0
    for kind, v in (("inventory", 900), ("process", ("P1", 30, 80)), ("supermarket", 300),
                    ("process", ("P2", 50, 100)), ("inventory", 900)):
        n = make_node(kind, x, 0); x += 150
        if kind == "process":
            n.name, n.cycle_time_s, n.uptime_pct = v
        else:
            n.quantity = v
        m.add_node(n)
    p1 = m.nodes_of("process")[0]
    p1.mttr_s = mttr_s
    sm = m.nodes_of("supermarket")[0]
    sm.max_level, sm.min_level = max_sm, min_sm
    return m, sm


def test_supermercado_pequeno_no_aguanta_y_uno_holgado_si():
    cfg = SimConfig(replications=5, days=30)
    chk = {mx: supermarket_checks(simulate(_pull_line(mx)[0], cfg))[0] for mx in (30, 800)}
    assert chk[30].verdict == "no" and chk[30].empty_pct > 0.05 and "Sube el nivel máximo" in chk[30].advice
    assert chk[800].verdict == "ok" and chk[800].min_obs_u > 0
    assert any("NO aguanta" in t for t in insights(simulate(_pull_line(30)[0], cfg)))


def test_kanban_limita_el_nivel_y_el_proceso_repositor_espera_la_senal():
    r = simulate(_pull_line(400)[0], SimConfig(**{**DET, "replications": 1}, release="unlimited"))
    sm = next(b for b in r.buffers if b.is_super)
    assert sm.max_u <= sm.capacity_u + 1e-9 and sm.capacity_u == pytest.approx(400, abs=15)
    p1 = r.stations[0]
    assert p1.idle > 0.3 and p1.blocked == pytest.approx(0, abs=1e-6)     # espera tarjeta, no está bloqueado
    assert p1.throughput_day == pytest.approx(900, rel=0.05)              # produce lo que se consume


def test_barrido_de_tamanos_mejora_al_crecer_el_supermercado():
    m, sm = _pull_line(200)
    pts = sweep_supermarket(m, sm.id, SimConfig(days=30), factors=(0.25, 1.0, 4.0))
    assert [p.max_u for p in pts] == sorted(p.max_u for p in pts)
    assert pts[0].empty_pct > pts[-1].empty_pct and pts[-1].verdict == "ok"
    with pytest.raises(SimulationError):
        sweep_supermarket(m, next(iter(m.nodes)), SimConfig())


def test_mttr_por_proceso_mantiene_la_disponibilidad():
    for mttr in (300, 3600):
        m = _line([50], [900, 900], [80]); next(iter(m.nodes_of("process"))).mttr_s = mttr
        r = simulate(m, SimConfig(ct_cv=0, demand_cv=0, replications=6, days=60))
        s = r.stations[0]
        assert s.down / (s.busy + s.down) == pytest.approx(0.20, abs=0.05)


def test_fotogramas_para_animar():
    m, sm = _pull_line(400)
    r = simulate(m, SimConfig(days=8, warmup_days=1, replications=1, sample_points=100))
    assert len(r.frames) == pytest.approx(100, abs=2) and r.frames[0].day == 0
    p1 = m.nodes_of("process")[0]
    assert {f.state[p1.id] for f in r.frames} <= {"busy", "down", "blocked", "starved", "idle"}
    assert all(f.level[sm.id] <= r.node_cap[sm.id] + 1e-9 for f in r.frames)
    assert r.node_min[sm.id] == pytest.approx(60, abs=15)
    assert r.frames[-1].done[p1.id] >= r.frames[0].done[p1.id]


def test_supermercado_y_mttr_se_guardan_con_el_mapa(tmp_path):
    m, sm = _pull_line(400, 80, 900)
    f = tmp_path / "m.vsm.json"
    save_map(m, str(f))
    back = load_map(str(f))
    assert back.nodes[sm.id].max_level == 400 and back.nodes[sm.id].min_level == 80
    assert back.nodes_of("process")[0].mttr_s == 900
