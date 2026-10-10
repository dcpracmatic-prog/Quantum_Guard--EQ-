"""Genera notebooks/centinela_preflight.ipynb (autocontenido; embebe src/ddqpu)."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "ddqpu"
MODULES = ["__init__.py", "circuits.py", "backend_utils.py", "analysis.py", "experiment.py", "plots.py", "sentinel.py"]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [md("""# Centinela QPU: sondeo previo de ~7 s antes de un trabajo caro

Qué resuelve: la calibración publicada de IBM se actualiza ~1 vez al día, pero en tus corridas v4
el qubit q142 de `ibm_fez` alternó en minutos entre **T2\\* ≈ 155 µs** y **≈ 40 µs**, con un salto de
frecuencia de hasta 6 kHz (firma de un defecto TLS fluctuante). Enviar un trabajo largo en el estado
degradado desperdicia tiempo de QPU.

Qué hace, en **un job** y con **K candidatos en paralelo** (mismo costo que uno):
| Medición | Circuitos | Para qué |
|---|---|---|
| Ramsey en X e Y (tramo denso ≤ 10 µs + 2 largos) | 20 | detuning sin alias y T2\\* |
| CPMG en 2 tiempos | 4 | cuánto recupera el DD **ahora** |
| T1 en 2 tiempos | 2 | separa desfase puro: Γφ = 1/T2\\* − 1/(2T1) |
| Calibración de lectura | 2 | mitigación por qubit |

Salida: estado (`estable` / `degradado`) contra la huella histórica de cada qubit, ranking en vivo,
ganancia esperada del DD y la **corrección de fase** (Z virtual, costo cero) para tu circuito.
Cada sondeo se guarda en una bitácora JSONL: con el tiempo es la estadística de estados por qubit.
"""),
 md("## 1. Instalación"),
 code('%pip install -q "qiskit>=1.3" "qiskit-ibm-runtime>=0.30" qiskit-aer matplotlib scipy\nprint("OK")'),
 md("## 2. Paquete `ddqpu` embebido")]
w = ["import pathlib, sys", "_FILES = {}"]
for m in MODULES:
    w.append(f"_FILES[{m!r}] = {(PKG / m).read_text()!r}")
w.append('''pkg = pathlib.Path("ddqpu"); pkg.mkdir(exist_ok=True)
for n, s in _FILES.items():
    (pkg / n).write_text(s)
sys.path.insert(0, str(pathlib.Path.cwd()))
for mod in [m for m in list(sys.modules) if m == "ddqpu" or m.startswith("ddqpu.")]:
    del sys.modules[mod]
import ddqpu
print("ddqpu", ddqpu.__version__)''')
cells.append(code("\n".join(w)))
cells.append(md("## 3. Configuración"))
cells.append(code('''from pathlib import Path
from ddqpu import sentinel as S
from ddqpu.backend_utils import get_service, _qubit_info

MODE = "hardware"                 # "hardware" | "sim"
CHANNEL, INSTANCE = "ibm_cloud", "open-instance"
BACKEND = "ibm_fez"
MUST_INCLUDE = [142]              # qubits que quieres vigilar siempre
K = 4                             # candidatos en paralelo (mismo costo)
MAX_QPU_S = 20                    # freno de seguridad
BASE = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(".")
OUT = BASE / "centinela"
BITACORA = S.Bitacora(OUT / "bitacora.jsonl")
SEMBRAR_V4 = True                 # agrega a la bitacora las 4 corridas v4 (23-sep-2026) de q142 como historial
pc = S.ProbeConfig(shots=512, shots_cal=2048, n_candidates=K)'''))
cells.append(md("## 4. Backend y candidatos"))
cells.append(code('''if MODE == "sim":
    from qiskit_ibm_runtime.fake_provider import FakeFez
    backend = FakeFez()
else:
    backend = get_service(CHANNEL, INSTANCE).backend(BACKEND)
cands = S.choose_candidates(backend, k=K, min_separation=pc.min_separation, must_include=MUST_INCLUDE)
print("Backend:", backend.name, "| candidatos:", cands)
for q in cands:
    i = _qubit_info(backend, q)
    print(f"  q{q:<4} calibracion publicada: T1={i.t1_us:6.1f} us  T2={i.t2_us:6.1f} us  err_lectura={i.ro_err:.3f}")

if SEMBRAR_V4 and backend.name == "ibm_fez" and not BITACORA.history("ibm_fez", 142):
    v4 = [("2026-09-23T04:00Z", 158.6, -27.04, "estable"), ("2026-09-23T04:02Z", 45.4, -25.32, "degradado"),
          ("2026-09-23T04:14Z", 37.6, -20.81, "degradado"), ("2026-09-23T04:16Z", 153.3, -27.05, "estable")]
    for t, t2, f, e in v4:
        BITACORA.append("ibm_fez", {142: {"q": 142, "T2star_us": t2, "detuning_kHz": f}}, {142: {"estado": e}}, when=t)
    print("Bitacora sembrada con las 4 corridas v4 de q142")'''))
cells.append(md("## 5. Sondeo (un job)"))
cells.append(code('''circs, specs = S.build_probe(len(cands), __import__("ddqpu").circuits.timing_from_backend(backend), pc)
cost = S.probe_cost(specs)
print(f"{len(circs)} circuitos | ~{cost['qpu_s']:.1f} s QPU | ~USD {cost['usd']:.2f} a precio Pay-As-You-Go")
manifest, counts = S.run_probe(backend, cands, OUT, pc, max_qpu_seconds=MAX_QPU_S, mode=MODE)
print("Job:", manifest["job_id"])'''))
cells.append(md("## 6. Diagnóstico y decisión"))
cells.append(code('''probe = S.analyze_probe(manifest, counts)
verdicts = {}
for q, r in probe.items():
    ref = S.reference_state(BITACORA.history(backend.name, q), _qubit_info(backend, q).t2_us)
    verdicts[q] = S.evaluate(r, ref)
    verdicts[q]["referencia"] = ref
print(S.summarize_probe(backend.name, probe, verdicts, manifest["cost"]))
print()
for q in S.rank_live(probe, verdicts):
    v = verdicts[q]
    g = v["ganancia_dd_estimada"]
    print(f"q{q}: {v['estado']} | {'; '.join(v['motivo'])}" + (f" | DD (eco/T2*) = {g:.2f}x" if g else ""))
BITACORA.append(backend.name, probe, verdicts, when=manifest["created_utc"])
best = S.rank_live(probe, verdicts)[0]
print(f"\\nQubit recomendado ahora: q{best}")'''))
cells.append(md("""## 7. Usar el resultado en tu circuito
- **Corrección de fase**: cada `delay` sin DD acumula 2π·f·τ de fase (27 kHz × 10 µs ≈ 1.7 rad en q142).
  `compensate_detuning` inserta un `rz` virtual después de cada `delay` (costo cero).
- **Qubit**: pasa `best` como `force_target` al notebook v4 o como `initial_layout` a tu transpilación."""))
cells.append(code('''from qiskit import QuantumCircuit
f = probe[best]["detuning_kHz"] or 0.0
demo = QuantumCircuit(1); demo.h(0); demo.delay(2500, 0, unit="dt"); demo.h(0)   # 10 us de espera
fixed = S.compensate_detuning(demo, {0: f}, backend.target.dt)
print(f"detuning q{best} = {f:+.2f} kHz -> fase acumulada en 10 us = {2*3.14159*f*1e3*10e-6:+.3f} rad")
print(fixed.draw(output="text"))'''))
cells.append(md("## 8. Historial por qubit"))
cells.append(code('''import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(8, 3.6))
for q in cands:
    h = BITACORA.history(backend.name, q)
    if not h: continue
    ax.plot(range(len(h)), [x["T2star_us"] or 0 for x in h], "-", lw=0.8, label=f"q{q}")
    for i, x in enumerate(h):
        ax.plot(i, x["T2star_us"] or 0, "o", color="#15803d" if x["estado"] == "estable" else "#b91c1c")
ax.set_xlabel("sondeo #"); ax.set_ylabel("T2* (us)"); ax.set_title("Bitacora: verde = estable, rojo = degradado")
ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(OUT / "bitacora.png", dpi=130)'''))
nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
out = ROOT / "notebooks" / "centinela_preflight.ipynb"
nbf.write(nb, out); print("escrito", out)
