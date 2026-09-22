"""Calculadoras del estado futuro: número de Kanban y tamaño de supermercado. Sin PyQt5.

Convenciones (las mismas del motor): tiempos en DÍAS LABORALES y demanda en unidades por día.

Kanban (fórmula clásica)
    N = ⌈ D × L × (1 + α) / C ⌉
    D demanda diaria · L tiempo de reposición (desde que sale la tarjeta hasta que el material vuelve al
    supermercado) · α factor de seguridad · C unidades por contenedor.

Supermercado (Rother & Shook: stock de ciclo + buffer + seguridad)
    ciclo     = D × R          lo que se consume entre dos reposiciones (R = intervalo de reposición)
    buffer    = D × días       protege contra picos de demanda
    seguridad = D × días       protege contra problemas internos (paradas, calidad)
    máximo    = ciclo + buffer + seguridad        mínimo = buffer + seguridad
    punto de reposición = D × L + buffer + seguridad   (nivel en que hay que pedir para no llegar por debajo del mínimo)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List


def _ceil(x: float) -> int:
    """Techo tolerante al ruido de coma flotante (1000 × 0.1 × 1.1 / 10 = 11.000000000000002 debe dar 11 tarjetas, no 12)."""
    return int(math.ceil(x - 1e-9))


def hours_to_days(hours: float, day_s: float) -> float:
    """Convierte horas a días laborales usando los segundos disponibles por día del mapa."""
    if day_s <= 0:
        raise ValueError("El tiempo disponible por día es 0: revisa turnos y horas (Archivo → Parámetros del caso).")
    return hours * 3600.0 / day_s


def _check(demand: float, container: float) -> None:
    if demand <= 0:
        raise ValueError("La demanda diaria debe ser mayor que 0.")
    if container <= 0:
        raise ValueError("El tamaño del contenedor debe ser mayor que 0.")


# ---------------------------------------------------------------- Kanban
@dataclass
class KanbanResult:
    cards: int                    # número de tarjetas Kanban
    units_in_loop: float          # cards × contenedor: máximo de unidades circulando en el lazo
    demand_during_lead: float     # D × L
    safety_units: float           # units_in_loop − D × L (incluye el redondeo hacia arriba)
    days_cover: float             # units_in_loop / D
    withdrawals_per_day: float    # contenedores que se consumen por día
    pitch_s: float                # cada cuántos segundos se consume un contenedor (takt × contenedor)


def kanban_cards(demand: float, lead_days: float, container: float, safety_pct: float = 0.0,
                 day_s: float = 0.0) -> KanbanResult:
    _check(demand, container)
    if lead_days < 0 or safety_pct < 0:
        raise ValueError("El tiempo de reposición y el factor de seguridad no pueden ser negativos.")
    need = demand * lead_days
    cards = max(1, _ceil(need * (1 + safety_pct / 100.0) / container))
    units = cards * container
    return KanbanResult(cards, units, need, units - need, units / demand, demand / container,
                        day_s * container / demand if day_s > 0 else 0.0)


# ---------------------------------------------------------------- supermercado
@dataclass
class SupermarketResult:
    cycle: float
    buffer: float
    safety: float
    max_level: float
    min_level: float
    avg_level: float              # mínimo + ciclo / 2: la cantidad "típica" (la que corresponde al lead time)
    reorder_point: float
    days_max: float
    days_avg: float
    locations: int                # contenedores necesarios para el nivel máximo (ubicaciones en la estantería)
    warnings: List[str] = field(default_factory=list)


def supermarket_size(demand: float, container: float, replenish_days: float, lead_days: float,
                     buffer_days: float = 0.0, safety_days: float = 0.0) -> SupermarketResult:
    _check(demand, container)
    if replenish_days <= 0:
        raise ValueError("El intervalo de reposición debe ser mayor que 0.")
    if min(lead_days, buffer_days, safety_days) < 0:
        raise ValueError("Los tiempos no pueden ser negativos.")
    cycle, buffer, safety = demand * replenish_days, demand * buffer_days, demand * safety_days
    mx, mn = cycle + buffer + safety, buffer + safety
    rop = demand * lead_days + mn
    warns: List[str] = []
    if lead_days > replenish_days:
        warns.append("El tiempo de reposición es mayor que el intervalo de reposición: habrá varias reposiciones "
                     "en camino a la vez y el punto de reposición supera el nivel máximo. Revisa si conviene "
                     "reponer con más frecuencia o acortar el tiempo de reposición.")
    return SupermarketResult(cycle, buffer, safety, mx, mn, mn + cycle / 2, rop, mx / demand,
                             (mn + cycle / 2) / demand, max(1, _ceil(mx / container)), warns)
