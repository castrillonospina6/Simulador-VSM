# Simulador VSM — MVP

Simulador de Value Stream Mapping en Python/PyQt5. Dibujas un VSM arrastrando
símbolos, ves las métricas (Takt Time, Lead Time, PCE, cuello de botella)
recalcularse **en vivo**, y practicas con **casos empresariales** que el sistema
**evalúa** contra una solución de referencia.

## Instalación

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Requiere Python 3.9+ y PyQt5 5.15. Tests: `python -m pytest -q tests`
(los tests de GUI corren en modo headless, no abren ventanas).

## Cómo usarlo

**Modo caso (recomendado)**
1. Menú **Casos** → elige un caso (Blanco / Amarillo / Verde) o un **caso aleatorio**.
   El panel derecho muestra el enunciado con los datos de la empresa.
2. Normaliza los datos (segundos por unidad, % de disponibilidad, unidades de inventario;
   en niveles altos vienen como piezas/hora, min por lote, "días de demanda"…).
3. Arrastra símbolos al canvas: proveedor, procesos, inventarios, cliente y planificación.
4. **Doble clic** en un símbolo para editar sus datos.
5. Conecta con la barra de herramientas (Material empuje / FIFO / pull, Información
   manual / electrónica): clic en el origen y luego en el destino. `Esc` cancela.
6. **Evaluar mi mapa** (`Ctrl+E`). Casos → *Ver solución de referencia* para comparar.

**Modo libre:** Archivo → Nuevo mapa. Dibuja lo que quieras; los parámetros
(demanda, turnos, horas, tiempo no disponible) se editan en Archivo → Parámetros del caso.

Otros: `Supr` borra la selección · `Ctrl + rueda` zoom · Archivo → Guardar/Abrir
(`.vsm.json`) · Ver → mostrar/ocultar paneles.

**Alcance del MVP:** el motor interpreta el flujo como una secuencia **lineal**,
ordenando procesos, inventarios y transportes de izquierda a derecha según su
posición X. Ramificaciones/uniones vienen en una fase posterior.

## Iconografía: 100 % de las fuentes

Están implementados **33 símbolos** (paleta izquierda, 6 categorías) y **6 tipos de flecha**
(barra de herramientas). `vsm/symbol_catalog.py` mapea cada pictograma del libro de Dumser
[L] y de la tabla de símbolos VSM [T] contra lo implementado, y `tests/test_symbols.py`
verifica que no falte ninguno.

| Categoría | Símbolos |
|---|---|
| Flujo de proceso | Proveedor · Cliente · Proceso / casilla de proceso (con íconos de operario) · Proceso compartido · Celda de trabajo · Operario · Tabla de datos |
| Material | Inventario · Supermercado · Carril PEPS (FIFO) con capacidad máx. · Buffer / existencias de seguridad · Punto de acumulación BUFFER (B) · Punto de acumulación STOCK DE SEGURIDAD (S) · Transporte (camión, avión, barco) · Flecha de transporte de mercancías · Flujo de MP y PT · Pull físico |
| Información | Control / planificación de la producción · Base de datos / MRP-ERP · Caja de información |
| Kanban y pull | Kanban de producción · Retirada Kanban · Lote de tarjetas Kanban · Señal Kanban · Tarjeta Kanban (poste) · Nivelación de carga (heijunka) · Secuencia pull ball |
| Tiempo | Línea de tiempo (segmento) · Tiempo total (se actualiza en vivo) · Reloj · Reelaboración |
| Mejora | Estallido Kaizen · Observación |
| Flechas | Push · Carril FIFO (con etiqueta, p. ej. «máx 20 uds») · Pull · Información manual · Información electrónica · Teléfono |

Estilo: por defecto se dibuja como la **tabla de símbolos VSM** (inventario naranja, control celeste, info electrónica curva, Kanban con líneas punteadas). **Ver → Estilo de símbolos → Libro (Dumser)** cambia al estilo del libro (inventario amarillo con «I», control oscuro, info electrónica en rayo, tabla de datos azul, estallido Kaizen).

Notas: inventario, supermercado, carril PEPS y buffers **suman al lead time** (cantidad / demanda diaria);
proceso compartido y celda de trabajo cuentan como procesos en el motor; el resto de símbolos
(Kanban, tiempo, mejora…) son anotaciones que no alteran el cálculo. Doble clic sobre una
flecha para ponerle una etiqueta.

## Cómo calcula

| Métrica | Fórmula |
|---|---|
| Takt Time | (turnos × (horas × 3600 − no disponible)) / demanda diaria |
| Tiempo de ciclo efectivo | TC / disponibilidad |
| Días de inventario | cantidad / demanda diaria (días laborales) |
| Lead Time | Σ esperas (inventarios + tránsitos) + Σ TC |
| PCE | Tiempo de valor agregado / Lead Time |
| Cuello de botella | mayor tiempo de ciclo efectivo; en rojo si supera el takt |

## Casos: 23 en 6 niveles + generador

| Nivel | Tolerancia | Qué exige |
|---|---|---|
| Junior ★ | ±8 % | 3 procesos, datos limpios en segundos y símbolos básicos. |
| Blanco ★★ | ±5 % | 4 procesos, datos limpios; se suman transportes y buffers. |
| Amarillo ★★★ | ±3 % | Unidades mezcladas, supermercados, carriles FIFO y Kanban. |
| Verde ★★★★ | ±2 % | Procesos compartidos y celdas, lotes, paradas, demanda semanal. |
| Rojo ★★★★★ | ±2 % | Sistemas pull en el estado actual, OEE, demanda mensual, pallets. |
| Negro ★★★★★★ | ±1 % | Flujos complejos: 7+ procesos, avión/barco, buffers, datos trampa. |

| Nivel | id | Caso | Sector | Símbolos especiales |
|---|---|---|---|---|
| Junior | `panaderia` | Panadería El Horno — Pan tajado | Alimentos | — |
| Junior | `camisetas` | Taller Aurora — Camisetas estampadas | Textil | — |
| Junior | `puertas` | Carpintería Roble — Puertas de interior | Madera y muebles | — |
| Blanco | `taburetes` | Laforêt SPRL — Taburetes | Muebles | camión |
| Blanco | `cafe` | Café Cumbre — Café tostado y molido 500 g | Alimentos | camión |
| Blanco | `yogur` | Lácteos La Vega — Yogur 1 L | Lácteos | Buffer / existencias de seguridad |
| Blanco | `calzado` | Calzados Sol — Zapatilla escolar | Calzado | camión |
| Amarillo | `farma` | Andina Pharma — Tabletas de acetaminofén 500 mg | Farmacéutico | Base de datos / MRP-ERP, camión |
| Amarillo | `shampoo` | Cosméticos Brisa — Shampoo 400 ml | Cuidado personal | Carril PEPS (FIFO) |
| Amarillo | `jugos` | Jugos Tropicales — Jugo de mango 1 L | Bebidas | Retirada Kanban, Supermercado, camión |
| Amarillo | `electronica` | ElectroNova — Tarjeta controladora | Electrónica | Base de datos / MRP-ERP, Carril PEPS (FIFO), avión |
| Amarillo | `bolsas` | PlastiEmpaques — Bolsas plásticas impresas | Plásticos | Punto de acumulación BUFFER |
| Verde | `autopartes` | Metalmecánica Cafetera — Soporte de motor SM-220 | Autopartes | Celda de trabajo, Proceso compartido, camión |
| Verde | `tornillos` | Tornillos del Norte — Tornillo hexagonal M8 | Metalmecánica | Proceso compartido, camión |
| Verde | `jeans` | Denim Antioquia — Jean cinco bolsillos | Confección | Celda de trabajo, Proceso compartido, camión |
| Verde | `fundicion` | Fundiciones Andinas — Carcasa de bomba | Fundición | Celda de trabajo, camión |
| Verde | `lab-clinico` | Laboratorio Clínico Central — Exámenes de sangre | Servicios de salud | Base de datos / MRP-ERP, Proceso compartido |
| Rojo | `bicicletas` | BiciAndes — Bicicleta urbana | Ensamble de vehículos | Base de datos / MRP-ERP, Carril PEPS (FIFO), Celda de trabajo, Proceso compartido, Retirada Kanban, Señal Kanban, Supermercado, barco |
| Rojo | `cerveza` | Cervecería Montaña — Cerveza 330 ml | Bebidas | Base de datos / MRP-ERP, Carril PEPS (FIFO), Punto de acumulación BUFFER, camión |
| Rojo | `pedido-a-cobro` | Distribuciones del Sol — Del pedido al despacho | Servicios administrativos | Base de datos / MRP-ERP, Proceso compartido, camión |
| Negro | `aeronautica` | AeroPartes — Panel de fuselaje | Aeronáutica | Base de datos / MRP-ERP, Buffer / existencias de seguridad, Celda de trabajo, Proceso compartido, Punto de acumulación BUFFER, avión, barco |
| Negro | `inyectables` | Andina Pharma — Ampollas inyectables | Farmacéutico | Base de datos / MRP-ERP, Carril PEPS (FIFO), Punto de acumulación BUFFER, Punto de acumulación STOCK DE SEGURIDAD, camión |
| Negro | `flores` | Flores del Oriente — Ramos de exportación | Agroindustria | Buffer / existencias de seguridad, Celda de trabajo, avión, camión |

Cada enunciado incluye objetivos de aprendizaje, demanda y jornada, tablas de procesos / inventarios /
transportes, flujos de información descritos en palabras y, según el nivel, observaciones que son
distractores. Los datos vienen en unidades mezcladas (segundos, minutos, piezas/hora, minutos por
lote; disponibilidad, paradas u OEE; unidades, días de demanda o pallets; demanda por día, semana o mes)
y hay que normalizarlos. **Caso aleatorio** (menú Casos): 6 niveles, reproducible por semilla.

Los casos son **realistas pero sintéticos**. Después de evaluar se muestra un *análisis de referencia*
(takt, cuello, esperas mayores) y las *oportunidades de mejora* del caso (insumo para el estado futuro).

**Agregar un caso propio** (p. ej. uno real anonimizado): en `vsm/cases_library.py` crea un `Case`
con `ProcSpec` / `InvSpec` / `TransSpec` y añádelo a `ALL_CASES`. `problems(case)` y
`tests/test_cases.py` verifican que los datos del enunciado se conviertan sin error, que haya un
cuello claro y que la solución de referencia puntúe 100.

## Evaluación (motor de reglas)

Compara tu mapa con el de referencia. Puntaje sobre 100 (aprueba con ≥ 75):

| Sección | Pts | Qué revisa |
|---|---|---|
| Flujo de material | 20 | proveedor, cliente, flechas, camino continuo, tipo de flecha (push / FIFO / pull) |
| Flujos de información | 10 | cada flujo del enunciado con el tipo correcto (electrónico / manual / teléfono); tipo equivocado = crédito parcial |
| Procesos + símbolos especiales | 15 | procesos completos (10) + transportes, supermercado, FIFO, celdas, compartidos, buffers, base de datos, Kanban (5; si el caso no los usa, los 15 son de procesos) |
| Exactitud de los datos | 30 | TC, disponibilidad, C/O, operarios, turnos, inventarios (cualquier tipo), tiempos en tránsito, capacidad de carriles FIFO |
| Métricas | 25 | takt, tiempo VA, lead time, PCE, cuello de botella y procesos sobre el takt |

Los mensajes indican **qué** revisar sin regalar la respuesta.

## Estructura del código

```
main.py                  Punto de entrada
vsm/
  models.py               Modelos puros (sin PyQt5): Process, Inventory, External, Transport, Control, VSMMap
  engine.py               Motor de cálculo (sin PyQt5)
  case_model.py           Modelo de casos: pasos, mapa de referencia, enunciado (HTML), validación
  cases_library.py       Los 23 casos (aquí se agregan casos nuevos)
  generator.py            Generador aleatorio por nivel y semilla
  cases.py                Fachada: CASES, CASES_BY_LEVEL, get_case, generate_case…
  evaluation.py           Evaluador por reglas (sin PyQt5)
  symbol_catalog.py       Catálogo pictograma → símbolo implementado (auditable)
  canvas_items.py         Los 32 símbolos gráficos y las flechas de conexión
  canvas_view.py          Canvas: drag&drop, modo conexión, borrado
  toolbox.py              Paleta por categorías (íconos = mismo dibujo que el canvas)
  dialogs.py              Formularios de edición
  metrics_panel.py        Métricas en vivo + escalera de tiempo
  persistence.py          Guardar/cargar JSON
  main_window.py          Ventana principal
tests/                    Tests del núcleo y smoke test de GUI
```

`models`, `engine`, `cases` y `evaluation` no dependen de PyQt5: son el "cerebro"
y se pueden reutilizar tal cual en una versión web o en un backend.

## Nota honesta sobre la "red neuronal" de evaluación

Una red neuronal necesita datos de entrenamiento, y no existe un dataset de
"VSMs correctos vs. incorrectos". La ruta realista:

1. Motor de reglas determinístico contra un estado de referencia calculable (**ya implementado**).
2. Cada partida jugada genera datos reales (mapa, puntaje, errores).
3. Con esos datos, entrenar un modelo (scikit-learn / red pequeña) que refine la
   calificación, o usar un LLM para retroalimentación cualitativa tipo coach.

## Hoja de ruta

- [x] Motor de cálculo + canvas con métricas en vivo
- [x] Generador de casos paramétrico (6 niveles, ruido de unidades, símbolos especiales, semilla)
- [x] 23 casos en 6 niveles con análisis de referencia y oportunidades de mejora
- [x] Evaluación por reglas con retroalimentación
- [ ] **Estado futuro**: el estudiante propone mejoras (supermercado, pull, flujo continuo, combinar procesos) y se evalúa el impacto en lead time/PCE
- [ ] Niveles/cinturones completos (Junior → … → Negro Master) con XP y desbloqueo
- [ ] Ramificaciones en el flujo (no solo lineal)
- [ ] Exportar VSM a imagen/PDF
- [ ] Retroalimentación con LLM y modelo entrenado con partidas reales
