"""Catálogo auditable: cada pictograma de las fuentes → símbolo implementado.

Fuentes: [L] libro «El mapa del flujo de valor» (J. Dumser) y [T] tabla de
símbolos VSM en español. Sin dependencias de PyQt5.

tipo: 'node' = símbolo de la paleta · 'conn' = tipo de flecha de la barra de herramientas
"""
from __future__ import annotations

# (nombre en la fuente, fuentes, tipo, clave)
CATALOG = [
    ("Cliente / Proveedor", "L T", "node", "supplier"),
    ("Cliente / Proveedor (lado cliente)", "L T", "node", "customer"),
    ("Proceso / Casilla de proceso", "L T", "node", "process"),
    ("Proceso compartido", "T", "node", "shared_process"),
    ("Celda de trabajo", "T", "node", "work_cell"),
    ("Operario", "L T", "node", "operator"),
    ("Datos / Tabla de datos de proceso", "L T", "node", "data_box"),
    ("Inventario", "L T", "node", "inventory"),
    ("Supermercado", "L T", "node", "supermarket"),
    ("Existencias de seguridad / Buffer o inventario de seguridad", "L T", "node", "safety_stock"),
    ("Punto de acumulación BUFFER (B)", "T", "node", "buffer_point"),
    ("Punto de acumulación STOCK DE SEGURIDAD (S)", "T", "node", "safety_point"),
    ("Entrega mediante camión / Transporte (camión, avión, barco)", "L T", "node", "transport"),
    ("Flecha de transporte o de movimiento de mercancías", "L", "node", "goods_arrow"),
    ("Flujo de MP y PT", "T", "node", "mp_pt_flow"),
    ("Pull físico / Flujo de materiales PULL", "L T", "node", "pull_physical"),
    ("Flecha push (empuje)", "L T", "conn", "push"),
    ("Flecha pull", "L", "conn", "pull"),
    ("Línea FIFO / Carril FIFO (flecha con «máx 20 uds»)", "L T", "conn", "fifo"),
    ("PEPS (FIFO) Lane (carril con capacidad máxima)", "T", "node", "fifo_lane"),
    ("Información manual", "L T", "conn", "info_manual"),
    ("Información electrónica", "L T", "conn", "info_electronic"),
    ("Teléfono", "L", "conn", "info_phone"),
    ("Control de la producción / planificación", "T", "node", "control"),
    ("Base de datos / Sistema MRP-ERP", "L T", "node", "database"),
    ("Información / Caja de información", "L T", "node", "info_box"),
    ("Producción Kanban / Kanban de producción", "L T", "node", "kanban_production"),
    ("Retirada Kanban", "T", "node", "kanban_withdrawal"),
    ("Batch Kanban / Lote de tarjetas Kanban", "L T", "node", "kanban_batch"),
    ("Señal Kanban", "L T", "node", "kanban_signal"),
    ("Tarjeta Kanban (poste de señales)", "T", "node", "kanban_post"),
    ("Nivelación de la carga (heijunka box, OXOX)", "L T", "node", "heijunka"),
    ("Secuencia de tiro/jalar - Pull Ball", "T", "node", "pull_ball"),
    ("Línea de tiempo / Segmento de tiempo", "L T", "node", "time_segment"),
    ("Tiempo total / Duración total", "L T", "node", "total_time"),
    ("Reloj", "L", "node", "clock"),
    ("Reelaboración", "L", "node", "rework"),
    ("Estallido Kaizen / Kaizen blits", "L T", "node", "kaizen"),
    ("Observación", "T", "node", "observation"),
]
