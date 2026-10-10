# dd-qpu-validation

**Validación experimental de Dynamical Decoupling (CPMG y XY4) en QPUs de IBM, con control de relevos y detección en tiempo real del estado del qubit.**

Versión 5.0.0 — incluye **Centinela**, un sondeo previo de aproximadamente 7 segundos de QPU que detecta el estado del qubit (fluctuaciones tipo TLS), selecciona el qubit más adecuado en el momento, estima la ganancia esperada del Dynamical Decoupling y aplica una corrección de fase (Z virtual).

Documentación de la herramienta: [`docs/producto_centinela.md`](docs/producto_centinela.md)

---

## Características principales

- Medición completa (canal libre + CPMG + XY4 + controles de relevo) en **un solo job**.
- Verificación estructural estricta: ausencia de compuertas de dos qubits y layout inicial = final.
- Coherencia en cuadratura, mitigación de error de lectura por qubit y ajustes ponderados.
- Prueba estadística pareada de relevos (fuga / crosstalk) con corrección de Bonferroni.
- **Centinela**: sondeo paralelo rápido para clasificación de estado y corrección de detuning.
- Modos de ejecución: `hardware`, `sim` (FakeFez) y `reuse` (reanálisis de jobs previos).
- Suite de pruebas automatizadas y scripts de reanálisis.

## Estructura del repositorio

```
src/ddqpu/                  # Paquete principal (única fuente de verdad)
  circuits.py               # Circuitos alineados a dt, espectadores y referencias de relevo
  backend_utils.py          # Ranking de qubits, layout, transpilación bloqueada, estimación de tiempo
  analysis.py               # Mitigación de lectura, coherencia, ajustes, prueba de relevos
  experiment.py             # Orquestación del lote experimental y análisis completo
  plots.py                  # Generación de figuras
  sentinel.py               # Centinela: sondeo, bitácora, decisión y corrección de fase
docs/
  producto_centinela.md     # Descripción pública de Centinela y resultados experimentales
notebooks/
  dd_validacion_v4.ipynb    # Notebook principal autocontenido (Kaggle / QPU)
  centinela_preflight.ipynb # Notebook de Centinela
  ejemplo_sim_fakefez.ipynb # Control negativo en simulador
  ejemplo_centinela_sim.ipynb
scripts/
  analyze_v4_runs.py        # Análisis de estados de las corridas v4
  reanalyze_previous.py     # Reanálisis de corridas v1–v3 sin gastar cola
results/                    # Resultados procesados (JSON, Markdown, figuras)
evidence/
  ibm_jobs/                 # Datos crudos de jobs de IBM Quantum
data/                       # Datos de corridas anteriores y notebooks originales
tests/                      # Suite pytest
tools/                      # Scripts para regenerar notebooks desde el código fuente
```

## Instalación rápida

```bash
pip install -e ".[dev]"
pytest -q
```

## Uso

### Notebook principal (recomendado para Kaggle o ejecución local)

1. Sube `notebooks/dd_validacion_v4.ipynb`.
2. Configura el secreto `IBM_QUANTUM_TOKEN`.
3. Selecciona el modo:

| MODE       | Descripción                                                                 |
|------------|-----------------------------------------------------------------------------|
| `"sim"`    | Ejecución en FakeFez + Aer (gratuito). Control negativo: sin ruido de baja frecuencia el DD no debe extender \(T_2\). |
| `"hardware"` | Un job real en el QPU. Se detiene si la estimación de tiempo supera el límite configurado. |
| `"reuse"`  | Recupera un job anterior mediante `REUSE_JOB_ID` y reanaliza sin consumir cola. |

### Centinela (pre-vuelo)

Utiliza `notebooks/centinela_preflight.ipynb` o importa directamente desde `ddqpu.sentinel`.

## Resultados destacados (ibm_fez, q142)

Reanálisis de corridas previas y nuevas mediciones de septiembre 2026 muestran:

- Existencia de **estados discretos** del qubit (bueno ≈ 155 µs vs degradado ≈ 40 µs en \(T_2^*\)).
- El Dynamical Decoupling elimina ~65 % del exceso de desfase del estado degradado.
- Supresión del ~93 % del acoplamiento ZZ medido.
- Cota superior de relevo a vecinos inferior al 0.18 % (95 % de confianza).

Detalle completo en `results/` y en [`docs/producto_centinela.md`](docs/producto_centinela.md).

## Aviso sobre datos de IBM Quantum

Los archivos contenidos en `evidence/ibm_jobs/` corresponden a resultados de jobs ejecutados en hardware de IBM Quantum.  
Se publican **exclusivamente con fines de reproducibilidad científica**.  
El uso de estos datos está sujeto a los términos de servicio y políticas de IBM Quantum.  
Este repositorio no está afiliado ni respaldado por IBM.

## Licencia y copyright

Copyright (c) 2026 **Arturo Salvador Balderas Hernández**

Este proyecto se distribuye bajo la licencia **MIT**.  
Consulta el archivo [`LICENSE`](LICENSE) para el texto completo.

## Citación

Si utilizas este código o los resultados en un trabajo académico o técnico, se agradece la cita o mención del repositorio y del autor.

---

Desarrollado con Qiskit y Qiskit IBM Runtime.
