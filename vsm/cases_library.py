"""Biblioteca de casos. Cada caso es una empresa ficticia pero realista.

Para agregar un caso propio (p. ej. uno real anonimizado) crea un `Case` con estas
mismas piezas y añádelo a `ALL_CASES` al final del archivo. `problems(case)` (ver
case_model.py) valida que los datos del enunciado se puedan convertir sin error.

Convención de los datos "limpios": tiempos de ciclo en s por unidad, C/O en s,
disponibilidad en %, inventarios en unidades, tránsito en días laborales.
"""
from __future__ import annotations

from .case_model import Case, ProcSpec, InvSpec, TransSpec, STD_INFO
from .models import CaseParams


# ---- constructores compactos ------------------------------------------------
def P(name, ct, co=0, up=100, ops=1, sh=1, **kw):
    return ProcSpec(name, ct, co, up, ops, sh, **kw)


def I(qty, label="", style="units", **kw):
    return InvSpec(qty, label, style, **kw)


def T(name, days, mode="camion", note=""):
    return TransSpec(name, days, mode, note)


def PARAMS(demand, shifts, hours, unavailable_min):
    return CaseParams(demand, shifts, hours, unavailable_min)


def INFO(cust="pronóstico semanal por correo electrónico",
         sup="pedidos de compra por correo electrónico",
         prog="programación semanal impresa que se entrega a cada proceso",
         cust_kind="info_electronic", sup_kind="info_electronic", prog_kind="info_manual"):
    return [("customer", "control", cust_kind, cust),
            ("control", "supplier", sup_kind, sup),
            ("control", "procs", prog_kind, prog)]


# =============================================================================
# JUNIOR — 3 procesos, datos limpios, símbolos básicos
# =============================================================================
J1_PANADERIA = Case(
    id="panaderia", title="Panadería El Horno — Pan tajado", sector="Alimentos", level="Junior",
    story=("Panadería de barrio que abastece supermercados de la zona con <b>pan tajado</b>. El dueño siente que "
           "el horno «no da abasto» y que el pan se acumula empacado antes de salir."),
    params=PARAMS(1200, 1, 8, 30), unit="bolsa", supplier="Molino de harina", supplier_note="entrega diaria",
    steps=[I(2400, "Materias primas"), P("Amasado", 20, 300, 95, 2), I(600),
           P("Horneado", 24, 0, 90, 1), I(1200), P("Empaque", 15, 0, 98, 2), I(1200, "Producto terminado")],
    info_links=INFO(cust="pedidos diarios de los supermercados por correo electrónico",
                    sup="pedido de harina cada semana por correo electrónico",
                    prog="el panadero jefe reparte la programación del día en una hoja impresa"),
    objectives=["Dibujar un VSM de 3 procesos con inventarios entre ellos.",
                "Calcular el Takt Time a partir de demanda y jornada.",
                "Identificar el cuello de botella usando el tiempo de ciclo efectivo."],
    opportunities=["Aumentar la disponibilidad del horno (mantenimiento autónomo, limpieza en paralelo).",
                   "Sincronizar Amasado y Horneado con un flujo más continuo para bajar el inventario intermedio.",
                   "Reducir el inventario de producto terminado: el pan pierde frescura en bodega."])

J2_CAMISETAS = Case(
    id="camisetas", title="Taller Aurora — Camisetas estampadas", sector="Textil", level="Junior",
    story=("Taller familiar que produce <b>camisetas estampadas</b> para colegios y empresas. Los pedidos llegan "
           "por teléfono y la dueña programa el día a mano."),
    params=PARAMS(500, 1, 8, 60), unit="camiseta", supplier="Textiles del Valle", supplier_note="entrega quincenal",
    steps=[I(1000, "Tela"), P("Corte", 30, 120, 95, 1), I(500), P("Estampado", 60, 600, 90, 2), I(1000),
           P("Empaque", 25, 0, 100, 2), I(1500, "Producto terminado")],
    info_links=[("customer", "control", "info_phone", "el cliente hace sus pedidos por llamada telefónica"),
                ("control", "supplier", "info_phone", "las compras de tela se piden por teléfono"),
                ("control", "procs", "info_manual", "la dueña anota la programación del día en un tablero")],
    objectives=["Reconocer el flujo de información por teléfono y manual.",
                "Identificar un cuello de botella cuya causa es el tiempo de cambio."],
    opportunities=["Reducir el tiempo de cambio de estampado (SMED): 10 min por cambio es mucho para lotes pequeños.",
                   "Agregar capacidad o un segundo operario en Estampado en horas pico.",
                   "Bajar el inventario de producto terminado con programación por pedido."])

J3_PUERTAS = Case(
    id="puertas", title="Carpintería Roble — Puertas de interior", sector="Madera y muebles", level="Junior",
    story=("Carpintería que fabrica <b>puertas</b> para constructoras. Todos los tiempos son largos (minutos por puerta), "
           "así que el cuello de botella no es obvio: hay que comparar con el takt <i>después</i> de ajustar por "
           "disponibilidad."),
    params=PARAMS(60, 1, 8, 45), unit="puerta", supplier="Aserradero", supplier_note="entrega semanal",
    steps=[I(180, "Madera"), P("Corte y canteado", 300, 900, 92, 2), I(120), P("Ensamble", 420, 0, 95, 2), I(60),
           P("Lacado", 360, 600, 90, 1), I(120, "Producto terminado")],
    info_links=INFO(cust="pedidos de las constructoras por correo electrónico",
                    sup="pedido de madera cada semana por correo electrónico",
                    prog="el jefe de taller entrega una orden de trabajo impresa por lote"),
    objectives=["Ver por qué el tiempo de ciclo efectivo (TC / disponibilidad) cambia el diagnóstico.",
                "Calcular lead time con inventarios expresados en unidades."],
    opportunities=["Ensamble supera el takt por poco: una pequeña mejora de disponibilidad lo libera.",
                   "El inventario entre procesos oculta el problema; reducirlo lo haría visible.",
                   "Programar por pedido en lugar de por pronóstico semanal."])

# =============================================================================
# BLANCO — 4 procesos, datos limpios
# =============================================================================
B0_TABURETES = Case(
    id="taburetes", title="Laforêt SPRL — Taburetes", sector="Muebles", level="Blanco",
    story=("Laforêt es una pyme que fabrica muebles. Se analiza la familia de los <b>taburetes</b>: la dirección "
           "siente que los pedidos se entregan tarde y que hay mucho producto almacenado. (Caso inspirado en el "
           "ejemplo de <i>El mapa del flujo de valor</i>, J. Dumser)."),
    params=PARAMS(900, 2, 8, 30), unit="taburete", supplier="Proveedor de madera y pintura",
    steps=[T("Camión del proveedor", 0, "camion", "entrega semanal"), I(1800, "Materia prima"),
           P("Pintura", 60, 180, 90, 2, 2), I(1800), P("Montaje", 30, 100, 95, 1, 2), I(2700),
           P("Embalaje", 20, 0, 98, 1, 1), I(1800), P("Expedición", 20, 0, 100, 1, 2),
           I(9000, "Producto terminado")],
    info_links=INFO(cust="el cliente envía previsiones semanales por correo electrónico",
                    sup="los pedidos de compra se mandan al proveedor por fax",
                    prog="la programación de la semana se distribuye a cada puesto interno"),
    objectives=["Construir el VSM del estado actual siguiendo las fases del libro.",
                "Ver que el 99 % del lead time es espera y que el PCE es minúsculo."],
    opportunities=["Basarse en pedidos semanales reales en lugar de previsiones.",
                   "Crear un supermercado justo antes de Pintura y pasar a un sistema pull.",
                   "Reducir el cambio de Pintura (180 s) y eliminar los residuos asociados.",
                   "Combinar Embalaje y Expedición en un solo proceso."])

B1_CAFE = Case(
    id="cafe", title="Café Cumbre — Café tostado y molido 500 g", sector="Alimentos", level="Blanco",
    story=("Tostadora de café del Eje Cafetero que empaca <b>café molido de 500 g</b> para cadenas de supermercados. "
           "El café verde llega de una cooperativa y el cuello de botella parece estar en el empaque."),
    params=PARAMS(2400, 2, 8, 30), unit="bolsa", supplier="Cooperativa de caficultores",
    steps=[T("Camión — cooperativa", 1, "camion", "café pergamino"), I(7200, "Café verde"),
           P("Tostión", 12, 900, 88, 1, 2), I(2400), P("Molienda", 10, 300, 95, 1, 2), I(2400),
           P("Empaque", 21, 120, 90, 3, 2), I(4800), P("Embalaje", 8, 0, 100, 1, 2),
           I(7200, "Producto terminado")],
    info_links=INFO(cust="las cadenas envían pedidos semanales por correo electrónico",
                    sup="el pedido de café verde se hace por teléfono a la cooperativa",
                    prog="el supervisor reparte una hoja de programación impresa cada mañana",
                    sup_kind="info_phone"),
    objectives=["Incluir un transporte en el mapa de material.",
                "Combinar flujo de información electrónica, telefónica y manual."],
    opportunities=["Empaque es el cuello: revisar disponibilidad (paradas por cambio de rollo) y balancear operarios.",
                   "Reducir inventario de café verde negociando entregas más frecuentes.",
                   "Enlazar Tostión → Molienda con un carril FIFO en lugar de un inventario de 1 día."])

B2_YOGUR = Case(
    id="yogur", title="Lácteos La Vega — Yogur 1 L", sector="Lácteos", level="Blanco",
    story=("Planta de lácteos que produce <b>yogur de 1 litro</b>. Como es un producto refrigerado, los inventarios "
           "viven en cuartos fríos y hay un stock de seguridad para cubrir picos de demanda."),
    params=PARAMS(3000, 2, 8, 45), unit="botella", supplier="Ganaderos de la región",
    supplier_note="recolección diaria de leche",
    steps=[I(6000, "Leche cruda"), P("Pasteurización", 6, 1800, 95, 1, 2), I(3000, "Tanque de incubación"),
           P("Envasado", 17, 600, 90, 2, 2), I(3000), P("Sellado y etiquetado", 12, 300, 96, 2, 2), I(3000),
           P("Encajado", 9, 0, 98, 2, 2), I(3000, "Producto terminado"),
           I(3000, "Stock de seguridad", kind="safety_stock")],
    info_links=INFO(cust="las tiendas piden por el portal web cada semana",
                    sup="las órdenes de leche se envían por correo electrónico",
                    prog="la programación diaria se imprime y se cuelga en cada línea"),
    objectives=["Usar el símbolo de stock de seguridad (existencias reservadas)."],
    opportunities=["Envasado supera el takt: mejorar disponibilidad o agregar capacidad de llenado.",
                   "Reducir el stock de seguridad con un pronóstico más confiable.",
                   "Acercar Sellado y Encajado con un flujo continuo."])

B3_CALZADO = Case(
    id="calzado", title="Calzados Sol — Zapatilla escolar", sector="Calzado", level="Blanco",
    story=("Fábrica de <b>zapatillas escolares</b> con fuerte estacionalidad. Se analiza la referencia más vendida; "
           "los distribuidores recogen en la bodega con transportadoras."),
    params=PARAMS(800, 2, 8, 40), unit="par", plural="pares", supplier="Proveedores de insumos",
    supplier_note="entrega semanal",
    steps=[I(1600, "Materiales"), P("Corte", 40, 600, 92, 3, 2), I(1600), P("Guarnecido", 62, 300, 90, 8, 2),
           I(1200), P("Montaje", 50, 900, 94, 4, 2), I(800), P("Acabado y empaque", 30, 0, 97, 3, 2),
           I(2400, "Producto terminado"), T("Camión — distribuidor", 1, "camion")],
    info_links=INFO(cust="los distribuidores envían pedidos por correo electrónico",
                    sup="las órdenes de compra se envían por correo electrónico",
                    prog="la programación semanal se imprime para cada sección"),
    objectives=["Ubicar el transporte al cliente al final del flujo."],
    opportunities=["Guarnecido es el cuello (8 operarios): balancear la línea de costura.",
                   "Reducir inventarios intermedios entre Corte y Guarnecido.",
                   "Programar el despacho para evitar 3 días de producto terminado."])

# =============================================================================
# AMARILLO — unidades mezcladas, supermercados, carriles FIFO, Kanban
# =============================================================================
A0_FARMA = Case(
    id="farma", title="Andina Pharma — Tabletas de acetaminofén 500 mg", sector="Farmacéutico", level="Amarillo",
    story=("Laboratorio con planta de sólidos orales. La familia analizada es la de tabletas de acetaminofén 500 mg "
           "empacadas en <b>cajas</b> de 2 blísteres (los tiempos se expresan por caja equivalente). El lead time se "
           "dispara por las cuarentenas y retenciones de control de calidad exigidas por las BPM."),
    params=PARAMS(6000, 2, 8, 45), unit="caja", supplier="Proveedor de API y excipientes",
    supplier_note="entrega quincenal",
    steps=[T("Camión — materias primas", 0.5, "camion"), I(12000, "Materia prima en cuarentena", "days"),
           P("Pesaje y dispensación", 3, 900, 98, 2, 2), I(3000),
           P("Mezclado", 4, 1800, 95, 1, 2, ct_style="pph", co_style="min"), I(6000),
           P("Compresión", 6, 2400, 90, 2, 2, co_style="min"), I(6000, style="days"),
           P("Recubrimiento", 5, 3600, 92, 1, 2, ct_style="pph", co_style="min"),
           I(12000, "Retención de calidad en proceso", "days"),
           P("Blisteado", 9, 1200, 85, 3, 2, ct_style="pph", co_style="min"), I(6000),
           P("Empaque secundario", 7, 600, 95, 2, 2, co_style="min", up_style="downtime"),
           I(30000, "Producto terminado en cuarentena", "days")],
    extras=[("database", "ERP / LIMS", {}, "top")],
    info_links=[("customer", "control", "info_electronic", "el distribuidor envía su pronóstico mensual por correo electrónico"),
                ("customer", "control", "info_phone", "ajusta las urgencias con llamadas telefónicas semanales"),
                ("control", "supplier", "info_electronic", "las compras se emiten al proveedor por correo electrónico"),
                ("control", "erp", "info_electronic", "planeación libera las órdenes de producción desde el ERP"),
                ("control", "procs", "info_manual", "las órdenes de producción impresas se entregan a cada área")],
    notes=["Los tiempos de limpieza y verificación de línea ya están incluidos en el tiempo de cambio."],
    objectives=["Manejar unidades mezcladas (piezas/hora, minutos, días de demanda).",
                "Representar el ERP y los distintos tipos de flujo de información."],
    opportunities=["Blisteado es el cuello: SMED en cambios (20 min) y mejora de disponibilidad (85 %).",
                   "Las cuarentenas de calidad dominan el lead time: liberar por muestreo/RFT donde la norma lo permita.",
                   "Enlazar Compresión y Recubrimiento con un carril FIFO en lugar de 1 día de inventario."])

A1_SHAMPOO = Case(
    id="shampoo", title="Cosméticos Brisa — Shampoo 400 ml", sector="Cuidado personal", level="Amarillo",
    story=("Planta que fabrica <b>shampoo de 400 ml</b> en lotes de mezcla que alimentan una línea de llenado. "
           "Entre Llenado y Etiquetado ya existe un carril FIFO de capacidad limitada."),
    params=PARAMS(9000, 3, 8, 40), unit="frasco", supplier="Proveedores de materias primas",
    supplier_note="entrega semanal",
    steps=[I(18000, "Materias primas", "days"),
           P("Mezcla", 3, 1800, 93, 2, 3, ct_style="batch", batch=1200, co_style="min"), I(4500),
           P("Llenado", 8, 900, 88, 3, 3, ct_style="pph", co_style="min"),
           I(600, "Carril FIFO", kind="fifo_lane", capacity=900),
           P("Etiquetado", 6, 300, 95, 2, 3, ct_style="pph", co_style="min"), I(3000),
           P("Encajado", 5, 0, 97, 2, 3), I(27000, "Producto terminado", "days")],
    info_links=INFO(cust="la cadena de supermercados envía su pronóstico por EDI",
                    sup="las compras se hacen por correo electrónico",
                    prog="la programación diaria se imprime y se entrega a cada línea"),
    objectives=["Usar el carril FIFO y ver que limita el flujo entre dos procesos.",
                "Leer un tiempo de ciclo expresado por lote."],
    opportunities=["Llenado es el cuello: bajar cambios de formato y subir disponibilidad.",
                   "Extender el FIFO a Mezcla → Llenado para reducir el inventario de 0.5 días.",
                   "Reducir 3 días de producto terminado con entregas más frecuentes."])

A2_JUGOS = Case(
    id="jugos", title="Jugos Tropicales — Jugo de mango 1 L", sector="Bebidas", level="Amarillo",
    story=("Planta que procesa <b>jugo de mango de 1 litro</b>. La fruta llega en camión y el jugo pasteurizado se "
           "almacena en un <b>supermercado</b> del que Llenado y tapado retira con tarjetas Kanban."),
    params=PARAMS(12000, 2, 8, 45), unit="botella", supplier="Frutícolas del Tolima",
    supplier_note="entrega diaria de fruta",
    steps=[T("Camión — fruta", 0.5, "camion"), I(12000, "Fruta y pulpa", "days"),
           P("Preparación", 3, 1200, 90, 4, 2, co_style="min"), I(6000),
           P("Pasteurización", 2, 1800, 96, 1, 2, ct_style="pph", co_style="min"),
           I(3000, "Supermercado de jugo pasteurizado", kind="supermarket"),
           P("Llenado y tapado", 4, 900, 88, 4, 2, ct_style="pph", co_style="min"), I(6000),
           P("Etiquetado", 3, 0, 95, 2, 2, ct_style="pph"), I(12000),
           P("Paletizado", 2, 0, 98, 2, 2), I(24000, "Producto terminado", "days"),
           T("Camión — distribuidor", 0.5, "camion")],
    extras=[("kanban_withdrawal", "Retirada Kanban", {"value": 600}, 5)],
    info_links=INFO(cust="el distribuidor envía pedidos diarios por EDI",
                    sup="el comprador llama al proveedor cada mañana para confirmar la fruta",
                    prog="el supervisor entrega el plan de producción en papel",
                    sup_kind="info_phone"),
    objectives=["Representar un supermercado con retirada Kanban (flecha pull).",
                "Distinguir flechas push y pull en el mismo mapa."],
    opportunities=["Llenado y tapado es el cuello: mejorar disponibilidad de la llenadora.",
                   "Extender el sistema pull al resto de la línea (Etiquetado y Paletizado).",
                   "Reducir 2 días de producto terminado alineando despachos a la demanda."])

A3_ELECTRONICA = Case(
    id="electronica", title="ElectroNova — Tarjeta controladora", sector="Electrónica", level="Amarillo",
    story=("Ensambladora de <b>tarjetas controladoras</b> para electrodomésticos. Los componentes llegan por vía aérea y "
           "la línea SMT trabaja con carriles FIFO. El cuello parece estar en la prueba funcional."),
    params=PARAMS(2000, 2, 8, 60), unit="tarjeta", supplier="Distribuidores de componentes",
    supplier_note="importación quincenal",
    steps=[T("Avión — componentes", 3, "avion"), I(6000, "Componentes", "days"),
           P("Impresión de pasta", 12, 600, 96, 1, 2, ct_style="pph", co_style="min"),
           I(200, "Carril FIFO", kind="fifo_lane", capacity=300),
           P("Colocación SMT", 20, 1200, 90, 2, 2, ct_style="pph", co_style="min"),
           I(200, "Carril FIFO", kind="fifo_lane", capacity=300), P("Reflujo", 15, 0, 98, 1, 2), I(1000),
           P("Inspección óptica (AOI)", 18, 0, 95, 1, 2, ct_style="pph"), I(1000),
           P("Prueba funcional", 26, 300, 95, 4, 2, co_style="min"), I(1000),
           P("Ensamble en carcasa", 14, 0, 97, 3, 2), I(4000, "Producto terminado", "days")],
    extras=[("database", "MES / ERP", {}, "top")],
    info_links=[("customer", "control", "info_electronic", "el cliente transmite su programa de requerimientos por EDI"),
                ("control", "supplier", "info_electronic", "las órdenes de compra se envían por correo electrónico"),
                ("control", "erp", "info_electronic", "el MES/ERP consolida planes y órdenes"),
                ("control", "procs", "info_electronic", "la programación aparece en las pantallas de cada estación")],
    objectives=["Representar el transporte aéreo y un sistema MES/ERP.",
                "Cadenas de proceso enlazadas por carriles FIFO."],
    opportunities=["Prueba funcional es el cuello: agregar un banco de pruebas o reducir tiempo de ciclo de prueba.",
                   "Los 3 días de tránsito aéreo + 3 días de inventario de componentes son la mayor espera.",
                   "Ampliar el flujo continuo con FIFO hasta AOI."])

A4_BOLSAS = Case(
    id="bolsas", title="PlastiEmpaques — Bolsas plásticas impresas", sector="Plásticos", level="Amarillo",
    story=("Fábrica de <b>bolsas plásticas impresas</b> (unidad: paquete de 100 bolsas). Opera 24 horas. Entre "
           "Impresión y Sellado se mantiene un buffer para desacoplar los cambios de tinta."),
    params=PARAMS(4000, 3, 8, 30), unit="paquete", supplier="Petroquímica nacional",
    supplier_note="entrega semanal de resina",
    steps=[I(8000, "Resina", "days"), P("Extrusión", 15, 3600, 85, 2, 3, co_style="min"), I(4000),
           P("Impresión", 19, 2400, 90, 2, 3, co_style="min"),
           I(8000, "Buffer de impresión", "days", kind="buffer_point"),
           P("Sellado y corte", 10, 900, 94, 2, 3, ct_style="pph", co_style="min"), I(4000),
           P("Empaque", 8, 0, 99, 3, 3), I(12000, "Producto terminado", "days")],
    info_links=[("customer", "control", "info_phone", "los clientes hacen sus pedidos por teléfono"),
                ("control", "supplier", "info_electronic", "las compras se envían por correo electrónico"),
                ("control", "procs", "info_manual", "la programación se cuelga en tableros impresos")],
    objectives=["Reconocer el símbolo de buffer (protección frente a variación)."],
    opportunities=["Impresión es el cuello: SMED en cambios de tinta (40 min) y mejorar disponibilidad.",
                   "El buffer de 2 días protege la impresión pero alarga el lead time.",
                   "Reducir 3 días de producto terminado."])

# =============================================================================
# VERDE — procesos compartidos, celdas, lotes, paradas, demanda semanal
# =============================================================================
V0_AUTOPARTES = Case(
    id="autopartes", title="Metalmecánica Cafetera — Soporte de motor SM-220", sector="Autopartes", level="Verde",
    story=("Proveedor Tier-2 de una ensambladora automotriz. La referencia <b>SM-220</b> es su producto estrella y el "
           "cliente amenaza con reducir volúmenes si no mejoran las entregas. Soldadura opera en una celda robotizada y "
           "la pintura es una línea compartida con otras referencias."),
    params=PARAMS(1200, 3, 8, 40), unit="pieza", supplier="Acería regional",
    supplier_note="entrega semanal de lámina",
    steps=[T("Camión — acería", 0.5, "camion"), I(2400, "Lámina", "days"),
           P("Corte láser", 24, 600, 92, 1, 3, ct_style="pph", co_style="min", up_style="downtime"), I(3600),
           P("Estampado", 54, 1800, 88, 2, 3, ct_style="batch", batch=50, co_style="min"), I(2400, style="days"),
           P("Soldadura", 60, 300, 90, 3, 3, ct_style="min", co_style="min", kind="work_cell"), I(1200),
           P("Pintura electroestática", 40, 900, 95, 2, 2, ct_style="pph", co_style="min", kind="shared_process"),
           I(1800, style="days"), P("Ensamble final", 50, 0, 97, 4, 3), I(600),
           P("Inspección y embalaje", 18, 0, 99, 2, 3, ct_style="pph"), I(6000, "Producto terminado", "days"),
           T("Camión — ensambladora", 0.5, "camion")],
    info_links=INFO(cust="el cliente transmite su programa de requerimientos por EDI",
                    sup="planeación emite pedidos al proveedor por correo electrónico",
                    prog="la programación diaria se entrega en papel a cada estación"),
    notes=["El área de mantenimiento y el almacén de herramientas no participan en el flujo de la familia.",
           "El 2 % de las piezas requiere retrabajo en soldadura; para este ejercicio se ignora."],
    objectives=["Representar una celda de trabajo y un proceso compartido.",
                "Detectar un cuello con muy poco margen sobre el takt."],
    opportunities=["Soldadura supera el takt por poco: 1 punto de disponibilidad la libera.",
                   "La pintura compartida obliga a lotes: coordinar la secuencia con las otras referencias.",
                   "Reducir 5 días de producto terminado con un supermercado pull hacia la ensambladora."])

V1_TORNILLOS = Case(
    id="tornillos", title="Tornillos del Norte — Tornillo hexagonal M8", sector="Metalmecánica", level="Verde",
    story=("Fabricante de <b>tornillos hexagonales M8</b> (unidad: millar). El tratamiento térmico se comparte con otras "
           "familias y trabaja por lotes; el cabeceado parece ser el cuello."),
    params=PARAMS(90, 3, 8, 45), unit="millar", plural="millares", supplier="Trefiladora nacional",
    supplier_note="entrega semanal de alambrón",
    steps=[T("Camión — alambrón", 1, "camion"), I(270, "Alambrón", "days"),
           P("Trefilado", 600, 3600, 90, 1, 3, ct_style="min", co_style="min"), I(180, style="days"),
           P("Cabeceado", 780, 2700, 88, 2, 3, ct_style="min", co_style="min"), I(90, style="days"),
           P("Roscado", 720, 1800, 92, 2, 3, ct_style="min", co_style="min"),
           I(360, "Espera de tratamiento térmico", "days"),
           P("Tratamiento térmico", 300, 0, 95, 2, 3, ct_style="batch", batch=10, kind="shared_process"),
           I(180, style="days"), P("Galvanizado", 540, 1200, 85, 3, 3, ct_style="min", co_style="min"), I(90),
           P("Selección y empaque", 400, 0, 97, 3, 3), I(270, "Producto terminado", "days")],
    info_links=INFO(cust="el cliente transmite su programa por EDI",
                    sup="las compras de alambrón se envían por correo electrónico",
                    prog="cada lote viaja con una tarjeta de ruta física"),
    notes=["El horno de tratamiento térmico atiende otras 4 familias; aquí solo se considera el tiempo dedicado a esta."],
    objectives=["Leer tiempos por lote y por millar.",
                "Reconocer un proceso compartido como fuente de espera."],
    opportunities=["Cabeceado es el cuello: mejorar disponibilidad y cambio de matriz (45 min).",
                   "El tratamiento térmico compartido genera 4 días de espera: lotes más pequeños y programación conjunta.",
                   "Reducir 3 días de producto terminado."])

V2_JEANS = Case(
    id="jeans", title="Denim Antioquia — Jean cinco bolsillos", sector="Confección", level="Verde",
    story=("Confeccionista de <b>jeans</b> con una célula de costura de 8 operarias y una lavandería compartida con "
           "otras marcas. Los pedidos y la producción se planean por semana."),
    params=PARAMS(1000, 2, 8, 45), unit="jean", supplier="Textileras de Medellín",
    supplier_note="entrega semanal de denim",
    demand_text="5,000 jeans por semana (5 días laborales)",
    steps=[I(3000, "Tela denim", "days"), P("Tendido y corte", 25, 300, 93, 4, 2), I(2000, style="days"),
           P("Costura", 50, 900, 95, 8, 2, co_style="min", kind="work_cell"),
           I(3000, "Cola de lavandería", "days"),
           P("Lavandería", 30, 1800, 85, 3, 2, ct_style="pph", co_style="min", kind="shared_process"), I(1000),
           P("Terminación", 40, 0, 96, 6, 2, ct_style="pph"), I(1000),
           P("Empaque", 15, 0, 98, 2, 2, ct_style="pph"), I(4000, "Producto terminado", "days"),
           T("Camión — distribuidor", 1, "camion")],
    info_links=INFO(cust="los almacenes envían pedidos semanales por correo electrónico",
                    sup="el comprador pide tela por correo electrónico",
                    prog="la programación semanal se entrega en papel a cada sección"),
    objectives=["Convertir demanda semanal a diaria.",
                "Representar una celda de costura y una lavandería compartida."],
    opportunities=["La célula de costura apenas supera el takt: balancear operaciones dentro de la célula.",
                   "La cola de lavandería (3 días) es la mayor espera: lavar por lotes más pequeños y frecuentes.",
                   "Reducir 4 días de producto terminado."])

V3_FUNDICION = Case(
    id="fundicion", title="Fundiciones Andinas — Carcasa de bomba", sector="Fundición", level="Verde",
    story=("Fundición de aluminio que produce <b>carcasas de bomba</b>. El mecanizado CNC se realiza en una celda de "
           "trabajo y el cliente ajusta sus pedidos con frecuencia."),
    params=PARAMS(400, 3, 8, 40), unit="pieza", supplier="Recicladores de chatarra", supplier_note="entrega semanal",
    steps=[T("Camión — chatarra", 1, "camion"), I(1200, "Chatarra y arena", "days"),
           P("Fundición", 150, 3600, 85, 3, 3, co_style="min"), I(800, style="days"),
           P("Desbarbado", 90, 0, 95, 4, 3), I(1200, style="days"),
           P("Mecanizado CNC", 180, 1800, 88, 3, 3, co_style="min", kind="work_cell"), I(800),
           P("Pintura", 120, 600, 92, 2, 3, co_style="min"), I(400),
           P("Inspección y embalaje", 100, 0, 98, 2, 3), I(2000, "Producto terminado", "days"),
           T("Camión — cliente", 1, "camion")],
    info_links=[("customer", "control", "info_electronic", "el cliente envía el programa mensual por EDI"),
                ("customer", "control", "info_phone", "y ajusta cantidades semanalmente por teléfono"),
                ("control", "supplier", "info_electronic", "planeación pide chatarra por correo electrónico"),
                ("control", "procs", "info_manual", "la programación diaria se entrega en papel")],
    notes=["Se ignora el retrabajo por porosidad (1.5 %)."],
    objectives=["Manejar dos flujos de información desde el cliente.",
                "Ver el efecto de inventarios intermedios de 2–3 días."],
    opportunities=["Mecanizado CNC es el cuello: SMED en cambios (30 min) y programación de herramientas.",
                   "Conectar Fundición y Desbarbado con un FIFO reduciría 2 días de espera.",
                   "5 días de producto terminado sugieren pasar a entregas por pull."])

V4_LAB = Case(
    id="lab-clinico", title="Laboratorio Clínico Central — Exámenes de sangre", sector="Servicios de salud",
    level="Verde",
    story=("Laboratorio que procesa <b>muestras de sangre</b> de varias sedes. El flujo es de servicio: no hay materia "
           "prima ni producto terminado, pero sí colas. El autoanalizador se comparte con el área de urgencias."),
    params=PARAMS(800, 3, 8, 60), unit="muestra", supplier="Sedes y consultorios",
    supplier_note="recolección cada 2 horas", customer="Médicos y pacientes",
    control_name="Coordinación del laboratorio",
    steps=[I(400, "Muestras en recepción"), P("Registro y rotulado", 60, 0, 98, 4, 3, ct_style="pph"), I(250),
           P("Centrifugado", 45, 0, 95, 2, 3, ct_style="pph"), I(300, "Cola de analizadores"),
           P("Análisis en autoanalizador", 90, 600, 92, 2, 3, ct_style="pph", co_style="min", kind="shared_process"),
           I(200), P("Validación y reporte", 40, 0, 99, 2, 3, ct_style="pph"),
           I(160, "Resultados pendientes de entrega"), P("Entrega de resultados", 30, 0, 100, 2, 3, ct_style="pph")],
    extras=[("database", "LIS (sistema del laboratorio)", {}, "top")],
    info_links=[("customer", "control", "info_electronic", "las órdenes médicas llegan por el sistema LIS"),
                ("control", "supplier", "info_phone", "la recolección de muestras se coordina por teléfono"),
                ("control", "erp", "info_electronic", "el LIS registra y asigna trabajo"),
                ("control", "procs", "info_electronic", "el LIS asigna la cola de trabajo de cada estación")],
    notes=["Las pruebas urgentes (8 %) se atienden fuera de la cola normal; ignóralas."],
    objectives=["Aplicar VSM a un servicio: las colas son inventarios.",
                "Representar un equipo compartido (autoanalizador)."],
    opportunities=["El autoanalizador es el cuello y además es compartido: separar la cola de urgencias.",
                   "Reducir la cola de analizadores con lotes de menor tamaño y carga continua.",
                   "Automatizar la entrega de resultados por portal para eliminar esa espera."])

# =============================================================================
# ROJO — sistemas pull en el estado actual, OEE, demanda mensual, pallets
# =============================================================================
R1_BICICLETAS = Case(
    id="bicicletas", title="BiciAndes — Bicicleta urbana", sector="Ensamble de vehículos", level="Rojo",
    story=("Ensambladora de <b>bicicletas urbanas</b>. Los componentes de transmisión se importan por barco. La línea de "
           "ensamble ya se abastece con un <b>supermercado</b> y tarjetas Kanban; la pintura se hace en una cabina "
           "compartida."),
    params=PARAMS(200, 1, 8, 30), unit="bicicleta", supplier="Proveedores de cuadros y transmisión",
    supplier_note="importación mensual",
    demand_text="4,400 bicicletas por mes (22 días laborales)",
    steps=[T("Barco — grupo de transmisión", 6, "barco", "componentes importados"),
           I(1200, "Componentes importados", "pallets", pack=50),
           P("Soldadura de cuadros", 110, 1800, 90, 3, 1, co_style="min"), I(400, style="days"),
           P("Pintura", 90, 2400, 80, 2, 1, co_style="min", up_style="oee", perf=95, quality=97,
             kind="shared_process"),
           I(600, "Supermercado de componentes y cuadros", "days", kind="supermarket"),
           P("Ensamble en línea", 130, 600, 92, 6, 1, co_style="min", kind="work_cell"),
           I(100, "Carril FIFO", kind="fifo_lane", capacity=120),
           P("Inspección y ajuste", 60, 0, 98, 2, 1, ct_style="pph"), I(1000, "Producto terminado", "days")],
    extras=[("database", "ERP", {}, "top"),
            ("kanban_withdrawal", "Retirada Kanban", {"value": 20}, 5),
            ("kanban_signal", "Señal Kanban", {"value": 200}, 5)],
    info_links=[("customer", "control", "info_electronic", "los distribuidores emiten pedidos mensuales por el ERP"),
                ("customer", "control", "info_phone", "y hacen ajustes semanales por teléfono"),
                ("control", "supplier", "info_electronic", "las órdenes de importación se envían por correo electrónico"),
                ("control", "erp", "info_electronic", "planeación programa desde el ERP"),
                ("control", "procs", "info_manual", "la programación diaria se entrega en papel")],
    notes=["Pintura opera con OEE: recuerda que el tiempo de ciclo efectivo solo usa la <b>disponibilidad</b>."],
    objectives=["Representar un pull ya existente (supermercado + Kanban).",
                "Separar disponibilidad de rendimiento y calidad dentro del OEE."],
    opportunities=["Ensamble en línea es el cuello: balancear las 6 posiciones y reducir el cambio de modelo.",
                   "El tránsito marítimo y el inventario de componentes suman 12 días: negociar lotes menores.",
                   "Extender el pull hacia Pintura con otro supermercado en lugar de push."])

R2_CERVEZA = Case(
    id="cerveza", title="Cervecería Montaña — Cerveza 330 ml", sector="Bebidas", level="Rojo",
    story=("Cervecería artesanal industrial que envasa <b>cerveza de 330 ml</b> en cajas de 24 botellas. La fermentación "
           "en tanques ocupa 14 días y domina el lead time; la línea de envasado es el punto crítico en piso."),
    params=PARAMS(12000, 3, 8, 60), unit="caja", supplier="Maltería y proveedores de lúpulo",
    supplier_note="entrega semanal",
    demand_text="72,000 cajas por semana (6 días operativos)",
    steps=[T("Camión — malta y lúpulo", 1, "camion"), I(36000, "Malta y lúpulo", "days"),
           P("Cocción", 2, 3600, 92, 2, 3, ct_style="batch", batch=1800, co_style="min"),
           I(168000, "Fermentación y maduración (tanques)", "days"),
           P("Filtración", 3, 1800, 90, 2, 3, ct_style="pph", co_style="min"),
           I(12000, "Tanque de cerveza filtrada", "days", kind="buffer_point"),
           P("Envasado", 6, 1200, 88, 6, 3, ct_style="pph", co_style="min", up_style="oee", perf=93, quality=98),
           I(900, "Carril FIFO", kind="fifo_lane", capacity=1200),
           P("Pasteurización de túnel", 5, 0, 95, 2, 3, ct_style="pph"), I(3000),
           P("Empacado", 4, 0, 96, 4, 3, ct_style="pph"), I(36000, "Producto terminado", "days"),
           T("Camión — distribuidor", 1, "camion")],
    extras=[("database", "SCADA / ERP", {}, "top")],
    info_links=[("customer", "control", "info_electronic", "los distribuidores envían pedidos semanales por EDI"),
                ("control", "supplier", "info_electronic", "las compras de malta se envían por correo electrónico"),
                ("control", "erp", "info_electronic", "el ERP libera órdenes y el SCADA reporta"),
                ("control", "procs", "info_electronic", "el SCADA muestra el plan de cada equipo")],
    notes=["La fermentación es un tiempo tecnológico inevitable: represéntala como espera y analiza el resto."],
    objectives=["Convertir demanda semanal (6 días operativos) a diaria.",
                "Ver cómo un tiempo tecnológico domina el lead time y el PCE."],
    opportunities=["Envasado es el cuello (OEE 80 %): atacar paradas menores y cambios de formato.",
                   "Cerca del 60 % del lead time es fermentación (14 de 23 días): tenerlo presente y no perseguirlo con Lean de piso.",
                   "Reducir 3 días de producto terminado y el buffer de cerveza filtrada."])

R3_O2C = Case(
    id="pedido-a-cobro", title="Distribuciones del Sol — Del pedido al despacho", sector="Servicios administrativos",
    level="Rojo",
    story=("Distribuidor mayorista que quiere entender por qué un <b>pedido</b> tarda tanto en llegar al cliente. "
           "El flujo es administrativo (registro, crédito, facturación, alistamiento): las colas de documentos son "
           "inventarios y el área de crédito atiende varias sucursales."),
    params=PARAMS(300, 1, 8, 60), unit="pedido", supplier="Fuerza de ventas", supplier_note="pedidos de la ruta",
    customer="Clientes (tiendas)", control_name="Jefatura de servicio al cliente",
    demand_text="6,600 pedidos por mes (22 días hábiles)",
    steps=[I(600, "Pedidos recibidos (bandeja)", "days"),
           P("Registro del pedido", 60, 0, 95, 4, 1, ct_style="pph"), I(450, style="days"),
           P("Validación de crédito", 72, 0, 92, 3, 1, ct_style="pph", kind="shared_process"), I(500),
           P("Facturación", 90, 0, 96, 4, 1, ct_style="pph"), I(300, "Facturas pendientes de alistar"),
           P("Alistamiento y despacho", 80, 0, 98, 6, 1, ct_style="pph"),
           T("Transportadora — entrega", 1, "camion")],
    extras=[("database", "ERP", {}, "top")],
    info_links=[("customer", "control", "info_electronic", "los clientes ordenan por el portal web"),
                ("customer", "control", "info_phone", "algunos piden por línea telefónica"),
                ("control", "erp", "info_electronic", "el ERP registra pedidos y facturas"),
                ("control", "procs", "info_electronic", "el ERP asigna la cola de trabajo de cada área")],
    notes=["La reprogramación de pedidos rechazados por crédito (6 %) se ignora en este ejercicio."],
    objectives=["Aplicar VSM a un proceso administrativo.",
                "Manejar tiempos expresados como pedidos por hora."],
    opportunities=["Facturación es el cuello: automatizar la facturación por lotes o por excepción.",
                   "Crédito es un área compartida y deja 1.5 días de cola antes de validar: reglas de aprobación automática para clientes buenos.",
                   "Reducir la bandeja de pedidos recibidos con recepción continua."])

# =============================================================================
# NEGRO — flujos complejos, avión/barco, buffers, datos trampa
# =============================================================================
N1_AERO = Case(
    id="aeronautica", title="AeroPartes — Panel de fuselaje", sector="Aeronáutica", level="Negro",
    story=("Proveedor aeronáutico de <b>paneles de fuselaje</b> de aluminio. La lámina llega por avión y el producto "
           "final se exporta por barco. Dos operaciones son compartidas con otros programas y el mecanizado se hace "
           "en una celda de trabajo. Los datos vienen de fuentes distintas y en unidades mezcladas."),
    params=PARAMS(40, 2, 8, 60), unit="panel", plural="paneles", supplier="Productor de aluminio aeronáutico",
    supplier_note="importación mensual",
    demand_text="880 paneles por mes (22 días laborales)",
    steps=[T("Avión — lámina aeronáutica", 3, "avion"),
           I(200, "Lámina de aluminio", "pallets", pack=20),
           P("Corte CNC", 600, 3600, 90, 2, 2, ct_style="min", co_style="min"), I(120, style="days"),
           P("Conformado", 900, 5400, 85, 3, 2, ct_style="min", co_style="min"),
           I(100, "Cola de tratamiento térmico", "days"),
           P("Tratamiento térmico", 1080, 0, 92, 2, 2, ct_style="batch", batch=20, kind="shared_process"),
           I(160, "Buffer previo a mecanizado", "days", kind="buffer_point"),
           P("Mecanizado", 1150, 3600, 90, 4, 2, co_style="min", up_style="oee", perf=92, quality=97,
             kind="work_cell"),
           I(60, style="days"),
           P("Anodizado", 480, 1800, 88, 2, 2, ct_style="min", co_style="min", kind="shared_process"),
           I(80, style="days"), P("Remachado y ensamble", 900, 0, 95, 6, 2, ct_style="min"), I(40, style="days"),
           P("Inspección NDT", 600, 0, 93, 2, 2, ct_style="min"),
           I(200, "Producto terminado", "days", kind="safety_stock"),
           T("Barco — exportación", 8, "barco")],
    extras=[("database", "ERP / MRP", {}, "top")],
    info_links=[("customer", "control", "info_electronic", "el cliente transmite su programa por EDI"),
                ("control", "supplier", "info_electronic", "las órdenes de compra se envían por correo electrónico"),
                ("control", "erp", "info_electronic", "el MRP libera órdenes de trabajo"),
                ("control", "procs", "info_manual", "cada panel viaja con una hoja de ruta impresa")],
    notes=["El ERP indica un tiempo de ciclo de 1,200 s para Mecanizado, pero la medición en piso es la que aparece en la tabla: usa la tabla.",
           "La inspección NDT de una muestra del 5 % de lotes se realiza en un laboratorio externo; se ignora."],
    objectives=["Manejar 7 procesos con 2 compartidos, una celda, un buffer y stock de seguridad.",
                "Distinguir datos del ERP de mediciones en piso."],
    opportunities=["Mecanizado apenas supera el takt (OEE 80 %): SMED y mejorar disponibilidad.",
                   "Coordinar los dos procesos compartidos con otros programas para reducir colas.",
                   "Los 8 días de barco son inevitables: reducir inventario y stock de seguridad para bajar el resto."])

N2_INYECTABLES = Case(
    id="inyectables", title="Andina Pharma — Ampollas inyectables", sector="Farmacéutico", level="Negro",
    story=("Línea de <b>inyectables estériles</b> (unidad: caja de 10 ampollas). El producto permanece en cuarentena "
           "hasta la liberación de esterilidad y hay buffers y stocks de seguridad exigidos por la política de "
           "calidad. El llenado aséptico es crítico, pero la inspección visual queda muy cerca del takt."),
    params=PARAMS(5000, 3, 8, 60), unit="caja", supplier="Proveedores de insumos y ampollas",
    supplier_note="entrega mensual",
    steps=[T("Camión — insumos", 1, "camion"), I(15000, "Insumos en cuarentena", "days"),
           P("Preparación de solución", 2, 7200, 90, 3, 3, ct_style="batch", batch=1800, co_style="min"),
           I(5000, "Buffer de solución", "days", kind="buffer_point"),
           P("Lavado y despirogenado", 4, 3600, 90, 2, 3, ct_style="pph", co_style="min"),
           I(500, "Carril FIFO", kind="fifo_lane", capacity=800),
           P("Llenado aséptico", 12, 5400, 78, 4, 3, ct_style="pph", co_style="min", up_style="oee",
             perf=94, quality=99),
           I(5000, style="days"), P("Inspección visual 100 %", 14, 0, 95, 10, 3),
           I(35000, "Cuarentena hasta liberación de calidad", "days"),
           P("Etiquetado y serialización", 6, 1200, 96, 3, 3, co_style="min"), I(5000, style="days"),
           P("Empaque secundario", 8, 0, 97, 3, 3),
           I(15000, "Stock de seguridad", "days", kind="safety_point"),
           I(15000, "Producto terminado", "days", kind="safety_point")],
    extras=[("database", "ERP / LIMS", {}, "top")],
    info_links=[("customer", "control", "info_electronic", "el operador logístico envía el programa de distribución por EDI"),
                ("customer", "control", "info_phone", "las urgencias hospitalarias se solicitan por teléfono"),
                ("control", "supplier", "info_electronic", "las compras se emiten al proveedor por correo electrónico"),
                ("control", "erp", "info_electronic", "el ERP/LIMS libera lotes y órdenes"),
                ("control", "procs", "info_manual", "los registros de lote (batch record) impresos acompañan cada orden")],
    notes=["Las pruebas de esterilidad toman 7 días; ese tiempo ya está incluido en la cuarentena.",
           "La OEE de Llenado incluye rendimiento y calidad; para el tiempo de ciclo efectivo solo cuenta la disponibilidad."],
    objectives=["Modelar cuarentenas, buffers, stocks de seguridad y carriles FIFO en un mismo mapa.",
                "Evitar el error de usar OEE completo en lugar de disponibilidad."],
    opportunities=["Llenado aséptico es el cuello (disponibilidad 78 %): limitar intervenciones y acortar cambios.",
                   "La cuarentena de esterilidad (7 días) domina el lead time: métodos rápidos validados.",
                   "Reducir los dos stocks de seguridad al final del flujo."])

N3_FLORES = Case(
    id="flores", title="Flores del Oriente — Ramos de exportación", sector="Agroindustria", level="Negro",
    story=("Floricultora del Oriente antioqueño que exporta <b>ramos de rosas</b> a Estados Unidos. El producto es "
           "perecedero: los inventarios son de horas, el armado se hace en una celda de trabajo y hay cuarto frío. "
           "Todo el lead time es de días y la variabilidad viene del clima."),
    params=PARAMS(6000, 2, 8, 45), unit="ramo", supplier="Invernaderos propios", supplier_note="corte diario",
    demand_text="150,000 tallos por día; cada ramo lleva 25 tallos",
    steps=[I(6000, "Flor lista para corte en campo", "days"), P("Corte y acopio", 7, 0, 95, 60, 2), I(3000, style="days"),
           P("Clasificación y selección", 6, 0, 96, 40, 2, ct_style="pph"), I(3000, style="days"),
           P("Armado de ramos", 8, 300, 90, 30, 2, ct_style="pph", co_style="min", kind="work_cell"),
           I(3000, style="days"), P("Hidratación y empaque", 5, 0, 97, 12, 2, ct_style="pph"),
           I(6000, "Cuarto frío", "days", kind="safety_stock"),
           T("Camión — aeropuerto", 0.5, "camion"), I(6000, "Carga en aeropuerto", "days"),
           T("Avión — Miami", 1, "avion")],
    info_links=[("customer", "control", "info_electronic", "las órdenes de los mayoristas llegan por correo electrónico"),
                ("customer", "control", "info_phone", "los cambios del mismo día se hacen por teléfono"),
                ("control", "supplier", "info_phone", "planeación coordina el corte con los invernaderos por teléfono"),
                ("control", "procs", "info_manual", "un tablero de metas por hora se actualiza a mano")],
    notes=["Convierte tallos a ramos antes de calcular el takt."],
    objectives=["Convertir tallos a ramos.",
                "Representar cuarto frío, transporte terrestre y aéreo en un flujo perecedero."],
    opportunities=["El armado (celda) es el cuello: estandarizar la receta de ramos y balancear la célula.",
                   "Cada día extra de inventario resta vida útil en florero para el consumidor final.",
                   "Enlazar Clasificación y Armado con FIFO para reducir 0.5 días de espera."])

ALL_CASES = [J1_PANADERIA, J2_CAMISETAS, J3_PUERTAS,
             B0_TABURETES, B1_CAFE, B2_YOGUR, B3_CALZADO,
             A0_FARMA, A1_SHAMPOO, A2_JUGOS, A3_ELECTRONICA, A4_BOLSAS,
             V0_AUTOPARTES, V1_TORNILLOS, V2_JEANS, V3_FUNDICION, V4_LAB,
             R1_BICICLETAS, R2_CERVEZA, R3_O2C,
             N1_AERO, N2_INYECTABLES, N3_FLORES]
