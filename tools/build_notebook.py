"""Genera notebooks/dd_validacion_v4.ipynb embebiendo el paquete src/ddqpu (una sola fuente de verdad).

Uso: python tools/build_notebook.py
"""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "ddqpu"
MODULES = ["__init__.py", "circuits.py", "backend_utils.py", "analysis.py", "experiment.py", "plots.py", "sentinel.py"]

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = []
cells.append(md("""# Validacion de Dynamical Decoupling en QPU — v4 (relevos y resultados optimizados)

**Un solo job** que mide, en el mismo lote y con el mismo layout fisico:

| Bloque | Circuitos | Para que |
|---|---|---|
| Calibracion de lectura | 2 (todo en 0, todo en 1) | Mitigar ⟨X⟩/⟨Y⟩ y tener el piso de lectura **de cada qubit** |
| Barrido principal | 3 protocolos × ~16 tiempos × bases X e Y | Coherencia en cuadratura \\|ρ01\\| = √(⟨X⟩²+⟨Y⟩²): elimina la oscilacion por detuning |
| Referencias de relevo | objetivo inactivo / objetivo en \\|1⟩ a 3 tiempos | Prueba **pareada** de transferencia de poblacion a cada vecino |
| Espectadores en \\|1⟩ (ZZ) | libre y CPMG a 3 tiempos | Medir cuanto afecta el estado de los vecinos a la fase del objetivo y si DD lo cancela |

## Que cambia respecto a v1-v3
1. **Detuning sin aliasing.** v2/v3 muestreaban cada 26-130 µs; el detuning real (~27 kHz) aparecia como 54 kHz y el T2 libre salia en 62 µs. Ahora hay un tramo denso (≤ 5 µs de paso) y lectura en X e Y.
2. **Ajustes fisicos.** C = 0 fijo (la coherencia decae a 0), ponderado por ruido de disparo, error inflado por √χ² si hay deriva. Esto quita la degeneracion T2↔C que daba barras de error mayores que el valor.
3. **Relevos bien planteados.** Se cuentan todas las compuertas de 2 qubits (un SWAP transpilado son 3 CZ), se verifica el layout inicial y final, y la poblacion de cada vecino se compara con **su propia** linea base (objetivo inactivo), con prueba de dos proporciones y correccion de Bonferroni.
4. **Tiempos alineados a dt.** Libre, CPMG y XY4 tienen exactamente el mismo tiempo de espera, sin los `UserWarning` de redondeo, y se reporta t efectivo con la duracion de los pulsos.
5. **Orden aleatorio** de circuitos para que la deriva lenta no se correlacione con t.
6. **Shots por circuito** (PUBs con shots propios) y **freno de tiempo QPU** antes de enviar.
7. **Modo `reuse`**: reanaliza un job ya ejecutado sin volver a hacer cola. **Modo `sim`**: prueba todo gratis con `FakeFez`.

## Requisitos (Kaggle)
Internet ON · secreto `IBM_QUANTUM_TOKEN` · reiniciar el kernel si lo pide tras `pip`.
"""))
cells.append(md("## 1. Instalacion"))
cells.append(code('%pip install -q "qiskit>=1.3" "qiskit-ibm-runtime>=0.30" qiskit-aer matplotlib scipy\nprint("OK")'))
cells.append(md("## 2. Paquete `ddqpu` (embebido)\nEsta celda escribe el paquete del repositorio en `./ddqpu/`. Si clonaste el repo, puedes omitirla y hacer `pip install -e .`."))

writer = ["import pathlib, importlib, sys", "_FILES = {}"]
for m in MODULES:
    src = (PKG / m).read_text()
    writer.append(f"_FILES[{m!r}] = {src!r}")
writer.append("""pkg = pathlib.Path("ddqpu"); pkg.mkdir(exist_ok=True)
for name, src in _FILES.items():
    (pkg / name).write_text(src)
sys.path.insert(0, str(pathlib.Path.cwd()))
for mod in [m for m in list(sys.modules) if m == "ddqpu" or m.startswith("ddqpu.")]:
    del sys.modules[mod]
import ddqpu
print("ddqpu", ddqpu.__version__, "listo")""")
cells.append(code("\n".join(writer)))

cells.append(md("""## 3. Configuracion
- `MODE = "hardware"` envia el job al QPU.
- `MODE = "sim"` usa `FakeFez` + Aer (gratis; sirve de **control negativo**: sin ruido de baja frecuencia, el DD no debe extender T2).
- `MODE = "reuse"` recupera el resultado de `REUSE_JOB_ID` usando el `manifest.json` guardado."""))
cells.append(code('''from pathlib import Path
from ddqpu.experiment import Config, build_batch, run_batch, reload_from_job, analyze, summarize, save_counts, to_jsonable
from ddqpu.backend_utils import get_service, rank_qubits, transpile_locked, estimate_qpu_seconds
from ddqpu.plots import plot_coherence, plot_relay

MODE = "hardware"            # "hardware" | "sim" | "reuse"
REUSE_JOB_ID = None          # p.ej. "d..." para reanalizar sin cola
CHANNEL, INSTANCE = "ibm_cloud", "open-instance"
OUT_DIR = Path("/kaggle/working/ddqpu_run") if Path("/kaggle/working").exists() else Path("ddqpu_run")

cfg = Config(
    backend_name="ibm_fez",
    force_target=None,        # 142 para comparar con v1-v3; None = mejor qubit segun calibracion actual
    n_neighbors=2,
    n_cpmg=6, n_xy4_cycles=2,
    shots_main=1024,          # por base (X e Y) => 2048 por punto de coherencia
    shots_ref=2048, shots_cal=4096,
    enable_zz=True,
    max_qpu_seconds=240,
)
cfg'''))

cells.append(md("## 4. Backend, qubit objetivo, vecinos y control"))
cells.append(code('''if MODE == "sim":
    from qiskit_ibm_runtime.fake_provider import FakeFez
    backend, service = FakeFez(), None
else:
    service = get_service(CHANNEL, INSTANCE)
    names = [b.name for b in service.backends(operational=True, simulator=False)]
    print("Backends operativos:", names)
    backend = service.backend(cfg.backend_name if cfg.backend_name in names else names[0])
print("Usando:", backend.name)

print("\\nTop qubits (score = min(T2, 2*T1) / (1 + 50*err_sx + 10*err_lectura)):")
for r in rank_qubits(backend, top=6):
    print(f"  q{r.q:<4} T1={r.t1_us:6.1f} us  T2={r.t2_us:6.1f} us  err_sx={r.sx_err:.2e}  err_ro={r.ro_err:.3f}  score={r.score:6.1f}")'''))

cells.append(md("## 5. Lote unico + verificacion estructural de relevos + estimacion de tiempo QPU"))
cells.append(code('''circs, specs, layout, timing, grid = build_batch(cfg, backend)
print("Layout fisico [objetivo, vecinos..., control]:", layout.physical,
      f"| control a distancia {layout.control_distance}")
print(f"T2 calibrado objetivo = {layout.target_t2_us:.1f} us | T1 = {layout.target_t1_us:.1f} us")
print("Rejilla de tiempos (us):", grid)
print(f"dt = {timing.dt*1e9:.2f} ns, granularidad = {timing.granularity} dt, pulso X = {timing.x_duration_dt} dt")

from collections import Counter
print("Circuitos por tipo:", dict(Counter(s.kind for s in specs)))
tcs_preview, report = transpile_locked(circs, backend, layout, cfg.optimization_level)
print("\\nVerificacion estructural:", "OK - sin compuertas de 2 qubits, layout inicial = final = " + str(layout.physical)
      if report["ok"] else report["issues"][:5])
print(f"Tiempo QPU estimado: ~{estimate_qpu_seconds(specs, backend):.0f} s (freno: {cfg.max_qpu_seconds} s)")'''))

cells.append(md("## 6. Ejecucion (una sola espera de cola)"))
cells.append(code('''import json
if MODE == "reuse":
    assert REUSE_JOB_ID, "Define REUSE_JOB_ID"
    manifest, counts = reload_from_job(service, REUSE_JOB_ID, OUT_DIR / "manifest.json")
    save_counts(OUT_DIR, manifest, counts)
else:
    manifest, counts = run_batch(cfg, backend, circs, specs, layout, OUT_DIR, mode=MODE)
print("Datos crudos guardados en", OUT_DIR / "raw_counts.json")'''))

cells.append(md("## 7. Analisis: coherencia en cuadratura, ajustes y extension por DD"))
cells.append(code('''res = analyze(manifest, counts)
print(summarize(res, manifest))
(OUT_DIR / "results.json").write_text(json.dumps(to_jsonable(res), indent=1))
fig = plot_coherence(res, manifest, OUT_DIR / "coherencia.png")'''))

cells.append(md("## 8. Relevos: prueba pareada por vecino"))
cells.append(code('''lay = manifest["layout"]
names = {f"vecino_bit{i+1}": f"q{q}" for i, q in enumerate(lay["neighbors"])}
names["control"] = f"q{lay['control']} (control)"
print(f"{'espectador':>16} {'P1 idle':>9} {'P1 activo':>10} {'Δ':>9} {'p':>8} {'P1 |1>':>9} {'Δ':>9} {'p':>8}")
for k, s in res["relay"].items():
    a, e = s["activo_vs_idle"], s["excitado_vs_idle"]
    print(f"{names[k]:>16} {a['p_ref']*100:8.3f}% {a['p_active']*100:9.3f}% {a['delta']*100:+8.3f}% {a['p_value']:8.3f}"
          f" {e['p_active']*100:8.3f}% {e['delta']*100:+8.3f}% {e['p_value']:8.3f}")
e0, e1 = res["readout"]["e0"], res["readout"]["e1"]
print("\\nError de lectura por qubit P(1|0):", [f"{x*100:.2f}%" for x in e0])
if res.get("zz"):
    for p, z in res["zz"].items():
        print(f"ZZ con vecinos en |1> ({p}): {z['zz_kHz']:+.2f} kHz  |",
              " ".join(f"t={r['t']:.0f}: dphi={r['dphi']:+.3f} rad, |c|1/|c|0={r['mag1']/max(r['mag0'],1e-3):.3f}" for r in z["rows"]))
fig = plot_relay(res, manifest, OUT_DIR / "relevos.png")'''))

cells.append(md("## 9. Veredicto por hipotesis"))
cells.append(code('''print("=" * 72)
ext = res["extension"]
for p in ("cpmg", "xy4"):
    if p in ext:
        e = ext[p]
        print(f"H1 [{p.upper()} extiende la coherencia]: T2_{p}/T2* = {e['ratio']:.2f} ± {e['err']:.2f} -> "
              + ("CONFIRMADA (> 2σ)" if e["significant"] else "NO confirmada"))
fits = res["fits"]
if fits.get("free"):
    b = fits["free"]["beta"]; eb = fits["free"]["beta_err"]
    print(f"H2 [ruido de baja frecuencia en libre, β>1]: β = {b:.2f} ± {eb:.2f} -> "
          + ("CONFIRMADA" if b - 1 > 2 * eb else "NO confirmada (decaimiento ~exponencial)"))
d = res.get("detuning")
if d:
    print(f"H3 [el cruce por cero del canal libre es detuning]: δf = {d['f_kHz']:+.2f} ± {d['f_err_kHz']:.2f} kHz -> "
          + ("CONFIRMADA" if abs(d["f_kHz"]) > 3 * d["f_err_kHz"] else "no hay detuning apreciable"))
rv = res["relay_verdict"]
print("H4 [no hay relevo a vecinos]: " + ("RECHAZADA, relevo en " + str(rv["flagged"]) if rv["relay_detected"]
      else f"CONFIRMADA, transferencia < {rv['worst_upper95']*100:.3f} % (95 %)"))
print("Verificacion estructural:", "sin SWAP ni 2q" if manifest["structural_check"]["ok"] else "PROBLEMAS")
print("=" * 72)'''))

cells.append(md("""## 10. Referencia: reanalisis de v1-v3 (ibm_fez q142)
Resultado de `scripts/reanalyze_previous.py` en el repositorio, sobre los datos ya medidos:

| Magnitud | Reportado antes | Reanalisis |
|---|---|---|
| Detuning libre | 53.9 kHz (v2) | **27.14 ± 0.06 kHz** (v2 tenia alias por el paso de 26 µs) |
| T2* libre | 5.2 µs (v1), 61.8 µs (v2) | **139 ± 7 µs** (β = 1.00) |
| T2 CPMG | 55.9 / 249 / 138 µs | **178 ± 5 µs** (combinado, C = 0) |
| T2 XY4 | 48 / 144 / 189 µs | **193 ± 9 µs** |
| Extension CPMG / libre | 10.7x, 3.2x | **1.28 ± 0.07x** |
| Relevo a vecinos (v3) | "sin relevo" (criterio invalido) | **< 0.145 %** (cota 95 %, absoluta) |
| N optimo (60 µs) | 16 | curva plana (χ²_red = 0.49): N no importa entre 2 y 24 |

Con la v4, si `force_target=142`, estos valores son la referencia contra la que comparar.

### Limites que siguen abiertos
- La lectura estandar no distingue |2⟩: una fuga a estados no computacionales se veria como perdida de coherencia. Se puede anadir un discriminador de 3 niveles cuando el backend lo permita.
- Crosstalk de largo alcance: se cubren vecinos directos y un control lejano; se puede ampliar `n_neighbors` o medir un anillo a distancia 2 sin circuitos adicionales.
- La deriva entre jobs (χ²_red de 4 a 11 entre v2 y v3) sugiere repetir la v4 2-3 veces para reportar una media con dispersion real.
"""))

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12"}})
out = ROOT / "notebooks" / "dd_validacion_v4.ipynb"
nbf.write(nb, out)
print("escrito", out)
