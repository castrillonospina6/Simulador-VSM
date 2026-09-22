"""Pistas que cuestan puntos. Sin PyQt5.

Cada pista se calcula a partir del mapa de referencia del caso y, una vez revelada, su costo se descuenta
del puntaje de la evaluación (ver progress.py). Las pistas dan información, nunca dibujan el mapa por ti.
El costo crece con lo que revelan: el Takt vale poco; el cuello de botella y el lead time, más.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable, List

from .case_model import Case, special_counts, key_label
from .engine import Metrics, compute_metrics
from .models import VSMMap

INFO_LABELS = {"info_electronic": "electrónico", "info_manual": "manual", "info_phone": "por teléfono"}


@dataclass(frozen=True)
class Hint:
    id: str
    title: str
    cost: int
    build: Callable[[Case, Metrics, VSMMap], str]
    applies: Callable[[Case, Metrics, VSMMap], bool] = lambda case, rm, ref: True


def _takt(case: Case, rm: Metrics, ref: VSMMap) -> str:
    return (f"El Takt Time esperado es <b>{rm.takt_time_s:.1f} s</b>: tiempo disponible por día ÷ demanda diaria "
            f"(con la demanda ya convertida a unidades por día). Si el tuyo es distinto, revisa "
            f"<i>Archivo → Parámetros del caso</i>.")


def _symbols(case: Case, rm: Metrics, ref: VSMMap) -> str:
    items = ", ".join(f"{n} × {key_label(k)}" for k, n in sorted(special_counts(ref).items()))
    return f"Además de proceso, inventario, proveedor, cliente y control, el mapa lleva: <b>{items}</b>."


def _info(case: Case, rm: Metrics, ref: VSMMap) -> str:
    c = Counter(kind for _a, _b, kind, _d in case.info_links)
    items = ", ".join(f"{n} × {INFO_LABELS.get(k, k)}" for k, n in c.items())
    return (f"El caso tiene <b>{len(case.info_links)}</b> flujos de información: {items}. "
            f"Un flujo hacia «cada proceso» se dibuja hacia todos los procesos.")


def _wait(case: Case, rm: Metrics, ref: VSMMap) -> str:
    e = max((t for t in rm.timeline if t.kind != "process"), key=lambda t: t.days)
    return f"La mayor espera del flujo es «{e.label}»: <b>{e.days:.1f} días</b> laborales."


def _bottleneck(case: Case, rm: Metrics, ref: VSMMap) -> str:
    r = next(p for p in rm.process_results if p.node_id == rm.bottleneck_id)
    return (f"El cuello de botella es <b>«{r.name}»</b>: su tiempo de ciclo efectivo (TC ÷ disponibilidad) es "
            f"{r.effective_ct_s:.1f} s frente a un takt de {rm.takt_time_s:.1f} s.")


def _lead(case: Case, rm: Metrics, ref: VSMMap) -> str:
    return (f"Lead time esperado ≈ <b>{rm.lead_time_days:.2f} días</b> laborales; el {rm.wait_share * 100:.1f} % es "
            f"espera. PCE ≈ {rm.pce * 100:.3f} %.")


HINTS = (
    Hint("takt", "Takt Time esperado", 2, _takt),
    Hint("symbols", "Símbolos especiales del caso", 2, _symbols,
         lambda case, rm, ref: bool(special_counts(ref))),
    Hint("info", "Flujos de información", 2, _info, lambda case, rm, ref: bool(case.info_links)),
    Hint("wait", "Mayor espera del flujo", 3, _wait,
         lambda case, rm, ref: any(t.kind != "process" for t in rm.timeline)),
    Hint("bottleneck", "Cuello de botella", 4, _bottleneck, lambda case, rm, ref: bool(rm.bottleneck_id)),
    Hint("lead", "Lead time y PCE esperados", 5, _lead),
)


def _ctx(case: Case):
    ref = case.reference_map()
    return compute_metrics(ref), ref


def available_hints(case: Case) -> List[Hint]:
    rm, ref = _ctx(case)
    return [h for h in HINTS if h.applies(case, rm, ref)]


def hint_text(case: Case, hint_id: str) -> str:
    h = next(h for h in HINTS if h.id == hint_id)
    rm, ref = _ctx(case)
    return h.build(case, rm, ref)


def hints_cost(case: Case, used: Iterable[str]) -> int:
    """Puntos que se descuentan por las pistas usadas (ids desconocidos o no aplicables no cuestan)."""
    used = set(used)
    return sum(h.cost for h in available_hints(case) if h.id in used)
