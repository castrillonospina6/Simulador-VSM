"""Generador paramétrico de casos (reproducible por semilla).

La complejidad crece con el nivel: nº de procesos, unidades mezcladas, símbolos
especiales (transportes, FIFO, supermercado, compartidos, celdas, buffers), OEE,
demanda semanal/mensual. El takt se calcula para que exista al menos un proceso
por encima del takt.
"""
from __future__ import annotations

import random
from typing import List, Optional

from .case_model import (Case, ProcSpec, InvSpec, TransSpec, LEVELS, STD_INFO, Step, problems)
from .engine import compute_metrics
from .models import CaseParams

_TEMPLATES = {
    "Alimentos": dict(company="Panificadora El Trigal", product="paquete de galletas", unit="paquete",
                      procs=["Mezclado", "Laminado y corte", "Horneado", "Enfriamiento", "Empaque", "Paletizado",
                             "Inspección", "Encajado"]),
    "Electrónica": dict(company="ElectroNova", product="tarjeta controladora", unit="tarjeta",
                        procs=["Impresión de pasta", "Colocación SMT", "Reflujo", "Inspección óptica",
                               "Prueba funcional", "Ensamble en carcasa", "Etiquetado", "Empaque"]),
    "Textil": dict(company="Confecciones Aurora", product="camisa polo", unit="camisa",
                   procs=["Tendido y corte", "Costura", "Bordado", "Lavado", "Planchado", "Control de calidad",
                          "Etiquetado", "Empaque"]),
    "Muebles": dict(company="Muebles del Valle", product="silla de comedor", unit="silla",
                    procs=["Corte de madera", "Ensamble", "Lijado", "Pintura", "Tapizado", "Control de calidad",
                           "Empaque", "Paletizado"]),
    "Plásticos": dict(company="Inyectados del Norte", product="tapa plástica", unit="caja",
                      procs=["Inyección", "Rebabado", "Decorado", "Ensamble", "Inspección", "Empaque",
                             "Paletizado", "Etiquetado"]),
}
_CT_S = {  # divisores de 3600 (para "piezas/hora" exacto)
    "Junior": [10, 12, 15, 20, 24, 25, 30, 36, 40, 45, 50, 60],
    "Blanco": [10, 12, 15, 20, 24, 25, 30, 36, 40, 45, 50, 60],
    "Amarillo": [10, 12, 15, 18, 20, 24, 30, 36, 40, 45, 50, 60, 72, 75, 90],
    "Verde": [12, 15, 18, 20, 24, 30, 36, 40, 45, 48, 50, 60, 72, 75, 80, 90, 100, 120],
    "Rojo": [12, 15, 18, 20, 24, 30, 36, 40, 45, 48, 50, 60, 72, 75, 80, 90, 100, 120],
    "Negro": [12, 15, 18, 20, 24, 30, 36, 40, 45, 48, 50, 60, 72, 75, 80, 90, 100, 120],
}
_INV_DAYS = [0.5, 1, 1.5, 2, 3, 4, 5, 7]
_N_PROCS = {"Junior": 3, "Blanco": 4, "Amarillo": 5, "Verde": 6, "Rojo": 7, "Negro": 8}


def generate_case(seed: Optional[int] = None, level: str = "Blanco") -> Case:
    """Genera un caso aleatorio pero reproducible (misma semilla y nivel → mismo caso)."""
    level = level if level in LEVELS else "Blanco"
    if seed is None:
        seed = random.randint(1000, 999999)
    rng = random.Random(seed)
    lv = LEVELS.index(level)          # 0 = Junior … 5 = Negro

    sector = rng.choice(list(_TEMPLATES))
    t = _TEMPLATES[sector]
    n = min(_N_PROCS[level], len(t["procs"]))
    names = [t["procs"][i] for i in sorted(rng.sample(range(len(t["procs"])), n))]

    shifts = rng.choice([1, 2, 2, 3])
    params = CaseParams(shifts=shifts, hours_per_shift=8.0, unavailable_min_per_shift=rng.choice([30, 45, 60]))

    mixed = lv >= 2                    # Amarillo+: unidades mezcladas
    hard = lv >= 3                     # Verde+: lotes, paradas
    kinds = ["process"] * n
    if lv >= 3:
        kinds[rng.randrange(n)] = "shared_process"
    if lv >= 4:
        kinds[rng.choice([i for i in range(n) if kinds[i] == "process"])] = "work_cell"
    if lv >= 5:
        idx = [i for i in range(n) if kinds[i] == "process"]
        if idx:
            kinds[rng.choice(idx)] = "shared_process"

    specs: List[ProcSpec] = []
    for name, kind in zip(names, kinds):
        ct = rng.choice(_CT_S[level])
        style, batch = "s", 1
        if mixed:
            style = rng.choice(["s", "min", "pph"] + (["batch"] if hard else []))
            if style == "batch":
                batch = rng.choice([10, 20, 50])
        up_style = "pct"
        if hard:
            up_style = rng.choice(["pct", "downtime"] + (["oee"] if lv >= 4 else []))
        uptime = rng.choice([80, 85, 88, 90, 92, 95, 97, 99])
        perf, quality = (rng.choice([90, 92, 94, 96]), rng.choice([96, 97, 98, 99])) if up_style == "oee" else (100, 100)
        s = ProcSpec(name=name, ct=ct, co=rng.choice([0, 0, 60, 120, 300, 600, 900]), uptime=uptime,
                     operators=rng.randint(1, 4), shifts=rng.randint(1, shifts), ct_style=style, batch=batch,
                     co_style=rng.choice(["s", "min"]) if mixed else "s", up_style=up_style,
                     perf=perf, quality=quality, kind=kind)
        if s.ct_style == "batch" and (s.ct * s.batch) % 6 != 0:
            s.ct_style = "s"
        if s.ct_style == "min" and s.ct % 6 != 0:
            s.ct_style = "s"
        specs.append(s)

    eff_max = max(s.ct / (s.uptime / 100) for s in specs)
    target_takt = eff_max * rng.uniform(0.85, 0.95)
    demand = max(10, int(round(params.available_seconds_per_day / target_takt / 10.0)) * 10)
    params.customer_demand = demand

    # ---- inventarios / transportes / símbolos especiales
    inv_style = lambda: "days" if (mixed and rng.random() < 0.5) else "units"
    special_between = {}                 # índice del inventario -> tipo especial
    if lv >= 2 and n >= 3:
        special_between[rng.randrange(1, n)] = rng.choice(["fifo_lane", "supermarket"])
    if lv >= 4 and n >= 4:
        j = rng.randrange(1, n)
        special_between.setdefault(j, "buffer_point")

    steps: List[Step] = []
    if lv >= 1:
        steps.append(TransSpec("Camión — proveedor", rng.choice([0.5, 1, 1]), "camion"))
    for i, s in enumerate(specs):
        days = rng.choice(_INV_DAYS)
        qty = round(days * demand)
        sp = special_between.get(i)
        if i == 0:
            steps.append(InvSpec(qty, "Materia prima", inv_style()))
        elif sp == "fifo_lane":
            q = max(10, round(qty * 0.1 / 10) * 10)
            steps.append(InvSpec(q, "Carril FIFO", kind="fifo_lane", capacity=q * 2))
        elif sp == "supermarket":
            steps.append(InvSpec(qty, "Supermercado", inv_style(), kind="supermarket"))
        elif sp == "buffer_point":
            steps.append(InvSpec(qty, "Buffer", inv_style(), kind="buffer_point"))
        else:
            steps.append(InvSpec(qty, "", inv_style()))
        steps.append(s)
    last_days = rng.choice(_INV_DAYS)
    last_kind = "safety_stock" if lv >= 5 else "inventory"
    steps.append(InvSpec(round(last_days * demand), "Producto terminado", inv_style(), kind=last_kind))
    if lv >= 3:
        steps.append(TransSpec("Barco — exportación" if lv >= 5 else "Camión — cliente",
                               rng.choice([2, 4, 6]) if lv >= 5 else 1, "barco" if lv >= 5 else "camion"))
    elif lv >= 2:
        steps.append(TransSpec("Camión — cliente", 1, "camion"))
    if lv >= 5:
        steps[0] = TransSpec("Avión — insumos", 3, "avion")

    # pallets (Rojo+) para el primer inventario
    if lv >= 4:
        first = next(s for s in steps if isinstance(s, InvSpec))
        first.style, first.pack = "pallets", 10 * rng.choice([1, 2, 5])
        first.qty = max(first.pack, round(first.qty / first.pack) * first.pack)

    # demanda semanal/mensual (Verde+)
    demand_text = ""
    pl = t["unit"] + "s"
    if lv == 3:
        demand_text = f"{demand * 5:,} {pl} por semana (5 días laborales)"
    elif lv >= 4:
        demand_text = f"{demand * 22:,} {pl} por mes (22 días laborales)"

    extras = []
    info = list(STD_INFO)
    if lv >= 2:
        info.insert(1, ("customer", "control", "info_phone", "el cliente ajusta pedidos urgentes por teléfono"))
    if lv >= 4:
        extras.append(("database", "ERP", {}, "top"))
        info.append(("control", "erp", "info_electronic", "el ERP consolida órdenes y planes"))

    notes = []
    if lv >= 3:
        notes = ["El área de mantenimiento y la bodega de repuestos no participan en el flujo.",
                 "Existe un turno de sábado que no se considera parte de la jornada normal."]

    case = Case(
        id=f"gen-{level.lower()}-{seed}",
        title=f"{t['company']} — {t['product'].capitalize()} (caso #{seed})",
        sector=sector, level=level,
        story=(f"<b>{t['company']}</b> fabrica {t['product']}s. La gerencia quiere entender por qué el tiempo total "
               f"desde que llega la materia prima hasta que se despacha es tan largo comparado con el tiempo que "
               f"realmente se trabaja el producto."),
        params=params, steps=steps, unit=t["unit"], demand_text=demand_text, info_links=info, extras=extras,
        supplier="Proveedor principal", supplier_note="entrega semanal", notes=notes,
        objectives=["Practicar la normalización de datos y la construcción del mapa del estado actual."])

    ref = compute_metrics(case.reference_map())
    over = ref.processes_over_takt
    case.opportunities = [
        f"{ref.bottleneck_name} es el cuello de botella: revisar disponibilidad, cambios y balance de operarios.",
        f"El {ref.wait_share * 100:.1f} % del lead time es espera: atacar los inventarios más grandes.",
        "Evaluar flujo continuo (FIFO) o supermercado pull entre los procesos más desbalanceados."]
    assert not problems(case), problems(case)
    return case
