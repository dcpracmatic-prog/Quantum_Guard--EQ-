"""Generate notebooks/dd_validacion_v4.ipynb embedding src/ddqpu as the single source of truth.

Usage: python tools/build_notebook.py
"""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "ddqpu"
MODULES = ["__init__.py", "circuits.py", "backend_utils.py", "analysis.py", "experiment.py", "plots.py", "sentinel.py"]

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = []
cells.append(md("""# QPU Dynamical Decoupling Validation — v4 (relays and optimized results)

One **single job** measures the following in the same batch and with the same physical layout:

| Block | Circuits | Purpose |
|---|---|---|
| Readout calibration | 2 (all-zero, all-one) | Mitigate ⟨X⟩/⟨Y⟩ and establish each qubit's readout floor |
| Main sweep | 3 protocols × ~16 times × X and Y bases | Quadrature coherence \\|ρ01\\| = √(⟨X⟩²+⟨Y⟩²): removes detuning oscillation |
| Relay references | target idle / target in \\|1⟩ at 3 times | **Paired** test of population transfer to each neighbor |
| Spectators in \\|1⟩ (ZZ) | free evolution and CPMG at 3 times | Measure how neighbor states affect target phase and whether DD cancels it |

## Changes from v1–v3
1. **Alias-free detuning.** v2/v3 sampled every 26–130 µs; actual detuning (~27 kHz) appeared as 54 kHz, and free T2 was estimated at 62 µs. The new sweep uses a dense segment (≤ 5 µs steps) and X/Y readout.
2. **Physically constrained fits.** Fix C = 0 (coherence decays to zero), weight by shot noise, and inflate errors by √χ² when drift is present. This removes the T2↔C degeneracy that produced error bars larger than the fitted value.
3. **Sound relay measurements.** Count all two-qubit gates (a transpiled SWAP becomes three CZ gates), verify initial and final layouts, and compare each neighbor's population with **its own** idle-target baseline using a two-proportion test and Bonferroni correction.
4. **Delays aligned to dt.** Free evolution, CPMG, and XY4 use exactly the same wait time, without rounding `UserWarning`s. Effective time including pulse duration is reported.
5. **Randomized circuit order** prevents slow drift from correlating with time.
6. **Shots per circuit** (PUBs with their own shot counts) and a **QPU time limit** before submission.
7. **`reuse` mode** reanalyzes a completed job without returning to the queue. **`sim` mode** tests the workflow for free with `FakeFez`.

## Requirements (Kaggle)
Internet enabled · `IBM_QUANTUM_TOKEN` secret · restart the kernel if prompted after `pip`.
"""))
cells.append(md("## 1. Installation"))
cells.append(code('%pip install -q "qiskit>=1.3" "qiskit-ibm-runtime>=0.30" qiskit-aer matplotlib scipy\nprint("OK")'))
cells.append(md("## 2. Embedded `ddqpu` package\nThis cell writes the repository package to `./ddqpu/`. If you cloned the repository, you can skip this cell and run `pip install -e .`."))

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
print("ddqpu", ddqpu.__version__, "ready")""")
cells.append(code("\n".join(writer)))

cells.append(md("""## 3. Configuration
- `MODE = "hardware"` submits the job to the QPU.
- `MODE = "sim"` uses `FakeFez` + Aer (free; a **negative control**: without low-frequency noise, DD should not extend T2).
- `MODE = "reuse"` loads the result for `REUSE_JOB_ID` from the saved `manifest.json`."""))
cells.append(code('''from pathlib import Path
from ddqpu.experiment import Config, build_batch, run_batch, reload_from_job, analyze, summarize, save_counts, to_jsonable
from ddqpu.backend_utils import get_service, rank_qubits, transpile_locked, estimate_qpu_seconds
from ddqpu.plots import plot_coherence, plot_relay

MODE = "hardware"            # "hardware" | "sim" | "reuse"
REUSE_JOB_ID = None          # e.g., "d..." to reanalyze without queueing
CHANNEL, INSTANCE = "ibm_cloud", "open-instance"
OUT_DIR = Path("/kaggle/working/ddqpu_run") if Path("/kaggle/working").exists() else Path("ddqpu_run")

cfg = Config(
    backend_name="ibm_fez",
    force_target=None,        # 142 to compare with v1-v3; None = best qubit by current calibration
    n_neighbors=2,
    n_cpmg=6, n_xy4_cycles=2,
    shots_main=1024,          # per basis (X and Y) => 2048 per coherence point
    shots_ref=2048, shots_cal=4096,
    enable_zz=True,
    max_qpu_seconds=240,
)
cfg'''))

cells.append(md("## 4. Backend, target qubit, neighbors, and control"))
cells.append(code('''if MODE == "sim":
    from qiskit_ibm_runtime.fake_provider import FakeFez
    backend, service = FakeFez(), None
else:
    service = get_service(CHANNEL, INSTANCE)
    names = [b.name for b in service.backends(operational=True, simulator=False)]
    print("Operational backends:", names)
    backend = service.backend(cfg.backend_name if cfg.backend_name in names else names[0])
print("Using:", backend.name)

print("\\nTop qubits (score = min(T2, 2*T1) / (1 + 50*sx_error + 10*readout_error)):")
for r in rank_qubits(backend, top=6):
    print(f"  q{r.q:<4} T1={r.t1_us:6.1f} us  T2={r.t2_us:6.1f} us  err_sx={r.sx_err:.2e}  err_ro={r.ro_err:.3f}  score={r.score:6.1f}")'''))

cells.append(md("## 5. Single batch, structural relay verification, and QPU runtime estimate"))
cells.append(code('''circs, specs, layout, timing, grid = build_batch(cfg, backend)
print("Physical layout [target, neighbors..., control]:", layout.physical,
      f"| control distance {layout.control_distance}")
print(f"Calibrated target T2 = {layout.target_t2_us:.1f} us | T1 = {layout.target_t1_us:.1f} us")
print("Time grid (us):", grid)
print(f"dt = {timing.dt*1e9:.2f} ns, granularity = {timing.granularity} dt, X pulse = {timing.x_duration_dt} dt")

from collections import Counter
print("Circuits by type:", dict(Counter(s.kind for s in specs)))
tcs_preview, report = transpile_locked(circs, backend, layout, cfg.optimization_level)
print("\\nStructural verification:", "OK - no 2-qubit gates, initial layout = final layout = " + str(layout.physical)
      if report["ok"] else report["issues"][:5])
print(f"Estimated QPU time: ~{estimate_qpu_seconds(specs, backend):.0f} s (limit: {cfg.max_qpu_seconds} s)")'''))

cells.append(md("## 6. Execution (one queue wait)"))
cells.append(code('''import json
if MODE == "reuse":
    assert REUSE_JOB_ID, "Set REUSE_JOB_ID"
    manifest, counts = reload_from_job(service, REUSE_JOB_ID, OUT_DIR / "manifest.json")
    save_counts(OUT_DIR, manifest, counts)
else:
    manifest, counts = run_batch(cfg, backend, circs, specs, layout, OUT_DIR, mode=MODE)
print("Raw data saved to", OUT_DIR / "raw_counts.json")'''))

cells.append(md("## 7. Analysis: quadrature coherence, fits, and DD extension"))
cells.append(code('''res = analyze(manifest, counts)
print(summarize(res, manifest))
(OUT_DIR / "results.json").write_text(json.dumps(to_jsonable(res), indent=1))
fig = plot_coherence(res, manifest, OUT_DIR / "coherencia.png")'''))

cells.append(md("## 8. Relays: paired test for each neighbor"))
cells.append(code('''lay = manifest["layout"]
names = {f"vecino_bit{i+1}": f"q{q}" for i, q in enumerate(lay["neighbors"])}
names["control"] = f"q{lay['control']} (control)"
print(f"{'spectator':>16} {'P1 idle':>9} {'P1 active':>10} {'Δ':>9} {'p':>8} {'P1 |1>':>9} {'Δ':>9} {'p':>8}")
for k, s in res["relay"].items():
    a, e = s["activo_vs_idle"], s["excitado_vs_idle"]
    print(f"{names[k]:>16} {a['p_ref']*100:8.3f}% {a['p_active']*100:9.3f}% {a['delta']*100:+8.3f}% {a['p_value']:8.3f}"
          f" {e['p_active']*100:8.3f}% {e['delta']*100:+8.3f}% {e['p_value']:8.3f}")
e0, e1 = res["readout"]["e0"], res["readout"]["e1"]
print("\\nPer-qubit readout error P(1|0):", [f"{x*100:.2f}%" for x in e0])
if res.get("zz"):
    for p, z in res["zz"].items():
        print(f"ZZ with neighbors in |1> ({p}): {z['zz_kHz']:+.2f} kHz  |",
              " ".join(f"t={r['t']:.0f}: dphi={r['dphi']:+.3f} rad, |c|1/|c|0={r['mag1']/max(r['mag0'],1e-3):.3f}" for r in z["rows"]))
fig = plot_relay(res, manifest, OUT_DIR / "relevos.png")'''))

cells.append(md("## 9. Hypothesis verdicts"))
cells.append(code('''print("=" * 72)
ext = res["extension"]
for p in ("cpmg", "xy4"):
    if p in ext:
        e = ext[p]
        print(f"H1 [{p.upper()} extends coherence]: T2_{p}/T2* = {e['ratio']:.2f} ± {e['err']:.2f} -> "
              + ("SUPPORTED (> 2σ)" if e["significant"] else "NOT SUPPORTED"))
fits = res["fits"]
if fits.get("free"):
    b = fits["free"]["beta"]; eb = fits["free"]["beta_err"]
    print(f"H2 [low-frequency noise in free evolution, β>1]: β = {b:.2f} ± {eb:.2f} -> "
          + ("SUPPORTED" if b - 1 > 2 * eb else "NOT SUPPORTED (approximately exponential decay)"))
d = res.get("detuning")
if d:
    print(f"H3 [the free-evolution zero crossing is caused by detuning]: δf = {d['f_kHz']:+.2f} ± {d['f_err_kHz']:.2f} kHz -> "
          + ("SUPPORTED" if abs(d["f_kHz"]) > 3 * d["f_err_kHz"] else "no appreciable detuning"))
rv = res["relay_verdict"]
print("H4 [no relay to neighbors]: " + ("REJECTED, relay on " + str(rv["flagged"]) if rv["relay_detected"]
      else f"SUPPORTED, transfer < {rv['worst_upper95']*100:.3f}% (95%)"))
print("Structural verification:", "no SWAP or 2-qubit gates" if manifest["structural_check"]["ok"] else "ISSUES")
print("=" * 72)'''))

cells.append(md("""## 10. Reference: reanalysis of v1–v3 (`ibm_fez`, q142)
Results from `scripts/reanalyze_previous.py` in this repository, based on previously collected data:

| Quantity | Previously reported | Reanalysis |
|---|---|---|
| Free detuning | 53.9 kHz (v2) | **27.14 ± 0.06 kHz** (v2 aliasing from 26 µs step) |
| Free T2* | 5.2 µs (v1), 61.8 µs (v2) | **139 ± 7 µs** (β = 1.00) |
| CPMG T2 | 55.9 / 249 / 138 µs | **178 ± 5 µs** (combined, C = 0) |
| XY4 T2 | 48 / 144 / 189 µs | **193 ± 9 µs** |
| CPMG/free extension | 10.7x, 3.2x | **1.28 ± 0.07x** |
| Relay to neighbors (v3) | “no relay” (invalid criterion) | **< 0.145%** (absolute 95% upper bound) |
| Optimal N (60 µs) | 16 | flat curve (χ²_red = 0.49): N does not matter from 2 to 24 |

With v4, if `force_target=142`, use these values as the comparison baseline.

### Remaining limitations
- Standard readout does not distinguish |2⟩: leakage into non-computational states would appear as coherence loss. A three-level discriminator could be added when supported by the backend.
- Long-range crosstalk: direct neighbors and one distant control are covered. `n_neighbors` could be increased, or a distance-2 ring could be measured without adding circuits.
- Drift between jobs (χ²_red of 4–11 between v2 and v3) suggests repeating v4 two or three times to report a mean with realistic dispersion.
"""))

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12"}})
out = ROOT / "notebooks" / "dd_validacion_v4.ipynb"
nbf.write(nb, out)
print("Wrote", out)
