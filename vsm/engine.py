"""Motor de cálculo del VSM: Takt Time, Lead Time, PCE y cuello de botella.

Sin dependencias de PyQt5. Alcance del MVP: el flujo se interpreta como una
secuencia LINEAL, ordenando procesos, inventarios y transportes de izquierda
a derecha según su posición X.

Convenciones
------------
* Los tiempos de espera se miden en DÍAS LABORALES: días de inventario =
  cantidad / demanda diaria. Para sumarlos con los tiempos de proceso (s) se
  convierten con los segundos disponibles por día.
* Tiempo de ciclo efectivo = TC / disponibilidad. Un proceso "supera el takt"
  si su tiempo de ciclo efectivo es mayor que el Takt Time.
* PCE = tiempo de valor agregado / lead time total.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .models import VSMMap, FLOW_KINDS, Process, Inventory, Transport


@dataclass
class ProcessResult:
    node_id: str
    name: str
    cycle_time_s: float
    effective_ct_s: float
    exceeds_takt: bool


@dataclass
class TimelineEntry:
    kind: str          # 'wait' | 'transport' | 'process'
    label: str
    seconds: float     # segundos laborales
    days: float        # días laborales
    node_id: str


@dataclass
class Metrics:
    takt_time_s: float = 0.0
    va_time_s: float = 0.0
    lead_time_s: float = 0.0
    lead_time_days: float = 0.0
    wait_time_s: float = 0.0
    pce: float = 0.0
    bottleneck_id: Optional[str] = None
    bottleneck_name: Optional[str] = None
    process_results: List[ProcessResult] = field(default_factory=list)
    timeline: List[TimelineEntry] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def wait_share(self) -> float:
        return self.wait_time_s / self.lead_time_s if self.lead_time_s > 0 else 0.0

    @property
    def processes_over_takt(self) -> List[ProcessResult]:
        return [p for p in self.process_results if p.exceeds_takt]


def ordered_flow(vmap: VSMMap):
    """Nodos del flujo de material, ordenados de izquierda a derecha."""
    nodes = [n for n in vmap.nodes.values() if n.kind in FLOW_KINDS]
    return sorted(nodes, key=lambda n: (n.x, n.y))


def compute_metrics(vmap: VSMMap) -> Metrics:
    p = vmap.params
    m = Metrics()
    m.takt_time_s = p.takt_time_s
    day_s = p.available_seconds_per_day
    demand = p.customer_demand

    if demand <= 0:
        m.warnings.append("La demanda del cliente debe ser mayor que 0 "
                          "(Archivo → Parámetros del caso).")
    if day_s <= 0:
        m.warnings.append("El tiempo disponible por día es 0: revisa turnos y horas.")

    flow = ordered_flow(vmap)
    if not any(isinstance(n, Process) for n in flow):
        m.warnings.append("Aún no hay procesos en el mapa.")

    for node in flow:
        if isinstance(node, Process):
            if node.uptime_pct > 0:
                eff = node.cycle_time_s / (node.uptime_pct / 100.0)
            else:
                eff = node.cycle_time_s
                m.warnings.append(f"'{node.name}' tiene disponibilidad 0 %.")
            over = m.takt_time_s > 0 and eff > m.takt_time_s + 1e-9
            m.process_results.append(ProcessResult(node.id, node.name, node.cycle_time_s, eff, over))
            m.va_time_s += node.cycle_time_s
            m.timeline.append(TimelineEntry("process", node.name, node.cycle_time_s,
                                            node.cycle_time_s / day_s if day_s > 0 else 0.0,
                                            node.id))
        elif isinstance(node, Inventory):
            days = node.quantity / demand if demand > 0 else 0.0
            secs = days * day_s
            m.wait_time_s += secs
            m.timeline.append(TimelineEntry("wait", node.name, secs, days, node.id))
        elif isinstance(node, Transport):
            days = max(0.0, node.transit_days)
            secs = days * day_s
            m.wait_time_s += secs
            m.timeline.append(TimelineEntry("transport", node.name, secs, days, node.id))

    m.lead_time_s = m.va_time_s + m.wait_time_s
    m.lead_time_days = m.lead_time_s / day_s if day_s > 0 else 0.0
    m.pce = m.va_time_s / m.lead_time_s if m.lead_time_s > 0 else 0.0

    if m.process_results:
        b = max(m.process_results, key=lambda r: r.effective_ct_s)
        m.bottleneck_id, m.bottleneck_name = b.node_id, b.name

    return m
