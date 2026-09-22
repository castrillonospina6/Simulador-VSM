"""Auditoría de la biblioteca de casos (23 casos, 6 niveles)."""
import copy

import pytest

from vsm.cases import (CASES, CASES_BY_LEVEL, LEVELS, LEVEL_INFO, brief_html, problems, get_case,
                       generate_case, special_counts, key_label)
from vsm.engine import compute_metrics
from vsm.evaluation import evaluate, result_html, LEVEL_TOL, name_similarity
from vsm.models import VSMMap, CONN_KINDS, MATERIAL_CONNS, INFO_CONNS


def test_biblioteca_completa():
    assert len(CASES) == 23
    assert list(CASES_BY_LEVEL) == list(LEVELS)
    counts = {lvl: len(cs) for lvl, cs in CASES_BY_LEVEL.items()}
    assert counts == {"Junior": 3, "Blanco": 4, "Amarillo": 5, "Verde": 5, "Rojo": 3, "Negro": 3}
    assert len({c.title for c in CASES.values()}) == 23
    assert len({c.sector for c in CASES.values()}) >= 14          # variedad de sectores


def test_tolerancia_decrece_con_el_nivel():
    tols = [LEVEL_TOL[l] for l in LEVELS]
    assert tols == sorted(tols, reverse=True)


@pytest.mark.parametrize("cid", list(CASES))
def test_caso_es_consistente(cid):
    c = CASES[cid]
    assert problems(c) == []                                   # los datos del enunciado son exactos
    ref = c.reference_map()
    m = compute_metrics(ref)
    assert m.takt_time_s > 0 and m.lead_time_days > 0
    assert len(m.processes_over_takt) == 1                     # un cuello claro por caso
    assert c.objectives and c.opportunities
    html = brief_html(c)
    assert c.title in html and "<table" in html and "Flujos de información" in html
    # toda flecha de la referencia conecta nodos existentes y de tipos válidos
    assert all(cn.source in ref.nodes and cn.target in ref.nodes and cn.kind in CONN_KINDS
               for cn in ref.connections)
    assert any(cn.kind in INFO_CONNS for cn in ref.connections)
    assert get_case(cid) is c


@pytest.mark.parametrize("cid", list(CASES))
def test_referencia_saca_100_y_tiene_analisis(cid):
    c = CASES[cid]
    res = evaluate(c.reference_map(), c)
    assert res.score == pytest.approx(100.0), [(s.name, s.messages) for s in res.sections]
    html = result_html(res, c)
    assert "Análisis de referencia" in html and "Oportunidades de mejora" in html


def test_pistas_de_simbolos_solo_en_niveles_bajos():
    assert "Pista" in brief_html(CASES["cafe"])
    assert "Pista" not in brief_html(CASES["autopartes"])


def test_los_niveles_altos_usan_simbolos_especiales():
    for c in CASES_BY_LEVEL["Negro"] + CASES_BY_LEVEL["Rojo"]:
        keys = special_counts(c.reference_map())
        assert len(keys) >= 3, (c.id, keys)
    used = set()
    for c in CASES.values():
        used |= set(special_counts(c.reference_map()))
    for needed in ("transport:camion", "transport:avion", "transport:barco", "supermarket", "fifo_lane",
                   "buffer_point", "safety_stock", "safety_point", "shared_process", "work_cell", "database",
                   "kanban_withdrawal", "kanban_signal"):
        assert needed in used, needed


def test_todos_los_tipos_de_flecha_aparecen_en_referencias():
    kinds = set()
    for c in CASES.values():
        kinds |= {cn.kind for cn in c.reference_map().connections}
    assert {"push", "pull", "info_manual", "info_electronic", "info_phone"} <= kinds


# ---------------------------------------------------------------- errores típicos del estudiante
def test_confundir_supermercado_con_inventario_penaliza_simbolos_y_flechas():
    c = CASES["jugos"]
    m = c.reference_map()
    sm = next(n for n in m.nodes.values() if n.kind == "supermarket")
    # lo dibuja como inventario normal
    from vsm.models import make_node
    inv = make_node("inventory", sm.x, sm.y); inv.quantity = sm.quantity; inv.name = sm.name
    m.remove_node(sm.id); m.add_node(inv)
    res = evaluate(m, c)
    txt = " ".join(t for s in res.sections for _, t in s.messages)
    assert res.score < 100 and "Supermercado" in txt


def test_flecha_de_informacion_con_tipo_equivocado_da_credito_parcial():
    c = CASES["panaderia"]
    m = c.reference_map()
    for cn in m.connections:
        if cn.kind == "info_manual":
            cn.kind = "info_phone"
    res = evaluate(m, c)
    info = next(s for s in res.sections if s.name == "Flujos de información")
    assert 0 < info.got < info.max


def test_sin_flujos_de_informacion_pierde_esos_puntos():
    c = CASES["panaderia"]
    m = c.reference_map()
    m.connections = [cn for cn in m.connections if cn.kind not in INFO_CONNS]
    res = evaluate(m, c)
    info = next(s for s in res.sections if s.name == "Flujos de información")
    assert info.got == 0 and res.score == pytest.approx(90.0)


def test_olvidar_el_transporte_penaliza_dato_y_simbolo():
    c = CASES["calzado"]
    m = c.reference_map()
    tr = next(n for n in m.nodes.values() if n.kind == "transport")
    m.remove_node(tr.id)
    res = evaluate(m, c)
    assert res.score < 100
    assert any("Transporte" in t for s in res.sections for _, t in s.messages)


def test_oee_en_vez_de_disponibilidad_se_detecta():
    c = CASES["cerveza"]
    m = c.reference_map()
    env = next(n for n in m.nodes.values() if n.name == "Envasado")
    env.uptime_pct = 88 * 0.93 * 0.98        # el estudiante usa el OEE completo (~80 %)
    res = evaluate(m, c)
    assert res.score < 100
    txt = " ".join(t for s in res.sections for _, t in s.messages)
    assert "Envasado" in txt and "disponibilidad" in txt


def test_demanda_semanal_mal_convertida_arruina_takt():
    c = CASES["jeans"]
    m = c.reference_map()
    m.params.customer_demand = 5000       # no dividió entre 5 días
    res = evaluate(m, c)
    assert res.score < 85
    assert any("Takt" in t for s in res.sections for _, t in s.messages)


def test_mapa_vacio_saca_muy_poco():
    for c in CASES.values():
        res = evaluate(VSMMap(params=copy.deepcopy(c.params)), c)
        assert res.score < 12 and not res.passed


def test_nombres_similares_con_tildes_y_prefijos():
    assert name_similarity("Inspeccion optica AOI", "Inspección óptica (AOI)") == 1.0 or \
        name_similarity("Inspeccion optica AOI", "Inspección óptica (AOI)") > 0.8
    assert key_label("transport:avion") == "Transporte · avión"
