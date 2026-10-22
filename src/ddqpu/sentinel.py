"""Sentinel: a few-second QPU preflight probe to decide, just before an expensive job,
which qubit to use, whether to enable DD, and which phase correction to apply.

Physical motivation (v4 runs on `ibm_fez`, q142, 2026-09-23):
- The qubit switches between two states over minutes: T2* ~155 us and ~40 us, with
  detuning of -27.0 kHz and -21 to -25 kHz. This is the signature of a fluctuating two-level system (TLS)
  coupled to the qubit: telegraph-like frequency jumps correlated with dephasing.
- Published calibration (T2 = 265 us) is updated about once per day and does not capture these jumps.
- Frequency is the least expensive variable to measure and changes with the state, so it is used as a
  "fingerprint" alongside T2*.

Probe design (one job, all candidates IN PARALLEL in the same circuits):
- Quadrature Ramsey (X and Y bases) in a dense segment (<= 10 us steps, alias-free up to 50 kHz),
  plus 2 long points for T2*.
- 2 CPMG points (multi-pulse echo) to estimate current DD improvement.
- 2 T1 points to separate pure dephasing: Gamma_phi = 1/T2* - 1/(2 T1).
- Dedicated readout calibration.
- About 28 circuits x 512 shots = 6–8 seconds of QPU time for K candidates in parallel.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from qiskit import QuantumCircuit

from .circuits import Timing, CircuitSpec, timing_from_backend, _dd_block, _pulse_sequence
from .backend_utils import rank_qubits, bfs_distances, _qubit_info
from . import analysis as A

USD_PER_MIN_PAYG = 96.0   # IBM Pay-As-You-Go (precio publico de lista, 2026)


# ------------------------------------------------------------------ configuracion
@dataclass
class ProbeConfig:
    ramsey_dense_us: List[float] = field(default_factory=lambda: [2, 5, 10, 15, 20, 25, 30, 40])
    ramsey_long_us: List[float] = field(default_factory=lambda: [80, 160])
    echo_us: List[float] = field(default_factory=lambda: [80, 160])
    t1_us: List[float] = field(default_factory=lambda: [80, 160])
    n_cpmg: int = 6
    shots: int = 512
    shots_cal: int = 2048
    n_candidates: int = 4
    min_separation: int = 3          # distancia minima en el grafo entre candidatos (evita ZZ entre ellos)
    optimization_level: int = 1


def choose_candidates(backend, k: int = 4, min_separation: int = 3, must_include: Sequence[int] = ()) -> List[int]:
    """Select top-k qubits by calibration with minimum separation on the coupling graph."""
    chosen = [int(q) for q in must_include]
    for r in rank_qubits(backend, top=10 * k + len(chosen)):
        if len(chosen) >= k:
            break
        if r.q in chosen:
            continue
        d = bfs_distances(backend, r.q)
        if all(d.get(c, 99) >= min_separation for c in chosen):
            chosen.append(r.q)
    return chosen


# ------------------------------------------------------------------ circuitos
def _ramsey(n: int, t_dt: int, basis: str, timing: Timing, pulses: Sequence[str] = ()):
    qc = QuantumCircuit(n, n)
    qc.h(range(n))
    qc.barrier()
    for q in range(n):
        _dd_block(qc, q, t_dt, list(pulses), timing)
    qc.barrier()
    if basis == "Y":
        qc.sdg(range(n))
    qc.h(range(n))
    qc.measure(range(n), range(n))
    return qc


def _t1(n: int, t_dt: int):
    qc = QuantumCircuit(n, n)
    qc.x(range(n))
    qc.barrier()
    if t_dt > 0:
        qc.delay(t_dt, range(n), unit="dt")
    qc.barrier()
    qc.measure(range(n), range(n))
    return qc


def build_probe(n_qubits: int, timing: Timing, pc: ProbeConfig = ProbeConfig()):
    """Circuitos logicos del sondeo sobre n_qubits candidatos en paralelo."""
    circs, specs = [], []

    def add(qc, spec, shots):
        spec.shots = shots
        qc.name = f"{spec.kind}_{spec.protocol}_{spec.basis}_{spec.t_us:.1f}"
        circs.append(qc)
        specs.append(spec)

    for st in ("0", "1"):
        qc = QuantumCircuit(n_qubits, n_qubits)
        if st == "1":
            qc.x(range(n_qubits))
        qc.measure(range(n_qubits), range(n_qubits))
        add(qc, CircuitSpec(kind=f"cal{st}"), pc.shots_cal)
    for t in list(pc.ramsey_dense_us) + list(pc.ramsey_long_us):
        t_dt = timing.us_to_dt(t)
        for b in ("X", "Y"):
            add(_ramsey(n_qubits, t_dt, b, timing), CircuitSpec(kind="ramsey", protocol="free", basis=b,
                t_us=timing.dt_to_us(t_dt), t_eff_us=timing.dt_to_us(t_dt)), pc.shots)
    pulses = _pulse_sequence("cpmg", pc.n_cpmg, 1)
    for t in pc.echo_us:
        t_dt = timing.us_to_dt(t)
        for b in ("X", "Y"):
            add(_ramsey(n_qubits, t_dt, b, timing, pulses), CircuitSpec(kind="echo", protocol="cpmg", basis=b,
                t_us=timing.dt_to_us(t_dt), t_eff_us=timing.dt_to_us(t_dt + len(pulses) * timing.x_duration_dt),
                n_pulses=len(pulses)), pc.shots)
    for t in pc.t1_us:
        t_dt = timing.us_to_dt(t)
        add(_t1(n_qubits, t_dt), CircuitSpec(kind="t1", basis="Z", t_us=timing.dt_to_us(t_dt),
                                             t_eff_us=timing.dt_to_us(t_dt)), pc.shots)
    return circs, specs


def probe_cost(specs, backend=None, usd_per_min: float = USD_PER_MIN_PAYG, rep_delay_s: float = 250e-6,
               meas_s: float = 1.6e-6):
    secs = sum(s.shots * (s.t_eff_us * 1e-6 + meas_s + rep_delay_s) for s in specs) + 2.0
    return {"qpu_s": float(secs), "usd": float(secs / 60.0 * usd_per_min)}


def run_probe(backend, candidates: Sequence[int], out_dir: Path, pc: ProbeConfig = ProbeConfig(),
              max_qpu_seconds: float = 20.0, mode: str = "hardware"):
    """Transpile with a fixed candidate layout, verify no 2-qubit/SWAP gates, and submit ONE job."""
    from qiskit import transpile
    from qiskit_ibm_runtime import SamplerV2
    timing = timing_from_backend(backend)
    circs, specs = build_probe(len(candidates), timing, pc)
    tcs = transpile(circs, backend, initial_layout=list(candidates), optimization_level=pc.optimization_level,
                    scheduling_method=None)
    for tc in tcs:
        n2q = sum(1 for ins in tc.data if ins.operation.num_qubits == 2 and ins.operation.name != "barrier")
        if n2q:
            raise RuntimeError(f"{tc.name}: {n2q} compuertas de 2 qubits (posible SWAP)")
    cost = probe_cost(specs)
    if mode == "hardware" and cost["qpu_s"] > max_qpu_seconds:
        raise RuntimeError(f"Estimated probe time {cost['qpu_s']:.1f}s > {max_qpu_seconds}s")
    job = SamplerV2(mode=backend).run([(tc, None, s.shots) for tc, s in zip(tcs, specs)])
    manifest = {"job_id": job.job_id(), "backend": backend.name, "candidates": list(map(int, candidates)),
                "specs": [s.to_dict() for s in specs], "probe_config": asdict(pc), "cost": cost,
                "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    res = job.result()
    counts = [A.counts_from_pub(res[i]) for i in range(len(specs))]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "probe_raw.json").write_text(json.dumps({**manifest, "counts": counts}))
    return manifest, counts


# ------------------------------------------------------------------ analisis
def _fit_fixed_amp(t, y, se, amp):
    """Fit y = amp * exp(-t/T): estimate T with weighted least squares in log space."""
    t, y, se = map(lambda a: np.asarray(a, float), (t, y, se))
    ok = (y > 0.02) & np.isfinite(y)
    if ok.sum() == 0:
        return None, None
    rates, w = [], []
    for ti, yi, si in zip(t[ok], y[ok], se[ok]):
        r = -math.log(min(yi / amp, 0.999)) / ti
        er = si / yi / ti
        rates.append(r); w.append(1 / max(er, 1e-9) ** 2)
    rates, w = np.array(rates), np.array(w)
    r = float(np.sum(w * rates) / np.sum(w)); er = float(math.sqrt(1 / np.sum(w)))
    if r <= 0:
        return None, None
    return 1 / r, er / r ** 2


def analyze_probe(manifest: dict, counts: list) -> Dict[int, dict]:
    specs, cands = manifest["specs"], manifest["candidates"]
    recs = list(zip(specs, counts))
    cal0 = next(c for s, c in recs if s["kind"] == "cal0")
    cal1 = next(c for s, c in recs if s["kind"] == "cal1")
    e0, e1 = A.readout_errors(cal0, cal1, len(cands))
    out = {}
    for b, q in enumerate(cands):
        def xy(kind):
            ts = sorted({s["t_us"] for s, _ in recs if s["kind"] == kind})
            X, Y, SX, SY = [], [], [], []
            for t in ts:
                cx = next(c for s, c in recs if s["kind"] == kind and s["t_us"] == t and s["basis"] == "X")
                cy = next(c for s, c in recs if s["kind"] == kind and s["t_us"] == t and s["basis"] == "Y")
                x, sx = A.mitigated_expectation(cx, b, e0[b], e1[b])
                y, sy = A.mitigated_expectation(cy, b, e0[b], e1[b])
                X.append(x); Y.append(y); SX.append(sx); SY.append(sy)
            mag, se, ph = A.coherence_from_xy(X, Y, SX, SY)
            return np.array(ts), mag, se, ph
        tr, mr, sr, pr = xy("ramsey")
        det = A.detuning_from_phase(tr, pr, mr)
        fit = A.fit_envelope(tr, mr, sr, beta_fixed=1.0, label=f"q{q}")
        amp = fit["A"] if fit else float(mr[0])
        te, me, se_, _ = xy("echo")
        T2e, T2e_err = _fit_fixed_amp(te, me, se_, amp)
        # T1: P1(t) mitigada, amplitud ~1 tras mitigar
        t1s, p1s, s1s = [], [], []
        for s, c in recs:
            if s["kind"] == "t1":
                z, sz = A.mitigated_expectation(c, b, e0[b], e1[b])
                t1s.append(s["t_us"]); p1s.append((1 - z) / 2); s1s.append(sz / 2)
        T1, T1_err = _fit_fixed_amp(t1s, p1s, s1s, 1.0)
        r = {"q": int(q), "readout_e0": float(e0[b]), "readout_e1": float(e1[b]),
             "detuning_kHz": det["f_kHz"] if det else None, "detuning_err_kHz": det["f_err_kHz"] if det else None,
             "T2star_us": fit["T2"] if fit else None, "T2star_err_us": fit["T2_err"] if fit else None,
             "T2echo_us": T2e, "T2echo_err_us": T2e_err, "T1_us": T1, "T1_err_us": T1_err}
        if r["T2star_us"] and T1:
            r["Gamma_phi_1_ms"] = 1e3 * (1 / r["T2star_us"] - 1 / (2 * T1))
        out[int(q)] = r
    return out


# ------------------------------------------------------------------ bitacora y decision
class Bitacora:
    """JSONL history by (backend, qubit). This product data source accumulates per-qubit state
    statistics over time (degraded-state fraction, dwell times)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, backend: str, probe: Dict[int, dict], verdicts: Dict[int, dict], when: Optional[str] = None):
        when = when or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            for q, r in probe.items():
                f.write(json.dumps({"t": when, "backend": backend, **r, "estado": verdicts[q]["estado"]}) + "\n")

    def history(self, backend: str, q: int) -> List[dict]:
        if not self.path.exists():
            return []
        rows = [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]
        return [r for r in rows if r["backend"] == backend and r["q"] == q]


def reference_state(history: List[dict], T2_cal_us: Optional[float] = None) -> dict:
    """Fingerprint of the 'good' state: median of stable entries (or all entries if unlabeled)."""
    good = [h for h in history if h.get("estado") == "estable" and h.get("T2star_us")]
    pool = good or [h for h in history if h.get("T2star_us")]
    if pool:
        t2 = float(np.median([h["T2star_us"] for h in pool]))
        f = [h["detuning_kHz"] for h in pool if h.get("detuning_kHz") is not None]
        return {"T2star_us": t2, "detuning_kHz": float(np.median(f)) if f else None, "n": len(pool)}
    # Without history: T2* ~ 0.5 x calibrated T2 (for q142: 155/265 = 0.59).
    return {"T2star_us": 0.5 * T2_cal_us if T2_cal_us else None, "detuning_kHz": None, "n": 0}


def evaluate(r: dict, ref: dict, min_ratio: float = 0.6, max_df_kHz: float = 1.0) -> dict:
    """Return qubit state and recommended action."""
    why = []
    estado = "estable"
    if r.get("T2star_us") is None:
        return {"estado": "sin_datos", "accion": "re-sondear", "motivo": ["T2* fit failed"]}
    if ref.get("T2star_us") and r["T2star_us"] < min_ratio * ref["T2star_us"]:
        estado = "degradado"; why.append(f"T2* {r['T2star_us']:.0f} us < {min_ratio:.0%} of reference {ref['T2star_us']:.0f} us")
    if ref.get("detuning_kHz") is not None and r.get("detuning_kHz") is not None:
        tol = max(max_df_kHz, 3 * (r.get("detuning_err_kHz") or 0))
        if abs(r["detuning_kHz"] - ref["detuning_kHz"]) > tol:
            estado = "degradado"; why.append(f"frequency shift {r['detuning_kHz'] - ref['detuning_kHz']:+.1f} kHz")
    if estado == "estable":
        accion = "ejecutar"
    else:
        accion = "cambiar de qubit o esperar y re-sondear; si se ejecuta, activar DD"
    gain = None
    if r.get("T2echo_us") and r.get("T2star_us"):
        gain = r["T2echo_us"] / r["T2star_us"]
    return {"estado": estado, "accion": accion, "motivo": why or ["within the reference fingerprint"],
            "ganancia_dd_estimada": gain,
            "correccion_fase_kHz": r.get("detuning_kHz")}


def rank_live(probe: Dict[int, dict], verdicts: Dict[int, dict]) -> List[int]:
    """Rank by current measured T2* (stable qubits first)."""
    return sorted(probe, key=lambda q: (verdicts[q]["estado"] != "estable", -(probe[q].get("T2star_us") or 0)))


# ------------------------------------------------------------------ correccion de fase (Z virtual)
def compensate_detuning(qc: QuantumCircuit, detuning_kHz: Dict[int, float], dt: float) -> QuantumCircuit:
    """Insert rz(-2*pi*f*tau) after each delay on qubit q (circuit index).
    Under the static-detuning model, this exactly cancels accumulated phase in each segment, with or without
    intermediate DD pulses (both are Z rotations that commute with free evolution).
    IBM virtual rz gates have zero time and error cost."""
    out = qc.copy_empty_like()
    for ins in qc.data:
        out.append(ins.operation, ins.qubits, ins.clbits)
        if ins.operation.name == "delay":
            dur = ins.operation.duration
            unit = ins.operation.unit
            tau = dur * dt if unit == "dt" else dur * {"s": 1, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}[unit]
            for qb in ins.qubits:
                q = qc.find_bit(qb).index
                if q in detuning_kHz and detuning_kHz[q]:
                    out.rz(-2 * math.pi * detuning_kHz[q] * 1e3 * tau, q)
    return out


def summarize_probe(backend_name: str, probe: Dict[int, dict], verdicts: Dict[int, dict], cost: dict) -> str:
    L = [f"Centinela | backend={backend_name} | costo ~{cost['qpu_s']:.1f} s QPU (~USD {cost['usd']:.2f} a precio PAYG)"]
    L.append(f"{'q':>5} {'T2*':>8} {'echo T2':>8} {'T1':>8} {'detuning':>10} {'state':>10}  action")
    for q in rank_live(probe, verdicts):
        r, v = probe[q], verdicts[q]
        fmt = lambda x: f"{x:8.1f}" if x else "     n/a"  # noqa: E731
        det = f"{r['detuning_kHz']:+9.2f}k" if r.get("detuning_kHz") is not None else "       n/a"
        L.append(f"{q:>5} {fmt(r.get('T2star_us'))} {fmt(r.get('T2echo_us'))} {fmt(r.get('T1_us'))} {det} {v['estado']:>10}  {v['accion']}")
    return "\n".join(L)


__all__ = ["ProbeConfig", "choose_candidates", "build_probe", "probe_cost", "run_probe", "analyze_probe",
           "Bitacora", "reference_state", "evaluate", "rank_live", "compensate_detuning", "summarize_probe",
           "USD_PER_MIN_PAYG"]
_ = _qubit_info
