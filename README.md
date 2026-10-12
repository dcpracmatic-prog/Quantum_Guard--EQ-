# Edge Quantum Guard (EQG)

**Edge Quantum Guard (EQG)** es una capa de control de bajo nivel entre una carga cuántica y el backend. Combina selección de layout, medición de salud, intervención condicional con dynamical decoupling (DD) y evaluación causal del resultado.

Este repositorio contiene los experimentos EQG y el paquete `ddqpu`, usado para validar CPMG/XY4, coherencia y control de relevos. La evidencia que se resume aquí es **experimental y acotada**: no equivale a certificación de producto ni demuestra generalización a otros algoritmos, tamaños o proveedores.

> **Confidencialidad:** los informes PDF añadidos están marcados “Confidential”. El repositorio debe mantenerse privado salvo que tengas autorización para hacerlos públicos.

## Cómo funciona EQG

| Rol | Módulo | Función |
|---|---|---|
| Eyes | AOM / salud | Combina calibración y medición en vivo para estimar régimen y salud por qubit. |
| Reflexes | MORPH | Selecciona un camino físico conectado según salud de qubit y error de compuertas CZ. |
| Judgment | Plan de mínima acción + veredicto causal | Decide si mantener, remapear o activar DD condicional, y registra el motivo. |
| Hands | DD + ejecución | Inserta CPMG/XY4 en ventanas ociosas y ejecuta la carga. |

**Centinela** es una sonda complementaria que caracteriza estados de coherencia y ayuda a decidir cuándo DD podría aportar. Sus resultados motivan la política; no sustituyen la validación de cada backend.

## Evidencia experimental documentada

Las corridas QAOA usan MaxCut sobre un camino de 8 nodos (`N=8`, `p=2`). El criterio preregistrado para la comparación A/B fue `z ≥ 2` sobre `AR` es la razón de aproximación; `ΔAR = AR(EQG) − AR(baseline)` y `EE` es el error estándar. Los valores de esta sección son los reportados en los informes adjuntos.

### IBM Quantum `ibm_fez`: orden cruzado

| Corrida | Orden | Presupuesto por brazo | AR con EQG | AR baseline | ΔAR ± EE | z |
|---|---|---:|---:|---:|---:|---:|
| R1 | EQG primero (B→A) | 7 s | 0.8147 ± 0.0027 | 0.7923 ± 0.0029 | +0.0224 ± 0.0040 | 5.7 |
| R2 | baseline primero (A→B) | 15 s | 0.8092 ± 0.0009 | 0.7713 ± 0.0010 | +0.0379 ± 0.0014 | 27.7 |

El signo positivo se mantuvo al invertir el orden de los brazos, lo que reduce —pero no elimina— el posible efecto de la deriva temporal del chip. Las instantáneas PRE/MID/POST atribuyen mejoras de estabilidad a MORPH y DD en estas corridas.

### Ablaciones de cuatro brazos: `ibm_marrakesh` e `ibm_kingston`

A = layout ingenuo; C = layout MORPH elegido por calibración; D = MORPH con DD forzado; E = EQG completo. El criterio preregistrado de cada ablación exige `z ≥ 2` y signo positivo en las cuatro repeticiones del experimento.

| Backend | AR A | AR C | AR D | AR E |
|---|---:|---:|---:|---:|
| `ibm_marrakesh` | 0.7189 ± 0.0023 | 0.7925 ± 0.0020 | 0.7898 ± 0.0020 | 0.8126 ± 0.0019 |
| `ibm_kingston` | 0.7700 ± 0.0019 | 0.8216 ± 0.0018 | 0.8150 ± 0.0019 | 0.8157 ± 0.0019 |

| Backend | C−A: layout | D−C: DD aislado | E−C: reacción en vivo | E−A: stack completo |
|---|---:|---:|---:|---:|
| `ibm_marrakesh` | +0.0736 (apoyado) | −0.0027 (no concluyente) | +0.0200 (apoyado) | +0.0937 (apoyado) |
| `ibm_kingston` | +0.0516 (apoyado) | −0.0066 (signo opuesto) | −0.0059 (signo opuesto) | +0.0458 (apoyado) |

En ambas ablaciones, la selección de layout por calibración fue el aporte grande y consistente. DD y reacción en vivo variaron por dispositivo: no deben presentarse como beneficios universales. En `ibm_kingston`, una comparación de configuraciones idénticas varió alrededor de 0.006 AR; el propio informe advierte no interpretar efectos de ese tamaño como concluyentes.

**Límites:** los informes cubren tres backends y una carga, con corridas de una sola jornada/ciclo de calibración; las cuatro repeticiones de las ablaciones no son una serie independiente entre días. PRE/MID/POST reduce, pero no elimina, la deriva. Hace falta replicar en más días, formalizar las ablaciones y probar otros backends/cargas antes de hacer afirmaciones generales.

### Informes completos

- [Technical Validation Report — IBM Fez (PDF)](docs/eqg/reports/eqg-technical-validation-ibm-fez-2026-10-12.pdf)
- [Validation and Cross-Hardware Reproducibility Plan (PDF)](docs/eqg/reports/eqg-cross-hardware-reproducibility-plan-2026-10-12.pdf)

## Notebooks EQG

Se conservaron los cuatro notebooks adjuntos tal como llegaron en `notebooks/eqg/`. Para ejecución, usa las copias revisadas en `notebooks/eqg/safe/`:

| Notebook seguro | Experimento |
|---|---|
| [QAOA Fez, 7 s, EQG primero](notebooks/eqg/safe/qaoa-ibm-fez-7s-eqg-first.ipynb) | Corrida A/B en orden B→A. |
| [QAOA Fez, 15 s, baseline primero](notebooks/eqg/safe/qaoa-ibm-fez-15s-baseline-first.ipynb) | Réplica con orden A→B. |
| [Ablación Marrakech, ABBA](notebooks/eqg/safe/ablation-ibm-marrakesh-abba.ipynb) | Cuatro brazos A/C/D/E. |
| [Ablación Kingston, ABBA](notebooks/eqg/safe/ablation-ibm-kingston-abba.ipynb) | Cuatro brazos A/C/D/E. |

### Preparación y seguridad

```bash
pip install -e ".[dev]"
pytest -q
```

Las copias seguras **no instalan paquetes automáticamente**. Prepara el entorno antes de abrirlas. Por defecto, `MODE = "sim"`; la simulación sirve para comprobar el flujo, **no es evidencia experimental**. No se ejecutaron estos notebooks al incorporarlos al repositorio.

Para hardware, revisa backend, plan de shots y presupuesto y habilita ambos controles de la copia correspondiente:

- Ablaciones ABBA: `MODE = "hardware"` y `CONFIRM_SPEND = True`.
- Corridas A/B de Fez: `MODE = "hardware"` y `CONFIRM_HARDWARE_RUN = True`.

La conexión al QPU queda bloqueada mientras falte la confirmación. Configura el token IBM como secreto del entorno (por ejemplo, el secreto de Kaggle); **no lo pegues en el notebook ni en el repositorio**. Cola de espera y tiempo de cuenta QPU son conceptos distintos.

## Paquete `ddqpu` y validación existente

La implementación de validación previa del repositorio está en `src/ddqpu/`:

- `circuits.py`: circuitos alineados a `dt`, espectadores y referencias de relevo.
- `backend_utils.py`: ranking de qubits, layout, transpilación y estimación de tiempo.
- `analysis.py`: mitigación de lectura, coherencia, ajustes y prueba de relevos.
- `experiment.py`: orquestación y análisis experimental.
- `plots.py`: figuras.
- `sentinel.py`: Centinela — sondeo, bitácora, decisión y corrección de fase.

La versión 5.0.0 incluye medición de canal libre, CPMG/XY4, controles de relevo, modos `hardware`, `sim` y `reuse`, pruebas automatizadas y scripts de reanálisis. La documentación del módulo Centinela está en [docs/producto_centinela.md](docs/producto_centinela.md). Los notebooks previos del paquete están en `notebooks/`.

## Resultados de Centinela

El análisis documentado para `ibm_fez`, qubit q142, reporta dos estados de coherencia `T2*` (155 ± 5 μs y 40 ± 4 μs), extensión de coherencia con DD, reducción del exceso de desfase y una cota de transferencia a vecinos menor de 0.18% (95% superior). Consulta el [informe de Centinela](docs/producto_centinela.md) y los archivos de `results/` para contexto, método y límites.

## Estructura del repositorio

```text
src/ddqpu/       Paquete de validación DD/Centinela
notebooks/       Notebooks existentes del paquete
notebooks/eqg/   Notebooks EQG originales recibidos
notebooks/eqg/safe/ Copias EQG con modo sim y bloqueo explícito de QPU
docs/eqg/reports/ Informes EQG y plan de reproducibilidad
results/          Resultados procesados y figuras
evidence/ibm_jobs/ Evidencia de jobs de IBM Quantum
 tests/          Suite pytest
 tools/          Herramientas para regenerar notebooks
```

## Datos y atribución

Los archivos de `evidence/ibm_jobs/` contienen resultados obtenidos en hardware de IBM Quantum y se conservan para reproducibilidad científica. Su uso sigue sujeto a los términos y políticas de IBM Quantum; el proyecto no está afiliado ni respaldado por IBM. Las exportaciones de analítica de uso con IBMid, correo, identificadores de cuenta o CRN se mantienen fuera del control de versiones. El campo `user_id` se eliminó de la evidencia incluida.

Qiskit conserva su licencia Apache-2.0 y las dependencias mantienen sus licencias propias.

## Licencia y copyright

Copyright (c) 2026 **Arturo Salvador Balderas Hernández**.

El contenido original de primera parte de este repositorio —código, documentación, notebooks, informes y resultados— se distribuye bajo **Elastic License 2.0 (ELv2)**. Consulta [`LICENSE`](LICENSE) y el [alcance y las excepciones](docs/licensing-scope.md). Los componentes, datos y materiales de terceros conservan sus propios términos. ELv2 restringe ofrecer el software como servicio hosted/managed con acceso a una parte sustancial de sus funciones; revisa el [texto de la licencia](https://www.elastic.co/licensing/elastic-license) antes de desplegarlo así. Las licencias de versiones o copias distribuidas anteriormente no se cambian retroactivamente.

## Citación

Si utilizas el código o los resultados en un trabajo académico o técnico, se agradece citar el repositorio y al autor. Para interpretar los hallazgos, conserva también el protocolo, los identificadores de jobs y los límites descritos en los informes.
