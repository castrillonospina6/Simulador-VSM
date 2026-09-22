"""Modelos de datos puros del simulador VSM (sin dependencias de PyQt5).

Este módulo es el "esqueleto" del simulador: el canvas, el motor de cálculo,
el evaluador y la persistencia trabajan todos sobre `VSMMap`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict, fields
from typing import Dict, List, Optional

# --- Tipos de conexión -------------------------------------------------------
MATERIAL_CONNS = ("push", "fifo", "pull")
INFO_CONNS = ("info_manual", "info_electronic", "info_phone")
CONN_KINDS = MATERIAL_CONNS + INFO_CONNS

CONN_LABELS = {
    "push": "Material · empuje (push)",
    "fifo": "Material · carril FIFO",
    "pull": "Material · jalar (pull)",
    "info_manual": "Información · manual",
    "info_electronic": "Información · electrónica",
    "info_phone": "Información · teléfono",
}

# Familias de nodos que forman el flujo de material que calcula el motor
PROCESS_KINDS = ("process", "shared_process", "work_cell")
INVENTORY_KINDS = ("inventory", "supermarket", "safety_stock", "buffer_point", "safety_point", "fifo_lane")
FLOW_KINDS = PROCESS_KINDS + INVENTORY_KINDS + ("transport",)

# Nombre legible de cada tipo de nodo (tooltips, diálogos, catálogo)
KIND_LABELS = {
    "supplier": "Proveedor", "customer": "Cliente", "process": "Proceso",
    "shared_process": "Proceso compartido", "work_cell": "Celda de trabajo",
    "operator": "Operario", "data_box": "Tabla de datos",
    "inventory": "Inventario", "supermarket": "Supermercado",
    "fifo_lane": "Carril PEPS (FIFO)",
    "safety_stock": "Buffer / existencias de seguridad",
    "buffer_point": "Punto de acumulación BUFFER",
    "safety_point": "Punto de acumulación STOCK DE SEGURIDAD",
    "transport": "Transporte", "goods_arrow": "Flecha de transporte de mercancías",
    "mp_pt_flow": "Flujo de MP y PT", "pull_physical": "Pull físico",
    "control": "Control / planificación de la producción",
    "database": "Base de datos / MRP-ERP", "info_box": "Caja de información",
    "kanban_production": "Kanban de producción", "kanban_withdrawal": "Retirada Kanban",
    "kanban_batch": "Lote de tarjetas Kanban", "kanban_signal": "Señal Kanban",
    "kanban_post": "Tarjeta Kanban (poste)", "heijunka": "Nivelación de carga (heijunka)",
    "pull_ball": "Secuencia de tiro / pull ball",
    "time_segment": "Línea de tiempo (segmento)", "total_time": "Tiempo total / duración total",
    "clock": "Reloj", "rework": "Reelaboración",
    "kaizen": "Estallido Kaizen", "observation": "Observación",
}

# Símbolos genéricos (clase `Symbol`): valores por defecto y campos editables.
# tipo de campo: text | multiline | float | int
SYMBOL_SPECS = {
    "operator": dict(name="Operario", value=1, fields=[
        dict(attr="value", label="Cantidad de operarios", type="int", min=0, max=99)]),
    "data_box": dict(name="Datos del proceso",
                     text="Tiempo de ciclo = \nTiempo de cambio = \nDisponibilidad = ",
                     fields=[dict(attr="text", label="Filas de datos (una por línea)", type="multiline")]),
    "goods_arrow": dict(name="Movimiento de mercancías", value=0, fields=[
        dict(attr="value", label="Orientación", type="float", suffix=" °", min=-360, max=360)]),
    "mp_pt_flow": dict(name="Flujo de MP y PT"),
    "pull_physical": dict(name="Pull físico"),
    "database": dict(name="MRP / ERP", fields=[]),
    "info_box": dict(name="Información", text="Información", fields=[
        dict(attr="text", label="Texto", type="multiline")]),
    "kanban_production": dict(name="Kanban de producción", value=20, fields=[
        dict(attr="value", label="Piezas a producir", type="float", suffix=" u", max=1e9)]),
    "kanban_withdrawal": dict(name="Retirada Kanban", value=20, fields=[
        dict(attr="value", label="Piezas a retirar", type="float", suffix=" u", max=1e9)]),
    "kanban_batch": dict(name="Lote de tarjetas Kanban", value=20, fields=[
        dict(attr="value", label="Piezas por lote", type="float", suffix=" u", max=1e9)]),
    "kanban_signal": dict(name="Señal Kanban", value=50, fields=[
        dict(attr="value", label="Umbral de activación", type="float", suffix=" u", max=1e9)]),
    "kanban_post": dict(name="Poste Kanban"),
    "heijunka": dict(name="Nivelación de carga"),
    "pull_ball": dict(name="Pull ball"),
    "time_segment": dict(name="Segmento de tiempo", value=1.0, value2=60.0, fields=[
        dict(attr="value", label="Tiempo de espera (sin valor agregado)", type="float", suffix=" d", max=1e6),
        dict(attr="value2", label="Tiempo de proceso (valor agregado)", type="float", suffix=" s", max=1e9)]),
    "total_time": dict(name="Duración total"),
    "clock": dict(name="Reloj", text="", fields=[
        dict(attr="text", label="Retraso / restricción de tiempo", type="text")]),
    "rework": dict(name="Reelaboración", value=0, fields=[
        dict(attr="value", label="Porcentaje de reelaboración", type="float", suffix=" %", max=100)]),
    "kaizen": dict(name="Mejora Kaizen"),
    "observation": dict(name="Observación", text="", fields=[
        dict(attr="text", label="Detalle (ajuste de programas por nivel de inventario)", type="text")]),
}


def new_id() -> str:
    return uuid.uuid4().hex[:8]


# --- Parámetros del caso -----------------------------------------------------
@dataclass
class CaseParams:
    """Parámetros globales que determinan el Takt Time."""

    customer_demand: float = 900.0          # unidades por día
    shifts: int = 2                         # turnos por día
    hours_per_shift: float = 8.0            # horas por turno
    unavailable_min_per_shift: float = 30.0  # descansos, reuniones, etc.

    @property
    def seconds_per_shift(self) -> float:
        return max(0.0, self.hours_per_shift * 3600 - self.unavailable_min_per_shift * 60)

    @property
    def available_seconds_per_day(self) -> float:
        return self.shifts * self.seconds_per_shift

    @property
    def takt_time_s(self) -> float:
        if self.customer_demand <= 0:
            return 0.0
        return self.available_seconds_per_day / self.customer_demand


# --- Parámetros económicos (vista económica / etapa 5) ----------------------
@dataclass
class EconParams:
    """Supuestos para convertir inventario y lead time en dinero. Valores de ejemplo: cámbialos por los reales."""

    material_cost: float = 10.0        # costo de materia prima / insumos por unidad ($)
    conversion_cost: float = 5.0       # costo de conversión por unidad: mano de obra + gastos de fabricación ($)
    capital_rate: float = 12.0         # costo de capital (% anual) — sobre inventario y mercancía en tránsito
    storage_rate: float = 5.0          # bodegaje, seguros y manejo (% anual) — solo inventario
    obsolescence_rate: float = 3.0     # obsolescencia y merma (% anual) — solo inventario
    work_days_per_year: float = 250.0  # días laborales por año
    include_transit: bool = True       # ¿la mercancía en tránsito es de la empresa?

    @property
    def unit_cost(self) -> float:
        return self.material_cost + self.conversion_cost


# --- Nodos -------------------------------------------------------------------
@dataclass
class Node:
    id: str = ""
    kind: str = ""
    name: str = ""
    x: float = 0.0
    y: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Process(Node):
    kind: str = "process"
    name: str = "Proceso"
    cycle_time_s: float = 30.0     # TC: tiempo de ciclo por pieza (s)
    changeover_s: float = 0.0      # C/O: tiempo de cambio de referencia (s)
    uptime_pct: float = 100.0      # disponibilidad de la máquina (%)
    operators: int = 1
    shifts: int = 1
    mttr_s: float = 0.0            # reparación media por falla (s) para la simulación; 0 = valor del simulador


@dataclass
class SharedProcess(Process):
    """Operación o departamento compartido con otros mapas de flujo."""
    kind: str = "shared_process"
    name: str = "Proceso compartido"


@dataclass
class WorkCell(Process):
    """Varios procesos integrados en una celda de manufactura."""
    kind: str = "work_cell"
    name: str = "Celda de trabajo"


@dataclass
class Inventory(Node):
    kind: str = "inventory"
    name: str = "Inventario"
    quantity: float = 0.0          # unidades almacenadas


@dataclass
class Supermarket(Inventory):
    kind: str = "supermarket"
    name: str = "Supermercado"
    max_level: float = 0.0         # nivel máximo = tarjetas Kanban × contenedor (0 = sin definir)
    min_level: float = 0.0         # nivel mínimo de seguridad (0 = sin definir)


@dataclass
class FifoLane(Inventory):
    """Carril PEPS (FIFO): primero en entrar, primero en salir; se anota la capacidad máxima."""
    kind: str = "fifo_lane"
    name: str = "Carril PEPS (FIFO)"
    capacity: float = 20.0


@dataclass
class SafetyStock(Inventory):
    """Buffer / existencias reservadas para circunstancias particulares."""
    kind: str = "safety_stock"
    name: str = "Buffer / stock de seguridad"


@dataclass
class BufferPoint(Inventory):
    """Punto de acumulación BUFFER (protege de variaciones externas: demanda)."""
    kind: str = "buffer_point"
    name: str = "Buffer"


@dataclass
class SafetyPoint(Inventory):
    """Punto de acumulación STOCK DE SEGURIDAD (protege de problemas internos)."""
    kind: str = "safety_point"
    name: str = "Stock de seguridad"


@dataclass
class External(Node):
    """Proveedor o cliente (símbolo de fábrica)."""

    kind: str = "supplier"
    name: str = "Proveedor"
    note: str = ""


@dataclass
class Transport(Node):
    kind: str = "transport"
    name: str = "Camión"
    transit_days: float = 0.0      # tiempo en tránsito (días laborales)
    mode: str = "camion"           # 'camion' | 'avion' | 'barco'


@dataclass
class Control(Node):
    """Planificación / control de la producción."""

    kind: str = "control"
    name: str = "Planificación de la producción"


@dataclass
class Symbol(Node):
    """Símbolo genérico (anotaciones, Kanban, tiempo, mejora…). Ver SYMBOL_SPECS."""

    kind: str = "info_box"
    name: str = ""
    text: str = ""
    value: float = 0.0
    value2: float = 0.0


NODE_CLASSES = {
    "process": Process, "shared_process": SharedProcess, "work_cell": WorkCell,
    "inventory": Inventory, "supermarket": Supermarket, "safety_stock": SafetyStock,
    "fifo_lane": FifoLane,
    "buffer_point": BufferPoint, "safety_point": SafetyPoint,
    "supplier": External, "customer": External,
    "transport": Transport, "control": Control,
}
NODE_CLASSES.update({k: Symbol for k in SYMBOL_SPECS})
ALL_NODE_KINDS = tuple(NODE_CLASSES)


def make_node(kind: str, x: float = 0.0, y: float = 0.0) -> Node:
    if kind == "supplier":
        node: Node = External(kind="supplier", name="Proveedor", note="Entrega semanal")
    elif kind == "customer":
        node = External(kind="customer", name="Cliente", note="")
    elif kind in SYMBOL_SPECS:
        spec = SYMBOL_SPECS[kind]
        node = Symbol(kind=kind, name=spec.get("name", ""), text=spec.get("text", ""),
                      value=float(spec.get("value", 0.0)), value2=float(spec.get("value2", 0.0)))
    elif kind in NODE_CLASSES:
        node = NODE_CLASSES[kind]()
    else:
        raise ValueError(f"Tipo de nodo desconocido: {kind}")
    node.id = new_id()
    node.x, node.y = x, y
    return node


def node_from_dict(d: dict) -> Node:
    cls = NODE_CLASSES[d["kind"]]
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})


# --- Conexiones --------------------------------------------------------------
@dataclass
class Connection:
    id: str
    source: str
    target: str
    kind: str = "push"
    note: str = ""      # etiqueta libre: frecuencia, capacidad máx. de un carril FIFO, etc.

    def to_dict(self) -> dict:
        return asdict(self)


# --- Mapa completo -----------------------------------------------------------
class VSMMap:
    def __init__(self, params: Optional[CaseParams] = None, case_id: Optional[str] = None):
        self.params: CaseParams = params or CaseParams()
        self.econ: EconParams = EconParams()
        self.nodes: Dict[str, Node] = {}
        self.connections: List[Connection] = []
        self.case_id: Optional[str] = case_id

    # -- edición
    def add_node(self, node: Node) -> Node:
        if not node.id:
            node.id = new_id()
        self.nodes[node.id] = node
        return node

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        self.connections = [c for c in self.connections
                            if c.source != node_id and c.target != node_id]

    def add_connection(self, source: str, target: str, kind: str, note: str = "") -> Optional[Connection]:
        if source == target or source not in self.nodes or target not in self.nodes:
            return None
        if kind not in CONN_KINDS:
            return None
        for c in self.connections:
            if c.source == source and c.target == target and c.kind == kind:
                return None
        conn = Connection(id=new_id(), source=source, target=target, kind=kind, note=note)
        self.connections.append(conn)
        return conn

    def remove_connection(self, conn_id: str) -> None:
        self.connections = [c for c in self.connections if c.id != conn_id]

    # -- consultas
    def nodes_of(self, *kinds: str) -> List[Node]:
        return [n for n in self.nodes.values() if n.kind in kinds]

    # -- serialización
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "case_id": self.case_id,
            "params": asdict(self.params),
            "econ": asdict(self.econ),
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "connections": [c.to_dict() for c in self.connections],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VSMMap":
        pnames = {f.name for f in fields(CaseParams)}
        params = CaseParams(**{k: v for k, v in d.get("params", {}).items() if k in pnames})
        m = cls(params=params, case_id=d.get("case_id"))
        enames = {f.name for f in fields(EconParams)}
        m.econ = EconParams(**{k: v for k, v in d.get("econ", {}).items() if k in enames})   # archivos viejos: valores por defecto
        for nd in d.get("nodes", []):
            m.add_node(node_from_dict(nd))
        for cd in d.get("connections", []):
            if cd["source"] in m.nodes and cd["target"] in m.nodes and cd["kind"] in CONN_KINDS:
                m.connections.append(Connection(id=cd.get("id") or new_id(),
                                                source=cd["source"], target=cd["target"],
                                                kind=cd["kind"], note=cd.get("note", "")))
        return m
