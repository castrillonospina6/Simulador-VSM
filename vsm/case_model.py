"""Modelo de casos (v2): especificaciones, mapa de referencia, enunciado y validación.

Sin dependencias de PyQt5.

Un caso describe una empresa "como la describiría ella": los datos del enunciado
pueden venir en distintas unidades (segundos, minutos, piezas/hora, minutos por
lote; disponibilidad, paradas u OEE; inventario en unidades, días o pallets;
demanda por día, semana o mes). El estudiante debe normalizarlos. La solución de
referencia se construye desde los datos "limpios" y es contra lo que se evalúa.

Los pasos del flujo pueden ser procesos (normales, compartidos o celdas de
trabajo), inventarios (inventario, supermercado, carril FIFO, buffers) y
transportes (camión, avión, barco). Los flujos de información y los símbolos
extra (base de datos, Kanban…) también forman parte del caso.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple, Union

from .models import CaseParams, VSMMap, make_node, KIND_LABELS, PROCESS_KINDS, INVENTORY_KINDS

LEVELS = ("Junior", "Blanco", "Amarillo", "Verde", "Rojo", "Negro")

LEVEL_INFO = {
    "Junior":   dict(tol=0.08, stars=1, blurb="3 procesos, datos limpios en segundos y símbolos básicos."),
    "Blanco":   dict(tol=0.05, stars=2, blurb="4 procesos, datos limpios; se suman transportes y buffers."),
    "Amarillo": dict(tol=0.03, stars=3, blurb="Unidades mezcladas, supermercados, carriles FIFO y Kanban."),
    "Verde":    dict(tol=0.02, stars=4, blurb="Procesos compartidos y celdas, lotes, paradas, demanda semanal."),
    "Rojo":     dict(tol=0.02, stars=5, blurb="Sistemas pull en el estado actual, OEE, demanda mensual, pallets."),
    "Negro":    dict(tol=0.01, stars=6, blurb="Flujos complejos: 7+ procesos, avión/barco, buffers, datos trampa."),
}

BASE_KINDS = {"process", "inventory", "supplier", "customer", "control"}
ROLES = ("customer", "supplier", "control", "procs", "erp")

# Tamaño (ancho, alto) de cada símbolo, para maquetar el mapa de referencia
_SIZE = {"process": (165, 118), "shared_process": (165, 118), "work_cell": (165, 150),
         "inventory": (80, 60), "supermarket": (64, 64), "fifo_lane": (136, 36),
         "safety_stock": (40, 84), "buffer_point": (40, 70), "safety_point": (40, 70),
         "transport": (90, 40)}
_GAP = 55.0


# =============================================================================
# Especificaciones de pasos
# =============================================================================
@dataclass
class ProcSpec:
    name: str
    ct: float                 # s por unidad
    co: float = 0.0           # s
    uptime: float = 100.0     # % (disponibilidad)
    operators: int = 1
    shifts: int = 1
    ct_style: str = "s"       # 's' | 'min' | 'pph' | 'batch'
    batch: int = 1            # tamaño de lote si ct_style == 'batch'
    co_style: str = "s"       # 's' | 'min'
    up_style: str = "pct"     # 'pct' | 'downtime' | 'oee'
    perf: float = 100.0       # rendimiento (%) — solo para up_style == 'oee'
    quality: float = 100.0    # calidad (%) — solo para up_style == 'oee'
    kind: str = "process"     # process | shared_process | work_cell
    flow_out: Optional[str] = None


@dataclass
class InvSpec:
    qty: float
    label: str = ""
    style: str = "units"      # 'units' | 'days' | 'pallets'
    kind: str = "inventory"   # inventory | supermarket | fifo_lane | safety_stock | buffer_point | safety_point
    pack: int = 1             # unidades por pallet (style == 'pallets')
    capacity: float = 0.0     # capacidad máx. (kind == 'fifo_lane')
    flow_out: Optional[str] = None


@dataclass
class TransSpec:
    name: str
    days: float
    mode: str = "camion"      # camion | avion | barco
    note: str = ""
    flow_out: Optional[str] = None


Step = Union[ProcSpec, InvSpec, TransSpec]

# (origen, destino, tipo de flecha, descripción para el enunciado)
InfoLink = Tuple[str, str, str, str]
# (tipo de nodo, nombre, atributos, ancla: 'top' o índice del paso sobre el que se coloca)
Extra = Tuple[str, str, dict, Union[str, int]]

STD_INFO: List[InfoLink] = [
    ("customer", "control", "info_electronic", "pronóstico semanal por correo electrónico"),
    ("control", "supplier", "info_electronic", "pedidos de compra por correo electrónico"),
    ("control", "procs", "info_manual", "programación semanal impresa que se entrega a cada proceso"),
]


@dataclass
class Case:
    id: str
    title: str
    sector: str
    level: str
    story: str
    params: CaseParams
    steps: List[Step]
    unit: str = "pieza"
    plural: str = ""
    supplier: str = "Proveedor"
    customer: str = "Cliente"
    supplier_note: str = ""
    control_name: str = ""
    demand_text: str = ""                                  # sustituye la línea estándar de demanda
    info_links: List[InfoLink] = field(default_factory=lambda: list(STD_INFO))
    extras: List[Extra] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)         # datos irrelevantes (distractores)
    objectives: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)  # análisis de mejora (se muestra al evaluar)

    # ---- consultas
    @property
    def pl(self) -> str:
        return self.plural or self.unit + "s"

    @property
    def processes(self) -> List[ProcSpec]:
        return [s for s in self.steps if isinstance(s, ProcSpec)]

    @property
    def tolerance(self) -> float:
        return LEVEL_INFO[self.level]["tol"]

    # ---- mapa de referencia (solución)
    def reference_map(self) -> VSMMap:
        m = VSMMap(params=replace(self.params), case_id=self.id)
        chain_y = 260.0
        center = chain_y + 68
        x = 0.0
        chain = []
        for s in self.steps:
            n = _step_node(s)
            w, h = _SIZE[n.kind]
            n.x, n.y = x, center - h / 2
            x += w + _GAP
            m.add_node(n)
            chain.append(n)
        end_x = x - _GAP

        sup = make_node("supplier", 0.0, 30.0)
        sup.name, sup.note = self.supplier, self.supplier_note
        cus = make_node("customer", max(200.0, end_x - 130.0), 30.0)
        cus.name, cus.note = self.customer, ""
        ctl = make_node("control", 0.0, 30.0)
        if self.control_name:
            ctl.name = self.control_name
        ctl.x = (sup.x + 130 + cus.x) / 2 - 95
        for n in (sup, cus, ctl):
            m.add_node(n)

        extra_nodes = []
        top_i = 0
        anchored: Counter = Counter()
        for kind, name, attrs, anchor in self.extras:
            n = make_node(kind)
            n.name = name
            for k, v in attrs.items():
                setattr(n, k, v)
            if anchor == "top":
                n.x, n.y = ctl.x + 235 + top_i * 130, 20.0
                top_i += 1
            else:
                k = anchored[int(anchor)]
                anchored[int(anchor)] += 1
                n.x, n.y = chain[int(anchor)].x - 50 + k * 150, chain_y - 125
            m.add_node(n)
            extra_nodes.append(n)

        # flujo de material
        m.add_connection(sup.id, chain[0].id, "push")
        for s, a, b in zip(self.steps, chain, chain[1:]):
            m.add_connection(a.id, b.id, _flow(s))
        m.add_connection(chain[-1].id, cus.id, _flow(self.steps[-1]))

        # flujos de información
        procs = [n for n in chain if n.kind in PROCESS_KINDS]
        erp = next((n for n in extra_nodes if n.kind == "database"), None)
        roles = {"customer": [cus], "supplier": [sup], "control": [ctl], "procs": procs,
                 "erp": [erp] if erp else []}
        for src, dst, kind, _desc in self.info_links:
            for a in roles[src]:
                for b in roles[dst]:
                    m.add_connection(a.id, b.id, kind)
        return m

    def special_counts(self) -> Counter:
        """Símbolos 'especiales' esperados (todo lo que no es proceso/inventario/proveedor/cliente/control)."""
        return special_counts(self.reference_map())


def _flow(step: Step) -> str:
    if step.flow_out:
        return step.flow_out
    if isinstance(step, InvSpec) and step.kind == "supermarket":
        return "pull"
    return "push"


def _step_node(s: Step):
    if isinstance(s, ProcSpec):
        n = make_node(s.kind)
        n.name, n.cycle_time_s, n.changeover_s = s.name, s.ct, s.co
        n.uptime_pct, n.operators, n.shifts = s.uptime, s.operators, s.shifts
    elif isinstance(s, InvSpec):
        n = make_node(s.kind)
        n.quantity = s.qty
        if s.label:
            n.name = s.label
        if s.kind == "fifo_lane":
            n.capacity = s.capacity or 20.0
    else:
        n = make_node("transport")
        n.name, n.transit_days, n.mode = s.name, s.days, s.mode
    return n


def symbol_key(node) -> str:
    return f"transport:{node.mode}" if node.kind == "transport" else node.kind


def special_counts(vmap: VSMMap) -> Counter:
    return Counter(symbol_key(n) for n in vmap.nodes.values() if n.kind not in BASE_KINDS)


_MODE_LABEL = {"camion": "camión", "avion": "avión", "barco": "barco"}


def key_label(key: str) -> str:
    if key.startswith("transport:"):
        return f"Transporte · {_MODE_LABEL.get(key.split(':')[1], key)}"
    return KIND_LABELS.get(key, key)


# =============================================================================
# Redacción del enunciado
# =============================================================================
def _fmt(x: float) -> str:
    return f"{round(x):,}" if abs(x - round(x)) < 1e-9 else f"{x:,.2f}".rstrip("0").rstrip(".")


def describe_ct(s: ProcSpec, case: Case) -> str:
    if s.ct_style == "min":
        return f"{_fmt(s.ct / 60)} min por {case.unit}"
    if s.ct_style == "pph":
        return f"{_fmt(3600 / s.ct)} {case.pl}/hora"
    if s.ct_style == "batch":
        return f"{_fmt(s.ct * s.batch / 60)} min por lote de {_fmt(s.batch)} {case.pl}"
    return f"{_fmt(s.ct)} s por {case.unit}"


def describe_co(s: ProcSpec) -> str:
    if s.co == 0:
        return "no aplica"
    return f"{_fmt(s.co / 60)} min" if s.co_style == "min" else f"{_fmt(s.co)} s"


def describe_up(s: ProcSpec) -> str:
    if s.up_style == "downtime":
        return f"paradas no planeadas del {_fmt(100 - s.uptime)} %"
    if s.up_style == "oee":
        oee = s.uptime * s.perf * s.quality / 1e4
        return (f"OEE {oee:.1f} % (disponibilidad {_fmt(s.uptime)} %, rendimiento {_fmt(s.perf)} %, "
                f"calidad {_fmt(s.quality)} %)")
    return f"{_fmt(s.uptime)} %"


def describe_inv(case: Case, s: InvSpec) -> str:
    if s.style == "days":
        return f"equivale a {_fmt(s.qty / case.params.customer_demand)} días de demanda"
    if s.style == "pallets":
        return f"{_fmt(s.qty / s.pack)} pallets de {_fmt(s.pack)} {case.pl}"
    txt = f"{_fmt(s.qty)} {case.pl}"
    if s.kind == "fifo_lane":
        txt += f" (capacidad máxima del carril: {_fmt(s.capacity)})"
    return txt


def inventory_position(case: Case, idx: int) -> str:
    def nm(s):
        return f"«{s.name}»" if isinstance(s, (ProcSpec, TransSpec)) else "el inventario contiguo"
    prev = case.steps[idx - 1] if idx > 0 else None
    nxt = case.steps[idx + 1] if idx + 1 < len(case.steps) else None
    if prev is None:
        return f"antes de {nm(nxt)}" if nxt else ""
    if nxt is None:
        return f"después de {nm(prev)}"
    return f"entre {nm(prev)} y {nm(nxt)}"


def _role_name(case: Case, role: str) -> str:
    if role == "customer":
        return case.customer
    if role == "supplier":
        return case.supplier
    if role == "control":
        return case.control_name or "Planificación de la producción"
    if role == "procs":
        return "cada proceso"
    erp = next((e for e in case.extras if e[0] == "database"), None)
    return erp[1] if erp else "sistema"


def brief_html(case: Case) -> str:
    p = case.params
    info = LEVEL_INFO[case.level]
    stars = "★" * info["stars"] + "☆" * (len(LEVELS) - info["stars"])

    if case.demand_text:
        demand = case.demand_text
    else:
        demand = f"{_fmt(p.customer_demand)} {case.pl} por día"

    proc_rows = ""
    for s in case.processes:
        proc_rows += (f"<tr><td><b>{s.name}</b></td><td>{describe_ct(s, case)}</td><td>{describe_co(s)}</td>"
                      f"<td>{describe_up(s)}</td><td align='center'>{s.operators}</td>"
                      f"<td align='center'>{s.shifts}</td></tr>")

    inv_rows, trans_rows = "", ""
    for i, s in enumerate(case.steps):
        if isinstance(s, InvSpec):
            lab = s.label or "Inventario"
            inv_rows += f"<tr><td>{lab} <i>({inventory_position(case, i)})</i></td><td>{describe_inv(case, s)}</td></tr>"
        elif isinstance(s, TransSpec):
            note = f" — {s.note}" if s.note else ""
            trans_rows += (f"<tr><td>{s.name}{note}</td><td>{_MODE_LABEL[s.mode].capitalize()}</td>"
                           f"<td>{_fmt(s.days)} días en tránsito</td></tr>")
    trans_html = (f"<h4>Transportes</h4><table border='1' cellspacing='0' cellpadding='3' width='100%'>"
                  f"{trans_rows}</table>") if trans_rows else ""

    info_items = "".join(
        f"<li><b>{_role_name(case, a)} → {_role_name(case, b)}:</b> {d}.</li>"
        for a, b, _k, d in case.info_links)
    supplier_line = f"<li>Proveedor: <b>{case.supplier}</b>" + (f" — {case.supplier_note}" if case.supplier_note else "") + ".</li>"

    obj = "".join(f"<li>{o}</li>" for o in case.objectives)
    obj_html = f"<h4>Objetivos de aprendizaje</h4><ul>{obj}</ul>" if obj else ""
    notes = "".join(f"<li>{n}</li>" for n in case.notes)
    notes_html = f"<h4>Observaciones adicionales</h4><ul>{notes}</ul>" if notes else ""

    hints = ""
    if case.level in ("Junior", "Blanco"):
        keys = sorted(special_counts(case.reference_map()))
        if keys:
            hints = ("<p><i>Pista de nivel " + case.level + ": este caso usa además estos símbolos: "
                     + ", ".join(key_label(k) for k in keys) + ".</i></p>")

    return f"""
<h2>{case.title}</h2>
<p><b>Nivel {case.level}</b> {stars}<br><i>{case.sector} · {info['blurb']}</i></p>
<p>{case.story}</p>
{obj_html}
<h4>Demanda y jornada</h4>
<ul>
<li>Demanda del cliente: <b>{demand}</b>.</li>
<li>Turnos por día: <b>{p.shifts}</b> de <b>{_fmt(p.hours_per_shift)} h</b>; tiempo no disponible por turno
(descansos, reuniones): <b>{_fmt(p.unavailable_min_per_shift)} min</b>.</li>
</ul>

<h4>Procesos (en orden de flujo)</h4>
<table border="1" cellspacing="0" cellpadding="3" width="100%">
<tr bgcolor="#dfe9f5"><th>Proceso</th><th>Tiempo de ciclo</th><th>Cambio (C/O)</th>
<th>Disponibilidad</th><th>Operarios</th><th>Turnos</th></tr>
{proc_rows}
</table>

<h4>Inventarios</h4>
<table border="1" cellspacing="0" cellpadding="3" width="100%">{inv_rows}</table>
{trans_html}

<h4>Proveedor, cliente e información</h4>
<ul>
{supplier_line}
<li>Cliente: <b>{case.customer}</b>.</li>
</ul>
<p>Flujos de información:</p>
<ul>{info_items}</ul>
{notes_html}
{hints}
<h4>Tu tarea</h4>
<ol>
<li>Normaliza los datos (segundos por {case.unit}, % de disponibilidad, unidades de inventario, demanda por día).</li>
<li>Arrastra al canvas los símbolos del flujo de material y de información.</li>
<li>Edita cada símbolo (doble clic) y conecta con el tipo de flecha correcto.</li>
<li>Revisa Takt Time, lead time y cuello de botella, y pulsa <b>Evaluar mi mapa</b>.</li>
</ol>
"""


# =============================================================================
# Validación de casos (exactitud de los datos del enunciado)
# =============================================================================
def problems(case: Case) -> List[str]:
    """Devuelve una lista de problemas de consistencia (vacía si el caso es correcto).

    Garantiza que lo que se muestra en el enunciado (redondeado) se puede convertir
    de vuelta a los datos "limpios" sin error.
    """
    errs: List[str] = []
    d = case.params.customer_demand
    if case.level not in LEVELS:
        errs.append(f"nivel desconocido: {case.level}")
    if not case.processes:
        errs.append("el caso no tiene procesos")
    for s in case.processes:
        n = s.name
        if s.ct_style == "pph":
            v = round(3600 / s.ct)
            if abs(3600 / v - s.ct) > 1e-9:
                errs.append(f"{n}: {s.ct} s no da piezas/hora exactas")
        elif s.ct_style == "min":
            if abs(round(s.ct / 60, 2) * 60 - s.ct) > 1e-6:
                errs.append(f"{n}: {s.ct} s no da minutos exactos")
        elif s.ct_style == "batch":
            v = round(s.ct * s.batch / 60, 2)
            if abs(v * 60 / s.batch - s.ct) > 1e-6:
                errs.append(f"{n}: lote de {s.batch} no da minutos exactos")
        if s.co_style == "min" and abs(round(s.co / 60, 2) * 60 - s.co) > 1e-6:
            errs.append(f"{n}: C/O {s.co} s no da minutos exactos")
        if s.up_style == "oee" and (s.perf >= 100 and s.quality >= 100):
            errs.append(f"{n}: OEE sin rendimiento/calidad")
        if s.kind not in PROCESS_KINDS:
            errs.append(f"{n}: tipo de proceso inválido")
    for s in case.steps:
        if isinstance(s, InvSpec):
            if s.kind not in INVENTORY_KINDS:
                errs.append(f"inventario con tipo inválido: {s.kind}")
            if s.style == "days" and abs(round(s.qty / d, 2) * d - s.qty) > 1e-6:
                errs.append(f"{s.label or 'inventario'}: {s.qty} no da días exactos")
            if s.style == "pallets" and (s.pack <= 0 or s.qty % s.pack != 0):
                errs.append(f"{s.label or 'inventario'}: {s.qty} no es múltiplo del pallet {s.pack}")
            if s.kind == "fifo_lane" and s.capacity <= 0:
                errs.append("carril FIFO sin capacidad")
        elif isinstance(s, TransSpec) and s.mode not in _MODE_LABEL:
            errs.append(f"transporte con medio inválido: {s.mode}")
    for a, b, k, _ in case.info_links:
        if a not in ROLES or b not in ROLES:
            errs.append(f"flujo de información con rol inválido: {a}->{b}")
        if (a == "erp" or b == "erp") and not any(e[0] == "database" for e in case.extras):
            errs.append("flujo hacia 'erp' sin base de datos en extras")
    for kind, _name, _attrs, anchor in case.extras:
        if anchor != "top" and not (isinstance(anchor, int) and 0 <= anchor < len(case.steps)):
            errs.append(f"extra {kind}: ancla inválida")
    return errs
