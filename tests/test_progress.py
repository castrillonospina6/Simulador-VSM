"""Cinturones, XP, pistas con costo y caso del día."""
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from vsm.cases import CASES, generate_case
from vsm.hints import available_hints, hint_text, hints_cost, HINTS
from vsm.progress import (BELTS, LEVEL_XP, Progress, adjust_result, attempt_html, belt_for, daily_case,
                          max_case_xp, next_belt, xp_for_score)
from vsm.evaluation import evaluate


# ---------------------------------------------------------------- cinturones y XP
def test_cinturones_coinciden_con_los_niveles_y_crecen():
    from vsm.cases import LEVELS
    assert [b.name for b in BELTS] == list(LEVELS)
    assert [b.min_xp for b in BELTS] == sorted(b.min_xp for b in BELTS) and BELTS[0].min_xp == 0
    assert belt_for(0).name == "Junior" and belt_for(59).name == "Junior" and belt_for(60).name == "Blanco"
    assert belt_for(10_000).name == "Negro" and next_belt(10_000) is None and next_belt(0).name == "Blanco"


def test_xp_por_puntaje():
    c = CASES["panaderia"]                                    # Junior: base 20
    assert xp_for_score(c, 74.9) == 0
    assert xp_for_score(c, 80) == 16
    assert xp_for_score(c, 100) == 25 == max_case_xp(c)       # 20 + 25 % de bono por ≥ 90
    assert xp_for_score(generate_case(1, "Junior"), 100) == 12          # aleatorio: mitad (10 + 2)
    assert xp_for_score(generate_case(1, "Negro"), 80) == 40


def test_el_total_posible_permite_llegar_al_cinturon_negro():
    total = sum(max_case_xp(c) for c in CASES.values())
    assert total > BELTS[-1].min_xp


def test_solo_se_gana_la_mejora_sobre_la_mejor_marca(tmp_path):
    p, c = Progress(str(tmp_path / "p.json")), CASES["taburetes"]     # Blanco: base 30
    a = p.record(c, 80)
    assert a.passed and a.base_xp == 24 and p.xp == 24
    assert p.record(c, 80).total == 0 and p.record(c, 70).total == 0 and p.xp == 24
    b = p.record(c, 100)
    assert b.base_xp == 38 - 24 and p.xp == 38
    assert p.entry(c.id)["attempts"] == 4 and p.entry(c.id)["best_net"] == 100


def test_reprobado_no_da_xp_y_no_contar_no_toca_nada(tmp_path):
    p, c = Progress(str(tmp_path / "p.json")), CASES["cafe"]
    assert p.record(c, 60).total == 0 and not p.record(c, 60).passed
    before = dict(p.cases)
    a = p.record(c, 100, count=False)
    assert a.net == 100 and not a.counted and a.total == 0 and p.xp == 0 and p.cases == before


def test_las_pistas_restan_puntos_y_pueden_quitar_el_aprobado(tmp_path):
    p, c = Progress(str(tmp_path / "p.json")), CASES["taburetes"]
    a = p.record(c, 100, penalty=6)
    assert a.net == 94 and a.base_xp == round(30 * .94) + round(30 * .25)
    b = p.record(CASES["cafe"], 78, penalty=6)
    assert b.net == 72 and not b.passed
    assert p.record(c, 3, penalty=10).net == 0                # nunca negativo


def test_subir_de_cinturon(tmp_path):
    p = Progress(str(tmp_path / "p.json"))
    p.xp = 55
    a = p.record(CASES["taburetes"], 100)
    assert a.promoted and a.belt_before.name == "Junior" and a.belt_after.name == "Blanco"
    assert "Cinturón Blanco" in attempt_html(a)


# ---------------------------------------------------------------- caso del día
def test_caso_del_dia_determinista_y_sin_repetir_en_23_dias():
    d0 = date(2026, 9, 21)
    assert daily_case(d0) is daily_case(d0)
    assert len({daily_case(d0 + timedelta(days=i)).id for i in range(23)}) == 23


def test_bono_del_dia_y_racha(tmp_path):
    p = Progress(str(tmp_path / "p.json"))
    d1 = date(2026, 9, 21)
    c1 = daily_case(d1)
    a = p.record(c1, 100, today=d1)
    earned = a.base_xp
    assert a.is_daily and a.daily_bonus == round(earned * .5) and a.streak == 1 and a.streak_bonus == 5
    assert p.xp == earned + a.daily_bonus + 5 and p.daily_done(d1)
    again = p.record(c1, 100, today=d1)                       # el bono es una vez al día
    assert not again.is_daily and again.total == 0

    d2 = d1 + timedelta(days=1)
    b = p.record(daily_case(d2), 100, today=d2)
    assert b.streak == 2 and b.streak_bonus == 10 and p.current_streak(d2) == 2
    d4 = d2 + timedelta(days=2)                               # se saltó un día: la racha vuelve a 1
    assert p.current_streak(d4) == 0
    assert p.record(daily_case(d4), 100, today=d4).streak == 1 and p.daily["best_streak"] == 2


def test_el_dia_no_cuenta_si_no_aprueba(tmp_path):
    p, d = Progress(str(tmp_path / "p.json")), date(2026, 9, 21)
    a = p.record(daily_case(d), 50, today=d)
    assert not a.is_daily and not p.daily_done(d)


# ---------------------------------------------------------------- persistencia
def test_guardar_y_cargar(tmp_path):
    f = str(tmp_path / "sub" / "p.json")
    p = Progress(f)
    p.record(CASES["taburetes"], 100)
    q = Progress(f)
    assert q.xp == p.xp > 0 and q.entry("taburetes")["passed"]
    q.reset()
    assert Progress(f).xp == 0


def test_archivo_danado_no_rompe(tmp_path):
    f = tmp_path / "p.json"
    f.write_text("{esto no es json", encoding="utf-8")
    p = Progress(str(f))
    assert p.xp == 0 and (tmp_path / "p.json.bak").exists()
    p.record(CASES["taburetes"], 100)                         # y se puede volver a guardar
    assert Progress(str(f)).xp == p.xp


def test_resumen_por_nivel(tmp_path):
    p = Progress(str(tmp_path / "p.json"))
    p.record(CASES["panaderia"], 100)
    row = {r[0]: r for r in p.level_summary()}
    assert row["Junior"][1:3] == (1, 3) and row["Junior"][3] == 25 and row["Negro"][1] == 0


# ---------------------------------------------------------------- pistas
@pytest.mark.parametrize("cid", list(CASES))
def test_cada_caso_tiene_pistas_utiles(cid):
    c = CASES[cid]
    hs = available_hints(c)
    ids = {h.id for h in hs}
    assert {"takt", "bottleneck", "lead", "info", "wait"} <= ids
    assert all(hint_text(c, h.id) for h in hs)
    assert hints_cost(c, ids) == sum(h.cost for h in hs) <= 18
    assert hints_cost(c, []) == 0 and hints_cost(c, ["no-existe"]) == 0


def test_pistas_del_caso_taburetes():
    c = CASES["taburetes"]
    assert "60.0 s" in hint_text(c, "takt")
    assert "Pintura" in hint_text(c, "bottleneck")
    assert "19." in hint_text(c, "lead")
    assert "Transporte · camión" in hint_text(c, "symbols")


def test_pista_de_simbolos_solo_si_hay_especiales():
    assert "symbols" not in {h.id for h in available_hints(CASES["panaderia"])}


def test_costo_creciente_con_lo_que_revela():
    cost = {h.id: h.cost for h in HINTS}
    assert cost["takt"] < cost["bottleneck"] < cost["lead"]


def test_ajuste_del_resultado_de_evaluacion():
    c = CASES["cafe"]
    raw = evaluate(c.reference_map(), c)
    adj = adjust_result(raw, 70.0)
    assert raw.score == 100 and adj.score == 70 and not adj.passed and raw.passed
