"""Simulación dinámica de eventos discretos (SimPy) del VSM. Sin PyQt5.

El VSM clásico es estático: usa promedios, así que no puede mostrar colas, bloqueos ni inanición. Este módulo
toma el mismo mapa (procesos, inventarios y transportes ordenados por X, igual que el motor estático) y lo
ejecuta como una línea en la que las piezas se mueven de verdad, con variabilidad.

Modelo
------
* Tiempo en SEGUNDOS LABORALES (solo se simula la jornada disponible; los días laborales del motor estático).
* Cada inventario es un contenedor (simpy.Container) que arranca con la cantidad del mapa y tiene capacidad
  finita: cantidad × cap_factor (carril FIFO: su capacidad máxima). Entre dos procesos sin inventario se
  inserta un contenedor de 1 lote (traspaso directo). Un contenedor lleno BLOQUEA al proceso anterior; uno
  vacío deja SIN MATERIAL (inanición) al siguiente.
* SUPERMERCADO = KANBAN REAL: un supermercado tiene N tarjetas (nivel máximo del nodo; si no se indica,
  cantidad × cap_factor). El proceso que lo repone solo arranca un lote si tiene una tarjeta libre, y la
  tarjeta vuelve cuando el siguiente paso (o el cliente) retira material. El nivel nunca supera el máximo y el
  proceso que repone queda «esperando señal» (no es bloqueo). Al final se dictamina si el supermercado aguanta.
* Cada proceso es un servidor único: toma un lote, lo trabaja (tiempo de ciclo con variabilidad gamma de
  coeficiente de variación `ct_cv`), y lo deposita; si la salida está llena espera (bloqueo).
* Disponibilidad: fallas que dependen del tiempo de trabajo, con MTBF = MTTR·A/(1−A) para que el tiempo de
  ciclo efectivo medio sea TC/A, la misma cifra que usa el motor estático. El MTTR sale del proceso
  (`mttr_s`, editable en su formulario) o, si es 0, del valor por defecto del simulador.
* Transporte: retraso puro (tránsito), con varias unidades en camino a la vez.
* Proveedor: entrega al ritmo de la demanda (`release="demand"`) o sin límite, hasta llenar (`"unlimited"`,
  empuje puro: el primer proceso nunca espera material).
* Cliente: pide al ritmo de la demanda con variabilidad `demand_cv`; si no hay producto terminado la venta
  se pierde (nivel de servicio = pedido atendido / pedido total).
* Para que sea rápido, las piezas se mueven en lotes de B unidades (B se elige solo; `batch` lo fuerza).

Lead time dinámico = inventario en proceso promedio / rendimiento (ley de Little). El PCE dinámico usa ese
lead time. Limitaciones: no se modelan cambios de referencia (C/O), operarios ni turnos individuales, ni
mezcla de productos; cada proceso es un servidor único.

Requiere `pip install simpy`.
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field, fields, replace
from typing import Callable, Dict, List, Optional, Tuple

try:                                    # se importa aquí para poder avisar con un mensaje claro
    import simpy
except ImportError:                     # pragma: no cover
    simpy = None

from .engine import compute_metrics, ordered_flow
from .models import VSMMap, Process, Inventory

RELEASES = ("demand", "unlimited")


class SimulationError(Exception):
    """Error legible para mostrar al usuario."""


# =============================================================================
# Configuración y resultados
# =============================================================================
@dataclass
class SimConfig:
    days: float = 20.0                # días laborales medidos
    warmup_days: float = 3.0          # días iniciales que se descartan (régimen transitorio)
    replications: int = 5
    seed: int = 1
    ct_cv: float = 0.25               # coeficiente de variación del tiempo de ciclo (0 = determinista)
    demand_cv: float = 0.25           # coeficiente de variación del intervalo entre pedidos
    mttr_min: float = 10.0            # tiempo medio de reparación (min)
    cap_factor: float = 2.0           # capacidad de cada inventario = cantidad del mapa × factor
    release: str = "demand"           # 'demand' | 'unlimited'
    batch: Optional[int] = None       # unidades por lote de simulación (None = automático)
    target_batches: int = 2000        # lotes por estación que se busca simular (controla la velocidad)
    sample_points: int = 400          # fotogramas de la animación / puntos de las series

    def validate(self) -> None:
        if self.days <= 0:
            raise SimulationError("Los días a simular deben ser mayores que 0.")
        if self.warmup_days < 0:
            raise SimulationError("El calentamiento no puede ser negativo.")
        if not 1 <= int(self.replications) <= 100:
            raise SimulationError("Las réplicas deben estar entre 1 y 100.")
        if min(self.ct_cv, self.demand_cv, self.mttr_min, self.cap_factor) < 0:
            raise SimulationError("La variabilidad, la reparación y la capacidad no pueden ser negativas.")
        if self.release not in RELEASES:
            raise SimulationError(f"Política de suministro desconocida: {self.release}")


@dataclass
class Kpis:
    throughput_day: float = 0.0       # u/día entregadas al cliente
    demand_day: float = 0.0           # u/día pedidas
    fill_rate: float = 1.0            # nivel de servicio (0–1)
    lost_day: float = 0.0             # u/día no atendidas
    lead_time_days: float = 0.0       # ley de Little
    pce: float = 0.0
    wip_units: float = 0.0            # inventario total promedio en el flujo


@dataclass
class StationStats:
    node_id: str
    name: str
    busy: float                       # fracción del tiempo trabajando
    down: float                       # … en falla / reparación
    blocked: float                    # … con la pieza terminada y la salida llena
    starved: float                    # … esperando material
    throughput_day: float
    idle: float = 0.0                 # … esperando señal Kanban (pull): no es una pérdida

    @property
    def occupancy(self) -> float:
        return self.busy + self.down


@dataclass
class BufferStats:
    node_id: str
    name: str
    kind: str                         # 'inventory' | 'implicit' (traspaso) | 'edge' (suministro/entrega) | 'transport'
    capacity_u: float
    avg_u: float
    min_u: float
    max_u: float
    full_pct: float                   # fracción del tiempo lleno
    empty_pct: float                  # fracción del tiempo vacío
    wait_days: float                  # espera promedio (Little)
    static_days: float                # espera que calcula el VSM estático
    below_min_pct: float = 0.0        # fracción del tiempo bajo el nivel mínimo (supermercados)
    min_level_u: float = 0.0
    empty_reps: float = 0.0           # fracción de réplicas en que se vació alguna vez
    is_super: bool = False
    consumer: str = ""                # paso que retira de este inventario


@dataclass
class Frame:
    """Foto del sistema en un instante (para animar el mapa)."""
    day: float
    level: Dict[str, float]           # id de nodo -> unidades (inventarios y mercancía en tránsito)
    state: Dict[str, str]             # id de proceso -> busy | down | blocked | starved | idle
    done: Dict[str, float]            # id de nodo -> unidades procesadas/entregadas acumuladas


@dataclass
class SupermarketCheck:
    node_id: str
    name: str
    verdict: str                      # 'ok' | 'justo' | 'no'
    max_u: float
    min_cfg_u: float
    avg_u: float
    min_obs_u: float
    max_obs_u: float
    empty_pct: float
    below_min_pct: float
    empty_reps: float
    consumer: str
    consumer_starved: float
    advice: str


@dataclass
class SweepPoint:
    max_u: float
    empty_pct: float
    empty_reps: float
    fill_rate: float
    wip_units: float
    verdict: str


@dataclass
class SimResult:
    config: SimConfig
    batch: int
    replications: int
    kpi: Kpis
    ci: Dict[str, float]              # semiancho del IC 95 % de cada KPI (0 con 1 réplica)
    stations: List[StationStats]
    buffers: List[BufferStats]
    static_lead_time_days: float
    static_pce: float
    takt_time_s: float
    capacity_day: float = 0.0          # u/día que permite el proceso más lento (estático)
    series: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)   # nombre -> (día, unidades)
    series_cap: Dict[str, float] = field(default_factory=dict)
    warmup_days: float = 0.0
    warnings: List[str] = field(default_factory=list)
    frames: List[Frame] = field(default_factory=list)
    node_cap: Dict[str, float] = field(default_factory=dict)     # id de nodo -> capacidad (u)
    node_min: Dict[str, float] = field(default_factory=dict)     # id de nodo -> nivel mínimo (u)


# =============================================================================
# Instrumentos
# =============================================================================
class _Level:
    """Nivel con promedio ponderado por el tiempo (y tiempo lleno / vacío)."""

    def __init__(self, t: float, level: float, cap: Optional[float] = None, thresh: Optional[float] = None):
        self.cap, self.thresh = cap, thresh
        self.reset(t, level)

    def reset(self, t: float, level: float) -> None:
        self.t0 = self.last_t = t
        self.level = level
        self.area = self.t_full = self.t_empty = self.t_below = 0.0
        self.min = self.max = level

    def update(self, t: float, level: float) -> None:
        dt = t - self.last_t
        if dt > 0:
            self.area += self.level * dt
            if self.level <= 0:
                self.t_empty += dt
            if self.cap is not None and self.level >= self.cap:
                self.t_full += dt
            if self.thresh is not None and self.level < self.thresh:
                self.t_below += dt
        self.last_t, self.level = t, level
        self.min, self.max = min(self.min, level), max(self.max, level)

    def window(self) -> float:
        return max(self.last_t - self.t0, 1e-12)

    def mean(self) -> float:
        return self.area / self.window()


class _Clock:
    """Tiempo acumulado en cada estado de un proceso."""
    STATES = ("busy", "down", "blocked", "starved", "idle")

    def __init__(self, t: float):
        self.state, self.since = "starved", t
        self.acc = {s: 0.0 for s in self.STATES}

    def set(self, state: str, t: float) -> None:
        self.acc[self.state] += t - self.since
        self.state, self.since = state, t

    def reset(self, t: float) -> None:
        self.acc = {s: 0.0 for s in self.STATES}
        self.since = t


class _Buf:
    def __init__(self, env, name: str, node, cap: int, init: int, kind: str, kanban: bool = False,
                 thresh: Optional[float] = None, consumer: str = ""):
        self.name, self.node, self.kind, self.cap, self.consumer = name, node, kind, cap, consumer
        self.cont = simpy.Container(env, capacity=cap, init=init)
        # tarjetas Kanban libres: nivel + tarjetas libres + material en camino = cap
        self.cards = simpy.Container(env, capacity=cap, init=cap - init) if kanban else None
        self.meter = _Level(0.0, init, cap, thresh)

    def touch(self, now: float) -> None:
        self.meter.update(now, self.cont.level)


class _Stn:
    def __init__(self, env, kind: str, node, name: str, rng: random.Random, cfg: SimConfig, B: int,
                 interval: float, transit_s: float = 0.0):
        self.kind, self.node, self.name, self.rng, self.cfg = kind, node, name, rng, cfg
        self.clock, self.wip, self.count, self.total = _Clock(0.0), _Level(0.0, 0), 0, 0
        self.mtbf = None
        if kind == "srv":
            self.ct = node.cycle_time_s * B
            a = node.uptime_pct / 100.0
            if 0 < a < 1 and (cfg.mttr_min > 0 or getattr(node, "mttr_s", 0.0) > 0):
                self.mttr = (getattr(node, "mttr_s", 0.0) or cfg.mttr_min * 60.0)
                self.mtbf = self.mttr * a / (1 - a)
                self.ttf = rng.expovariate(1.0 / self.mtbf)
        else:
            self.transit, self.n = transit_s, 0
            k = max(2, math.ceil(2 * transit_s / interval) + 1) if interval > 0 else 2
            self.slots = simpy.Container(env, capacity=k, init=k)


@dataclass
class _Sales:
    demanded: int = 0
    served: int = 0


# =============================================================================
# Procesos SimPy
# =============================================================================
def _sample(rng: random.Random, mean: float, cv: float) -> float:
    if mean <= 0:
        return 0.0
    if cv <= 0:
        return mean
    k = 1.0 / (cv * cv)
    return rng.gammavariate(k, mean / k)


def _take(env, b: _Buf):
    """Retira un lote; si es un supermercado, la tarjeta vuelve al proceso que lo repone."""
    yield b.cont.get(1)
    b.touch(env.now)
    if b.cards is not None:
        yield b.cards.put(1)


def _server(env, st: _Stn, inb: _Buf, outb: _Buf):
    while True:
        st.clock.set("idle", env.now)
        if outb.cards is not None:                          # pull: necesita una tarjeta para producir
            yield outb.cards.get(1)
        st.clock.set("starved", env.now)
        yield from _take(env, inb)
        st.wip.update(env.now, 1)
        st.clock.set("busy", env.now)
        dur = _sample(st.rng, st.ct, st.cfg.ct_cv)
        while dur > 1e-9:
            if st.mtbf is None or dur < st.ttf:
                yield env.timeout(dur)
                if st.mtbf is not None:
                    st.ttf -= dur
                break
            yield env.timeout(st.ttf)                       # trabaja hasta la falla
            dur -= st.ttf
            st.clock.set("down", env.now)
            yield env.timeout(st.rng.expovariate(1.0 / st.mttr))
            st.clock.set("busy", env.now)
            st.ttf = st.rng.expovariate(1.0 / st.mtbf)
        st.clock.set("blocked", env.now)
        yield outb.cont.put(1)
        outb.touch(env.now)
        st.wip.update(env.now, 0)
        st.count += 1
        st.total += 1


def _delay(env, st: _Stn, inb: _Buf, outb: _Buf):
    while True:
        yield st.slots.get(1)
        if outb.cards is not None:
            yield outb.cards.get(1)
        yield from _take(env, inb)
        st.n += 1
        st.wip.update(env.now, st.n)
        env.process(_deliver(env, st, outb))


def _deliver(env, st: _Stn, outb: _Buf):
    if st.transit > 0:
        yield env.timeout(st.transit)
    yield outb.cont.put(1)
    outb.touch(env.now)
    st.n -= 1
    st.wip.update(env.now, st.n)
    st.count += 1
    st.total += 1
    yield st.slots.put(1)


def _supplier(env, out: _Buf, interval: float):
    while True:
        if interval > 0:
            yield env.timeout(interval)
        if out.cards is not None:
            yield out.cards.get(1)
        yield out.cont.put(1)
        out.touch(env.now)


def _customer(env, fin: _Buf, interval: float, cv: float, rng: random.Random, sales: _Sales):
    while True:
        yield env.timeout(_sample(rng, interval, cv))
        sales.demanded += 1
        if fin.cont.level >= 1:
            yield from _take(env, fin)
            sales.served += 1


def _warmup(env, warm_s: float, bufs, stns, sales: _Sales):
    yield env.timeout(warm_s)
    for b in bufs:
        b.meter.reset(env.now, b.cont.level)
    for s in stns:
        s.clock.reset(env.now)
        s.wip.reset(env.now, s.wip.level)
        s.count = 0
    sales.demanded = sales.served = 0


def _sampler(env, bufs, stns, series, frames, day_s: float, dt: float, B: int):
    while True:
        lv, stt, dn = {}, {}, {}
        for b in bufs:
            v = b.cont.level * B
            series[b.name].append((env.now / day_s, v))
            if b.node is not None:
                lv[b.node.id] = v
        for s in stns:
            if s.node is None:
                continue
            if s.kind == "srv":
                stt[s.node.id] = s.clock.state
            else:
                lv[s.node.id] = s.n * B
            dn[s.node.id] = s.total * B
        frames.append(Frame(env.now / day_s, lv, stt, dn))
        yield env.timeout(dt)


# =============================================================================
# Una réplica
# =============================================================================
@dataclass
class _Run:
    kpi: Kpis
    stations: List[StationStats]
    buffers: List[BufferStats]
    series: Dict[str, List[Tuple[float, float]]]
    caps: Dict[str, float]
    frames: List[Frame] = field(default_factory=list)
    node_cap: Dict[str, float] = field(default_factory=dict)
    node_min: Dict[str, float] = field(default_factory=dict)


def _batch_size(flow, demand: float, cfg: SimConfig, total_days: float) -> int:
    if cfg.batch:
        return max(1, int(cfg.batch))
    b = max(1, math.ceil(demand * total_days / cfg.target_batches))
    pos = [n.quantity for n in flow if isinstance(n, Inventory) and n.quantity > 0]
    if pos:                                   # que el lote no sea grande frente al inventario más pequeño
        b = max(math.ceil(b / 4), min(b, max(1, int(min(pos) // 4))))
    return b


def _build_sequence(flow):
    """Alterna inventarios y estaciones; inserta contenedores implícitos y enlaces de tiempo cero."""
    seq, prev = [], None
    for n in flow:
        kind = "buf" if isinstance(n, Inventory) else "srv" if isinstance(n, Process) else "dly"
        if prev is None:
            if kind != "buf":
                seq.append(("buf", None))
        elif prev == "buf" and kind == "buf":
            seq.append(("dly", None))
        elif prev != "buf" and kind != "buf":
            seq.append(("buf", None))
        seq.append((kind, n))
        prev = kind
    if prev != "buf":
        seq.append(("buf", None))
    return seq


def _run_once(vmap: VSMMap, cfg: SimConfig, seed: int, record: bool) -> _Run:
    p = vmap.params
    day_s, demand = p.available_seconds_per_day, p.customer_demand
    flow = ordered_flow(vmap)
    total_days = cfg.warmup_days + cfg.days
    B = _batch_size(flow, demand, cfg, total_days)
    interval = day_s * B / demand                          # segundos entre pedidos de un lote
    env = simpy.Environment()
    seq = _build_sequence(flow)

    def nm(i):                                             # nombre de la estación vecina
        n = seq[i][1]
        return n.name if n is not None else "siguiente paso"

    used: set = set()

    def unique(name: str) -> str:
        base, k = name, 2
        while name in used:
            name, k = f"{base} ({k})", k + 1
        used.add(name)
        return name

    def inv_label(i: int, n) -> str:            # «Inventario» genérico -> dónde está
        if n.name.strip() not in ("", "Inventario"):
            return n.name
        if i + 1 < len(seq):
            return f"Inventario antes de {nm(i + 1)}"
        return f"Inventario después de {nm(i - 1)}"

    bufs: Dict[int, _Buf] = {}
    for i, (k, n) in enumerate(seq):
        if k != "buf":
            continue
        if n is not None:
            init = int(round(n.quantity / B))
            sm = n.kind == "supermarket"
            thresh = None
            if n.kind == "fifo_lane":
                cap = max(1, int(round(getattr(n, "capacity", 0) / B)))
                init = min(init, cap)
            elif sm and getattr(n, "max_level", 0.0) > 0:
                cap = max(2, int(round(n.max_level / B)))
                init = cap                               # un supermercado Kanban arranca lleno (todas las tarjetas afuera)
            else:
                cap = max(2, math.ceil(init * cfg.cap_factor))
            if sm and getattr(n, "min_level", 0.0) > 0:
                thresh = n.min_level / B
            bufs[i] = _Buf(env, unique(inv_label(i, n)), n, max(cap, init), init, "inventory", kanban=sm,
                           thresh=thresh, consumer=nm(i + 1) if i + 1 < len(seq) else "cliente")
        elif i == 0:
            bufs[i] = _Buf(env, unique("Suministro"), None, 2, 0, "edge")
        elif i == len(seq) - 1:
            cap = max(2, math.ceil(0.5 * demand / B))
            bufs[i] = _Buf(env, unique("Entrega al cliente"), None, cap, 0, "edge")
        else:
            bufs[i] = _Buf(env, unique(f"{nm(i - 1)} → {nm(i + 1)}"), None, 1, 0, "implicit")

    stns: List[_Stn] = []
    for i, (k, n) in enumerate(seq):
        if k == "buf":
            continue
        rng = random.Random(f"{seed}:{i}")
        if k == "srv":
            st = _Stn(env, "srv", n, n.name, rng, cfg, B, interval)
            env.process(_server(env, st, bufs[i - 1], bufs[i + 1]))
        else:
            transit = (max(0.0, n.transit_days) * day_s) if n is not None else 0.0
            st = _Stn(env, "dly", n, n.name if n is not None else "enlace", rng, cfg, B, interval, transit)
            env.process(_delay(env, st, bufs[i - 1], bufs[i + 1]))
        stns.append(st)

    sales = _Sales()
    first, last = bufs[0], bufs[len(seq) - 1]
    env.process(_supplier(env, first, interval if cfg.release == "demand" else 0.0))
    env.process(_customer(env, last, interval, cfg.demand_cv, random.Random(f"{seed}:c"), sales))
    all_bufs = list(bufs.values())
    env.process(_warmup(env, cfg.warmup_days * day_s, all_bufs, stns, sales))
    series = {b.name: [] for b in all_bufs}
    frames: List[Frame] = []
    if record:
        env.process(_sampler(env, all_bufs, stns, series, frames, day_s,
                             total_days * day_s / max(2, cfg.sample_points), B))

    end = total_days * day_s
    env.run(until=end)
    window = cfg.days * day_s
    for b in all_bufs:
        b.touch(end)
    for s in stns:
        s.clock.set(s.clock.state, end)
        s.wip.update(end, s.wip.level)

    thr = sales.served * B / cfg.days
    dem = sales.demanded * B / cfg.days
    static = compute_metrics(vmap)
    stations, buffers = [], []
    wip_total = 0.0
    for s in stns:
        if s.kind == "srv":
            a = s.clock.acc
            stations.append(StationStats(s.node.id, s.name, a["busy"] / window, a["down"] / window,
                                         a["blocked"] / window, a["starved"] / window, s.count * B / cfg.days,
                                         a["idle"] / window))
            wip_total += s.wip.mean() * B
        elif s.node is not None:                           # transporte real (los enlaces no se reportan)
            avg = s.wip.mean() * B
            wip_total += avg
            buffers.append(BufferStats(s.node.id, s.name, "transport", 0.0, avg, s.wip.min * B, s.wip.max * B,
                                       0.0, 0.0, avg / thr if thr > 0 else 0.0, max(0.0, s.node.transit_days)))
    for i in sorted(bufs):
        b = bufs[i]
        avg = b.meter.mean() * B
        wip_total += avg
        w = b.meter.window()
        static_d = b.node.quantity / demand if b.node is not None else 0.0
        buffers.append(BufferStats(b.node.id if b.node is not None else "", b.name, b.kind, b.cap * B, avg,
                                   b.meter.min * B, b.meter.max * B, b.meter.t_full / w, b.meter.t_empty / w,
                                   avg / thr if thr > 0 else 0.0, static_d, b.meter.t_below / w,
                                   (b.meter.thresh or 0.0) * B, 1.0 if b.meter.t_empty / w > 0.001 else 0.0,
                                   b.cards is not None, b.consumer))
    lead = wip_total / thr if thr > 0 else 0.0
    pce = min(1.0, static.va_time_s / (lead * day_s)) if lead > 0 else 0.0
    kpi = Kpis(thr, dem, sales.served / sales.demanded if sales.demanded else 1.0, max(0.0, dem - thr),
               lead, pce, wip_total)
    caps = {b.name: b.cap * B for b in all_bufs}
    node_cap = {b.node.id: b.cap * B for b in all_bufs if b.node is not None}
    node_min = {b.node.id: (b.meter.thresh or 0.0) * B for b in all_bufs if b.node is not None}
    return _Run(kpi, stations, buffers, series if record else {}, caps, frames if record else [], node_cap,
                node_min)


# =============================================================================
# API pública
# =============================================================================
def _mean_obj(objs):
    first, kw = objs[0], {}
    for f in fields(first):
        v = getattr(first, f.name)
        kw[f.name] = statistics.fmean(getattr(o, f.name) for o in objs) if isinstance(v, float) else v
    return type(first)(**kw)


_T95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26}


def _half_width(xs: List[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    t = _T95.get(n - 1, 2.2 if n < 30 else 1.96)
    return t * statistics.stdev(xs) / math.sqrt(n)


def _check(vmap: VSMMap) -> None:
    p = vmap.params
    if p.customer_demand <= 0:
        raise SimulationError("La demanda del cliente debe ser mayor que 0 (Archivo → Parámetros del caso).")
    if p.available_seconds_per_day <= 0:
        raise SimulationError("El tiempo disponible por día es 0: revisa turnos y horas.")
    if not any(isinstance(n, Process) for n in ordered_flow(vmap)):
        raise SimulationError("El mapa no tiene procesos: agrega al menos uno para simular.")


def simulate(vmap: VSMMap, cfg: Optional[SimConfig] = None,
             progress: Optional[Callable[[int, int], None]] = None) -> SimResult:
    """Simula el mapa `replications` veces (semillas seed, seed+1…) y devuelve los promedios."""
    if simpy is None:
        raise SimulationError("Falta la librería simpy.\nInstálala con:  pip install simpy")
    cfg = cfg or SimConfig()
    cfg.validate()
    _check(vmap)
    n = int(cfg.replications)
    runs: List[_Run] = []
    for i in range(n):
        if progress:
            progress(i, n)
        runs.append(_run_once(vmap, cfg, cfg.seed + i, record=(i == 0)))
    if progress:
        progress(n, n)

    kpi = _mean_obj([r.kpi for r in runs])
    ci = {f.name: _half_width([getattr(r.kpi, f.name) for r in runs]) for f in fields(Kpis)}
    stations = [_mean_obj([r.stations[j] for r in runs]) for j in range(len(runs[0].stations))]
    buffers = [_mean_obj([r.buffers[j] for r in runs]) for j in range(len(runs[0].buffers))]
    static = compute_metrics(vmap)
    day_s = vmap.params.available_seconds_per_day
    cap_day = (day_s / max(r.effective_ct_s for r in static.process_results)
               if static.process_results and max(r.effective_ct_s for r in static.process_results) > 0 else 0.0)
    warns = []
    if kpi.throughput_day <= 0:
        warns.append("No salió producto en el periodo medido: revisa inventarios, tiempos y calentamiento.")
    res = SimResult(cfg, _batch_size(ordered_flow(vmap), vmap.params.customer_demand, cfg,
                                     cfg.warmup_days + cfg.days), n, kpi, ci, stations, buffers,
                    static.lead_time_days, static.pce, static.takt_time_s, cap_day, runs[0].series,
                    runs[0].caps, cfg.warmup_days, warns, runs[0].frames, runs[0].node_cap, runs[0].node_min)
    return res


# =============================================================================
# ¿Aguanta el supermercado?
# =============================================================================
def _verdict(b: BufferStats) -> str:
    if b.empty_pct > 0.01:
        return "no"                           # se queda sin producto más del 1 % del tiempo
    if b.empty_reps > 0 or (b.min_level_u > 0 and b.below_min_pct > 0.05):
        return "justo"
    return "ok"


def supermarket_checks(res: SimResult) -> List[SupermarketCheck]:
    """Dictamen de cada supermercado del mapa: aguanta / justo / no aguanta."""
    out = []
    stn = {s.name: s for s in res.stations}
    for b in res.buffers:
        if not b.is_super:
            continue
        v = _verdict(b)
        cons = stn.get(b.consumer)
        starved = cons.starved if cons else 0.0
        if v == "no":
            adv = (f"Se queda sin producto {b.empty_pct * 100:.1f} % del tiempo"
                   + (f" y «{b.consumer}» espera material {starved * 100:.0f} % del tiempo" if cons else "")
                   + ". Sube el nivel máximo (prueba «Probar otros tamaños»), acorta el tiempo de reposición o "
                     "ataca las fallas y la variabilidad del proceso que lo repone.")
        elif v == "justo":
            adv = (f"Casi siempre alcanza, pero se vació en {b.empty_reps * 100:.0f} % de las réplicas"
                   if b.empty_reps > 0 else
                   f"Nunca se vacía, pero pasa {b.below_min_pct * 100:.0f} % del tiempo bajo el mínimo "
                   f"({b.min_level_u:,.0f} u)") + ". El margen de seguridad es justo: no lo reduzcas."
        else:
            adv = f"Aguanta: nunca se vació; el nivel mínimo observado fue {b.min_u:,.0f} u de {b.capacity_u:,.0f}."
            if b.capacity_u > 0 and b.min_u > 0.35 * b.capacity_u:
                adv += (f" Sobra colchón: podrías reducir el máximo a ≈ {b.capacity_u - 0.8 * b.min_u:,.0f} u "
                        f"(verifícalo con «Probar otros tamaños»).")
        out.append(SupermarketCheck(b.node_id, b.name, v, b.capacity_u, b.min_level_u, b.avg_u, b.min_u, b.max_u,
                                    b.empty_pct, b.below_min_pct, b.empty_reps, b.consumer, starved, adv))
    return out


def sweep_supermarket(vmap: VSMMap, node_id: str, cfg: Optional[SimConfig] = None,
                      factors=(0.5, 0.75, 1.0, 1.5, 2.0, 3.0),
                      progress: Optional[Callable[[int, int], None]] = None) -> List[SweepPoint]:
    """Repite la simulación con otros niveles máximos del supermercado (× el actual) para ver dónde deja de vaciarse."""
    cfg = cfg or SimConfig()
    node = vmap.nodes.get(node_id)
    if node is None or node.kind != "supermarket":
        raise SimulationError("El nodo elegido no es un supermercado.")
    base = getattr(node, "max_level", 0.0) or node.quantity * cfg.cap_factor
    if base <= 0:
        raise SimulationError("El supermercado no tiene cantidad ni nivel máximo: edítalo primero.")
    pts = []
    sub = replace(cfg, replications=min(cfg.replications, 3))
    for i, f in enumerate(factors):
        if progress:
            progress(i, len(factors))
        m = VSMMap.from_dict(vmap.to_dict())
        m.nodes[node_id].max_level = float(round(base * f))
        r = simulate(m, sub)
        b = next(b for b in r.buffers if b.node_id == node_id)
        pts.append(SweepPoint(b.capacity_u, b.empty_pct, b.empty_reps, r.kpi.fill_rate, r.kpi.wip_units,
                              _verdict(b)))
    if progress:
        progress(len(factors), len(factors))
    return pts


# =============================================================================
# Lectura del resultado
# =============================================================================
def insights(res: SimResult) -> List[str]:
    """Hallazgos en lenguaje llano: lo que el VSM estático no puede decir."""
    k = res.kpi
    out: List[str] = list(res.warnings)
    if k.demand_day > 0:
        if k.fill_rate >= 0.98:
            out.append(f"Nivel de servicio {k.fill_rate * 100:.1f} %: el sistema atiende la demanda.")
        else:
            out.append(f"Nivel de servicio {k.fill_rate * 100:.1f} %: se pierden ≈ {k.lost_day:,.0f} u/día "
                       f"de {k.demand_day:,.0f} pedidas. El producto terminado se agota.")
    out.append(f"Lead time dinámico {k.lead_time_days:.1f} d (VSM estático: {res.static_lead_time_days:.1f} d). "
               f"PCE dinámico {k.pce * 100:.3f} % (estático: {res.static_pce * 100:.3f} %).")
    if res.stations:
        top = max(res.stations, key=lambda s: s.occupancy)
        out.append(f"Proceso más cargado: «{top.name}», ocupado {top.occupancy * 100:.0f} % del tiempo "
                   f"(trabajando {top.busy * 100:.0f} % + en falla {top.down * 100:.0f} %).")
        if res.capacity_day and res.capacity_day < 0.995 * k.demand_day:
            out.append(f"Capacidad: el proceso más lento solo permite ≈ {res.capacity_day:,.0f} u/día frente a "
                       f"{k.demand_day:,.0f} pedidas. Mientras haya inventario el déficit se disimula (revisa qué "
                       f"inventarios se vacían); cuando se agote, el servicio cae.")
        for s in res.stations:
            if s.starved >= 0.25:
                out.append(f"Inanición: «{s.name}» pasa {s.starved * 100:.0f} % del tiempo esperando material; "
                           f"lo que hay aguas arriba no le alcanza o le llega a saltos.")
            if s.blocked >= 0.10:
                out.append(f"Bloqueo: «{s.name}» pasa {s.blocked * 100:.0f} % del tiempo con la pieza lista y la "
                           f"salida llena; produce más de lo que el siguiente paso absorbe.")
    for b in res.buffers:
        if b.kind in ("transport", "edge") or b.is_super:
            continue
        if b.full_pct >= 0.30:
            out.append(f"«{b.name}» está lleno {b.full_pct * 100:.0f} % del tiempo: bloquea al paso anterior.")
        if b.empty_pct >= 0.30:
            out.append(f"«{b.name}» está vacío {b.empty_pct * 100:.0f} % del tiempo: deja sin material al paso "
                       f"siguiente.")
    for c in supermarket_checks(res):
        tag = {"ok": "Aguanta", "justo": "Justo", "no": "NO aguanta"}[c.verdict]
        out.append(f"Supermercado «{c.name}»: {tag}. {c.advice}")
    for s in res.stations:
        if s.idle >= 0.25:
            out.append(f"Pull: «{s.name}» espera la señal Kanban {s.idle * 100:.0f} % del tiempo; solo produce lo "
                       f"que se consume, y eso es lo esperado.")
    worst = max((b for b in res.buffers if b.kind != "transport"), key=lambda b: b.wait_days, default=None)
    if worst is not None and worst.wait_days > 0:
        out.append(f"Mayor espera: «{worst.name}» ≈ {worst.wait_days:.1f} d (el VSM estático calcula "
                   f"{worst.static_days:.1f} d).")
    return out
