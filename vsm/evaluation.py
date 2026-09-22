"""Motor de evaluación (reglas / experto determinístico) del mapa del estudiante.

Compara el mapa del usuario contra el mapa de referencia del caso. Sin PyQt5.

Puntaje (100):
  20  Flujo de material: proveedor, cliente, flechas, camino continuo, tipo de flecha (push/FIFO/pull)
  10  Flujos de información: cada flujo esperado con el tipo correcto (electrónico / manual / teléfono)
  15  Procesos completos (10) + símbolos especiales (5: transportes, supermercado, FIFO, celdas,
      compartidos, buffers, base de datos, Kanban…). Si el caso no usa símbolos especiales, los 15 son de procesos.
  30  Exactitud de los datos (tiempos, C/O, disponibilidad, operarios, inventarios, tránsitos, capacidades)
  25  Métricas (takt, tiempo VA, lead time, PCE, cuello de botella y procesos sobre el takt)

La tolerancia depende del nivel (Junior 8 % … Negro 1 %).
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from .case_model import (Case, LEVEL_INFO, BASE_KINDS, special_counts, key_label, _role_name)
from .engine import Metrics, compute_metrics
from .models import (VSMMap, Process, Inventory, Transport, MATERIAL_CONNS, INFO_CONNS, CONN_LABELS,
                     PROCESS_KINDS, INVENTORY_KINDS)

LEVEL_TOL = {k: v["tol"] for k, v in LEVEL_INFO.items()}
PASS_SCORE = 75.0
MATCH_THRESHOLD = 0.6


@dataclass
class Section:
    name: str
    max: float
    got: float = 0.0
    messages: List[Tuple[Optional[bool], str]] = field(default_factory=list)  # (ok, texto)

    def ok(self, text: str):
        self.messages.append((True, text))

    def bad(self, text: str):
        self.messages.append((False, text))

    def info(self, text: str):
        self.messages.append((None, text))


@dataclass
class EvaluationResult:
    score: float
    rating: str
    passed: bool
    sections: List[Section]
    user_metrics: Metrics
    ref_metrics: Metrics


# ---------------------------------------------------------------- utilidades
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def name_similarity(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _rel_err(u: float, r: float) -> float:
    if r == 0:
        return 0.0 if u == 0 else 1.0
    return abs(u - r) / abs(r)


def _close(u: float, r: float, rel_tol: float, abs_tol: float = 0.0) -> bool:
    return abs(u - r) <= max(abs_tol, rel_tol * abs(r)) + 1e-9


def _match_processes(user: VSMMap, ref: VSMMap) -> Dict[str, Optional[Process]]:
    """Empareja cada proceso de referencia con el proceso del usuario más parecido."""
    user_procs = [n for n in user.nodes.values() if isinstance(n, Process)]
    used = set()
    out: Dict[str, Optional[Process]] = {}
    for rp in [n for n in ref.nodes.values() if isinstance(n, Process)]:
        best, best_s = None, 0.0
        for up in user_procs:
            if up.id in used:
                continue
            sc = name_similarity(up.name, rp.name)
            if sc > best_s:
                best, best_s = up, sc
        if best is not None and best_s >= MATCH_THRESHOLD:
            used.add(best.id)
            out[rp.id] = best
        else:
            out[rp.id] = None
    return out


# ---------------------------------------------------------------- 1. flujo de material (20)
def _eval_material(user: VSMMap, ref: VSMMap) -> Section:
    sec = Section("Flujo de material", 20)
    got = 0.0
    sups, cuss = user.nodes_of("supplier"), user.nodes_of("customer")
    if sups:
        got += 3
        sec.ok("Proveedor presente.")
    else:
        sec.bad("Falta el proveedor (arriba a la izquierda).")
    if cuss:
        got += 3
        sec.ok("Cliente presente.")
    else:
        sec.bad("Falta el cliente (arriba a la derecha).")

    chain_kinds = {"supplier", "customer", "transport"} | set(PROCESS_KINDS) | set(INVENTORY_KINDS)
    ref_mat = [c for c in ref.connections if c.kind in MATERIAL_CONNS]
    expected = len(ref_mat)
    valid = [c for c in user.connections
             if c.kind in MATERIAL_CONNS
             and user.nodes[c.source].kind in chain_kinds and user.nodes[c.target].kind in chain_kinds]
    ratio = min(1.0, len(valid) / expected) if expected else 0.0
    got += 5 * ratio
    if ratio >= 1.0:
        sec.ok("Flechas de material completas entre los elementos del flujo.")
    else:
        sec.bad(f"Tienes {len(valid)} flecha(s) de material y el flujo necesita al menos {expected}.")

    reachable = False
    if sups and cuss:
        adj: Dict[str, List[str]] = {}
        for c in valid:
            adj.setdefault(c.source, []).append(c.target)
        targets = {c.id for c in cuss}
        seen, stack = set(), [s.id for s in sups]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adj.get(cur, []))
        reachable = bool(seen & targets)
    if reachable:
        got += 4
        sec.ok("Hay un camino de material continuo de proveedor a cliente.")
    else:
        sec.bad("No hay un camino de material continuo (con la flecha en el sentido correcto) "
                "entre proveedor y cliente.")

    # tipo de flecha: push / FIFO / pull
    ref_k = Counter(c.kind for c in ref_mat)
    usr_k = Counter(c.kind for c in valid)
    matched = sum(min(usr_k[k], n) for k, n in ref_k.items())
    got += 5 * (matched / expected if expected else 0.0)
    if matched >= expected:
        sec.ok("Los tipos de flecha de material (push / FIFO / pull) coinciden.")
    else:
        for k, n in ref_k.items():
            if usr_k[k] < n:
                sec.bad(f"Faltan {n - usr_k[k]} flecha(s) de tipo «{CONN_LABELS[k]}» "
                        f"(revisa dónde el flujo es de empuje y dónde es jalado o FIFO).")
    sec.got = got
    return sec


# ---------------------------------------------------------------- 2. información (10)
def _roles(vm: VSMMap, pairs: Dict[str, Optional[Process]]) -> Dict[str, list]:
    return {"customer": vm.nodes_of("customer")[:1], "supplier": vm.nodes_of("supplier")[:1],
            "control": vm.nodes_of("control")[:1], "erp": vm.nodes_of("database")[:1],
            "procs": vm.nodes_of(*PROCESS_KINDS)}


def _pair_score(user: VSMMap, a, b, kind: str) -> float:
    conns = [c for c in user.connections if c.kind in INFO_CONNS
             and {c.source, c.target} == {a.id, b.id}]
    if any(c.kind == kind for c in conns):
        return 1.0
    return 0.5 if conns else 0.0


def _eval_info(user: VSMMap, case: Case, pairs: Dict[str, Optional[Process]]) -> Section:
    sec = Section("Flujos de información", 10)
    links = case.info_links
    roles = _roles(user, pairs)
    ref_proc_ids = list(pairs)
    if not roles["control"]:
        sec.bad("Falta el símbolo de planificación / control de la producción y sus flujos de información.")
        return sec
    per = 10.0 / len(links)
    total = 0.0
    for src, dst, kind, desc in links:
        label = f"«{_role_name(case, src)} → {_role_name(case, dst)}»"
        if "procs" in (src, dst):
            other = src if dst == "procs" else dst
            base = roles[other]
            if not base:
                score = 0.0
            else:
                # cuenta solo procesos de referencia emparejados
                scores = []
                for rid in ref_proc_ids:
                    up = pairs[rid]
                    scores.append(_pair_score(user, base[0], up, kind) if up is not None else 0.0)
                score = sum(scores) / len(scores) if scores else 0.0
        else:
            a, b = roles[src], roles[dst]
            score = _pair_score(user, a[0], b[0], kind) if a and b else 0.0
        total += per * score
        if score >= 0.999:
            sec.ok(f"Flujo {label} correcto.")
        elif score > 0:
            sec.bad(f"Flujo {label}: existe pero revisa el tipo de flecha (manual, electrónica o teléfono) "
                    f"según el enunciado: «{desc}».")
        else:
            sec.bad(f"Falta el flujo de información {label}: «{desc}».")
    sec.got = total
    return sec


# ---------------------------------------------------------------- 3. procesos y símbolos (15)
def _eval_processes(user: VSMMap, ref: VSMMap, pairs: Dict[str, Optional[Process]], max_pts: float) -> Section:
    sec = Section("Procesos completos", max_pts)
    n = len(pairs)
    found = sum(1 for v in pairs.values() if v is not None)
    got = max_pts * found / n if n else 0.0
    for rid, up in pairs.items():
        if up is None:
            sec.bad(f"No encontré el proceso «{ref.nodes[rid].name}».")
    if found == n:
        sec.ok("Están todos los procesos del enunciado.")
    n_user = len(user.nodes_of(*PROCESS_KINDS))
    extra = max(0, n_user - found)
    if extra:
        pen = min(5.0, float(extra))
        got = max(0.0, got - pen)
        sec.bad(f"Tienes {extra} proceso(s) que no corresponden al enunciado (−{pen:g} pts).")
    sec.got = got
    return sec


def _eval_symbols(user: VSMMap, ref: VSMMap) -> Optional[Section]:
    exp = special_counts(ref)
    if not exp:
        return None
    sec = Section("Símbolos especiales", 5)
    have = special_counts(user)
    total = sum(exp.values())
    matched = sum(min(have[k], n) for k, n in exp.items())
    sec.got = 5.0 * matched / total
    for k, n in exp.items():
        if have[k] < n:
            sec.bad(f"Falta {n - have[k]} × «{key_label(k)}» (¿algún elemento del enunciado se dibuja con "
                    f"otro símbolo?).")
    if matched == total:
        sec.ok("Usaste los símbolos especiales que pedía el caso.")
    return sec


# ---------------------------------------------------------------- 4. datos (30)
def _eval_data(user: VSMMap, ref: VSMMap, pairs: Dict[str, Optional[Process]], tol: float) -> Section:
    """Cada campo tiene un peso: el tiempo de ciclo y la disponibilidad pesan más
    porque determinan el cuello de botella y el tiempo de valor agregado."""
    sec = Section("Exactitud de los datos", 30)
    total = 0.0
    right = 0.0
    fields_ = [  # (atributo, etiqueta, tol. relativa, tol. absoluta, peso)
        ("cycle_time_s", "tiempo de ciclo", tol, 0.0, 3.0),
        ("uptime_pct", "disponibilidad", 0.0, 1.0, 2.0),
        ("changeover_s", "tiempo de cambio (C/O)", tol, 0.0, 1.0),
        ("operators", "operarios", 0.0, 0.0, 1.0),
        ("shifts", "turnos", 0.0, 0.0, 1.0),
    ]
    for rid, up in pairs.items():
        rp: Process = ref.nodes[rid]  # type: ignore[assignment]
        for attr, label, rel, ab, w in fields_:
            total += w
            if up is not None and _close(getattr(up, attr), getattr(rp, attr), rel, ab):
                right += w
            elif up is not None:
                sec.bad(f"{rp.name}: el {label} no coincide con el enunciado "
                        f"(tienes {getattr(up, attr):g}). Revisa unidades y conversiones.")

    # inventarios (cualquier tipo): emparejamiento voraz por cantidad (peso 2)
    ref_inv = [n for n in ref.nodes.values() if isinstance(n, Inventory)]
    free = [n.quantity for n in user.nodes.values() if isinstance(n, Inventory)]
    missing = 0
    for rn in ref_inv:
        total += 2.0
        hit = next((u for u in free if _close(u, rn.quantity, tol)), None)
        if hit is not None:
            free.remove(hit)
            right += 2.0
        else:
            missing += 1
    if missing:
        sec.bad(f"{missing} inventario(s) del enunciado no aparecen con la cantidad correcta "
                f"(recuerda convertir «días de demanda» o «pallets» a unidades).")

    # transportes con tiempo en tránsito (peso 2)
    ref_tr = [n for n in ref.nodes.values() if isinstance(n, Transport) and n.transit_days > 0]
    free_t = [n.transit_days for n in user.nodes.values() if isinstance(n, Transport)]
    miss_t = 0
    for rn in ref_tr:
        total += 2.0
        hit = next((u for u in free_t if _close(u, rn.transit_days, tol)), None)
        if hit is not None:
            free_t.remove(hit)
            right += 2.0
        else:
            miss_t += 1
    if miss_t:
        sec.bad(f"{miss_t} transporte(s) sin el tiempo en tránsito correcto.")

    # capacidad de carriles FIFO (peso 1)
    ref_f = [n for n in ref.nodes.values() if n.kind == "fifo_lane"]
    free_f = [n.capacity for n in user.nodes.values() if n.kind == "fifo_lane"]
    miss_f = 0
    for rn in ref_f:
        total += 1.0
        hit = next((u for u in free_f if _close(u, rn.capacity, tol)), None)
        if hit is not None:
            free_f.remove(hit)
            right += 1.0
        else:
            miss_f += 1
    if miss_f:
        sec.bad(f"{miss_f} carril(es) FIFO sin la capacidad máxima correcta.")

    sec.got = 30.0 * right / total if total else 0.0
    if total and right == total:
        sec.ok("Todos los datos coinciden con el enunciado.")
    return sec


# ---------------------------------------------------------------- 5. métricas (25)
def _eval_metrics(um: Metrics, rm: Metrics, tol: float) -> Section:
    sec = Section("Métricas", 25)
    got = 0.0
    if _close(um.takt_time_s, rm.takt_time_s, 0.01):
        got += 5
        sec.ok(f"Takt Time correcto ({rm.takt_time_s:.1f} s).")
    else:
        sec.bad(f"Tu Takt Time ({um.takt_time_s:.1f} s) no coincide con el esperado. "
                "Revisa demanda diaria, turnos, horas y tiempo no disponible (Archivo → Parámetros del caso).")
    for label, u, r, hint in (
            ("Tiempo de valor agregado", um.va_time_s, rm.va_time_s, "Revisa los tiempos de ciclo (¿unidades?)."),
            ("Lead time", um.lead_time_s, rm.lead_time_s, "Revisa inventarios y tiempos en tránsito."),
            ("PCE", um.pce, rm.pce, "Depende del tiempo VA y del lead time.")):
        e = _rel_err(u, r)
        if e <= tol:
            got += 5
            sec.ok(f"{label} dentro de la tolerancia (±{tol * 100:g} %).")
        elif e <= 3 * tol:
            got += 2.5
            sec.bad(f"{label} cercano pero fuera de la tolerancia (error {e * 100:.1f} %). {hint}")
        else:
            sec.bad(f"{label} muy alejado del esperado (error {e * 100:.0f} %). {hint}")
    if um.bottleneck_name and rm.bottleneck_name and \
            name_similarity(um.bottleneck_name, rm.bottleneck_name) >= MATCH_THRESHOLD:
        got += 3
        sec.ok(f"Cuello de botella identificado: {rm.bottleneck_name}.")
    else:
        sec.bad("El cuello de botella de tu mapa no coincide con el esperado "
                "(usa el tiempo de ciclo efectivo = TC / disponibilidad).")
    if sorted(_norm(p.name) for p in rm.processes_over_takt) == sorted(_norm(p.name) for p in um.processes_over_takt):
        got += 2
        sec.ok("Los procesos que superan el takt coinciden con los esperados.")
    else:
        sec.bad("Los procesos que superan el takt en tu mapa no coinciden con los esperados.")
    sec.got = got
    return sec


def _rating(score: float) -> str:
    if score >= 90:
        return "Excelente — nivel superado"
    if score >= PASS_SCORE:
        return "Aprobado"
    if score >= 50:
        return "En progreso"
    return "Necesita revisión"


def evaluate(user: VSMMap, case: Case) -> EvaluationResult:
    ref = case.reference_map()
    tol = LEVEL_TOL.get(case.level, 0.05)
    um, rm = compute_metrics(user), compute_metrics(ref)
    pairs = _match_processes(user, ref)
    symbols = _eval_symbols(user, ref)
    sections = [
        _eval_material(user, ref),
        _eval_info(user, case, pairs),
        _eval_processes(user, ref, pairs, 10.0 if symbols else 15.0),
    ]
    if symbols:
        sections.append(symbols)
    sections += [_eval_data(user, ref, pairs, tol), _eval_metrics(um, rm, tol)]
    score = round(sum(s.got for s in sections), 1)
    return EvaluationResult(score, _rating(score), score >= PASS_SCORE, sections, um, rm)


# ---------------------------------------------------------------- salida HTML
def analysis_html(case: Case, rm: Metrics) -> str:
    """Análisis de referencia (se muestra después de evaluar): hallazgos y oportunidades de mejora."""
    pce = rm.pce * 100
    waits = sorted((e for e in rm.timeline if e.kind != "process"), key=lambda e: -e.days)[:3]
    over = ", ".join(f"{r.name} ({r.effective_ct_s:.1f} s)" for r in rm.processes_over_takt) or "ninguno"
    out = ["<h3>Análisis de referencia</h3>",
           f"<p>Takt <b>{rm.takt_time_s:.1f} s</b> · Tiempo VA <b>{rm.va_time_s:g} s</b> · "
           f"Lead time <b>{rm.lead_time_days:.2f} días</b> · PCE <b>{pce:.3f} %</b><br>"
           f"Cuello de botella: <b>{rm.bottleneck_name}</b> · Superan el takt: {over}<br>"
           f"El {rm.wait_share * 100:.2f} % del lead time es espera sin valor agregado.</p>"]
    if waits:
        out.append("<p>Mayores esperas: " + "; ".join(f"{e.label} ({e.days:.1f} d)" for e in waits) + ".</p>")
    if case.opportunities:
        out.append("<h4>Oportunidades de mejora (estado futuro)</h4><ul>"
                   + "".join(f"<li>{o}</li>" for o in case.opportunities) + "</ul>")
    return "\n".join(out)


def result_html(res: EvaluationResult, case: Optional[Case] = None) -> str:
    color = "#1e8449" if res.passed else "#b9770e"
    out = [f"<h2>Puntaje: <span style='color:{color}'>{res.score:g} / 100</span></h2>",
           f"<p><b>{res.rating}</b></p>"]
    for s in res.sections:
        out.append(f"<h4>{s.name} — {s.got:.1f} / {s.max:g}</h4><ul>")
        for ok, text in s.messages:
            mark = {True: "<span style='color:#1e8449'>✓</span>",
                    False: "<span style='color:#c0392b'>✗</span>",
                    None: "•"}[ok]
            out.append(f"<li>{mark} {text}</li>")
        out.append("</ul>")
    if case is not None:
        out.append(analysis_html(case, res.ref_metrics))
    return "\n".join(out)
