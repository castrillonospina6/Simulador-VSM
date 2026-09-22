"""Vista económica del VSM: convierte inventario y lead time en capital de trabajo y costo de mantener. Sin PyQt5.

Idea (etapa 5 del libro: justificar la mejora):
  * Cada inventario (o mercancía en tránsito) inmoviliza dinero = unidades × valor unitario.
  * El valor unitario crece a lo largo del flujo: materia prima + costo de conversión acumulado. El costo de
    conversión se reparte entre los procesos en proporción a su tiempo de ciclo (si todos valen 0, por igual).
  * Costo de mantener por año = capital × costo de capital  +  inventario × (almacenaje + obsolescencia).
    La mercancía en tránsito paga capital pero no bodega.
  * No se incluye el material que está dentro de las máquinas (el tiempo de ciclo): es despreciable frente a la espera.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .engine import ordered_flow, compute_metrics
from .models import EconParams, VSMMap, Process, Inventory, Transport


def money(x: float) -> str:
    return f"$ {x:,.0f}"


@dataclass
class EconLine:
    node_id: str
    label: str
    kind: str            # 'inventory' | 'transport'
    units: float
    days: float
    unit_value: float

    @property
    def capital(self) -> float:
        return self.units * self.unit_value


@dataclass
class EconResult:
    econ: EconParams
    demand: float
    lead_time_days: float
    lines: List[EconLine] = field(default_factory=list)

    @property
    def capital_total(self) -> float:
        return sum(l.capital for l in self.lines)

    @property
    def capital_transit(self) -> float:
        return sum(l.capital for l in self.lines if l.kind == "transport")

    @property
    def capital_inventory(self) -> float:
        return self.capital_total - self.capital_transit

    @property
    def cost_capital_year(self) -> float:
        return self.capital_total * self.econ.capital_rate / 100.0

    @property
    def cost_storage_year(self) -> float:
        return self.capital_inventory * self.econ.storage_rate / 100.0

    @property
    def cost_obsolescence_year(self) -> float:
        return self.capital_inventory * self.econ.obsolescence_rate / 100.0

    @property
    def holding_year(self) -> float:
        return self.cost_capital_year + self.cost_storage_year + self.cost_obsolescence_year

    @property
    def units_sold_year(self) -> float:
        return self.demand * self.econ.work_days_per_year

    @property
    def holding_per_unit(self) -> float:
        u = self.units_sold_year
        return self.holding_year / u if u > 0 else 0.0

    @property
    def turns(self) -> float:
        """Rotación = costo de lo vendido en el año / capital inmovilizado."""
        cap = self.capital_total
        return self.units_sold_year * self.econ.unit_cost / cap if cap > 0 else 0.0


def analyze(vmap: VSMMap, econ: Optional[EconParams] = None) -> EconResult:
    e = econ or vmap.econ
    demand = vmap.params.customer_demand
    flow = ordered_flow(vmap)
    procs = [n for n in flow if isinstance(n, Process)]
    total_ct = sum(n.cycle_time_s for n in procs)
    done_ct, done_n = 0.0, 0
    res = EconResult(e, demand, compute_metrics(vmap).lead_time_days)
    for node in flow:
        if isinstance(node, Process):
            done_ct += node.cycle_time_s
            done_n += 1
            continue
        frac = done_ct / total_ct if total_ct > 0 else (done_n / len(procs) if procs else 0.0)
        value = e.material_cost + e.conversion_cost * frac
        if isinstance(node, Inventory):
            units = node.quantity
            days = units / demand if demand > 0 else 0.0
            res.lines.append(EconLine(node.id, node.name, "inventory", units, days, value))
        elif isinstance(node, Transport) and e.include_transit:
            days = max(0.0, node.transit_days)
            res.lines.append(EconLine(node.id, node.name, "transport", demand * days, days, value))
    return res


def scale_inventories(vmap: VSMMap, factor: float) -> VSMMap:
    """Copia del mapa con todos los inventarios multiplicados por `factor` (escenario «reducir X %»)."""
    clone = VSMMap.from_dict(vmap.to_dict())
    for n in clone.nodes.values():
        if isinstance(n, Inventory):
            n.quantity *= factor
    return clone


# ---------------------------------------------------------------- justificar la mejora
@dataclass
class EconComparison:
    current: EconResult
    future: EconResult
    investment: float = 0.0

    @property
    def capital_freed(self) -> float:
        return self.current.capital_total - self.future.capital_total

    @property
    def annual_saving(self) -> float:
        return self.current.holding_year - self.future.holding_year

    @property
    def lead_time_saved_days(self) -> float:
        return self.current.lead_time_days - self.future.lead_time_days

    @property
    def payback_months(self) -> Optional[float]:
        """Meses para recuperar la inversión solo con el ahorro anual recurrente."""
        if self.investment > 0 and self.annual_saving > 0:
            return self.investment / self.annual_saving * 12
        return None

    @property
    def payback_net_months(self) -> Optional[float]:
        """Igual, pero descontando el efectivo liberado (que entra una sola vez). 0 = el efectivo liberado ya la paga."""
        if self.investment > 0 and self.annual_saving > 0:
            return max(0.0, self.investment - self.capital_freed) / self.annual_saving * 12
        return None


def compare(current: EconResult, future: EconResult, investment: float = 0.0) -> EconComparison:
    return EconComparison(current, future, max(0.0, investment))


def summary_text(cur: EconResult, comp: Optional[EconComparison] = None) -> str:
    """Texto listo para pegar en un informe."""
    out = [f"Situación actual: el flujo tiene {cur.lead_time_days:.1f} días de lead time y mantiene "
           f"{money(cur.capital_total)} inmovilizados en inventario y mercancía en tránsito. Mantenerlos cuesta "
           f"{money(cur.holding_year)} al año, unos {cur.holding_per_unit:,.2f} por unidad vendida."]
    if comp is not None:
        f = comp.future
        out.append(f"Estado propuesto: el lead time pasa de {cur.lead_time_days:.1f} a {f.lead_time_days:.1f} días "
                   f"({f.lead_time_days - cur.lead_time_days:+.1f}) y el capital inmovilizado de "
                   f"{money(cur.capital_total)} a {money(f.capital_total)}.")
        if comp.annual_saving > 0 or comp.capital_freed > 0:
            out.append(f"Se liberan {money(comp.capital_freed)} de efectivo (una sola vez) y se ahorran "
                       f"{money(comp.annual_saving)} al año en costo de mantener.")
        else:
            out.append("El estado propuesto no libera capital ni reduce el costo de mantener.")
        if comp.investment > 0:
            pb, pn = comp.payback_months, comp.payback_net_months
            if pb is None:
                out.append(f"Con una inversión de {money(comp.investment)} no hay recuperación: el ahorro anual "
                           f"no es positivo.")
            else:
                extra = ("el efectivo liberado ya cubre la inversión" if pn == 0
                         else f"{pn:.1f} meses si se cuenta el efectivo liberado")
                out.append(f"Con una inversión de {money(comp.investment)}, se recupera en {pb:.1f} meses solo "
                           f"con el ahorro anual; {extra}.")
    return "\n".join(out)
