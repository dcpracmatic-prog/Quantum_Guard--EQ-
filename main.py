#!/usr/bin/env python3
"""Edge Quantum Guard: complete pipeline based on the ABBA ablation notebook.
Includes Eyes/AOM, Reflexes/MORPH, causal Judgment, Hands/DD, QAOA MaxCut,
A/C/D/E arms, PRE/POST snapshots, budget controls, and statistical contrasts.
Hardware mode requires --mode hardware --confirm-spend and an IBM token in the environment.
"""
import argparse as _argparse
import os as _os
import sys as _sys

_parser = _argparse.ArgumentParser(description="Full EQG QAOA ablation: A/C/D/E.")
_parser.add_argument("--mode", choices=("sim", "hardware"), default="sim")
_parser.add_argument("--backend", default="ibm_kingston")
_parser.add_argument("--confirm-spend", action="store_true")
_parser.add_argument("--smoke", action="store_true", help="Run a quick local check with fewer shots.")
_parser.add_argument("--output-dir", default="outputs/eqg_ablation")
_parser.add_argument("--list-backends", action="store_true")
_args, _unknown = _parser.parse_known_args()

if _args.list_backends:
    _token = _os.getenv("IBM_QUANTUM_TOKEN") or _os.getenv("QISKIT_IBM_TOKEN")
    if not _token:
        _sys.exit("ERROR: set IBM_QUANTUM_TOKEN or QISKIT_IBM_TOKEN to query the IBM catalog.")
    from qiskit_ibm_runtime import QiskitRuntimeService
    try:
        _service = QiskitRuntimeService(channel="ibm_cloud", token=_token.strip(),
                                        instance=_os.getenv("IBM_QUANTUM_INSTANCE", "open-instance"))
    except Exception:
        _service = QiskitRuntimeService(token=_token.strip())
    for _backend in _service.backends():
        try:
            _status = _backend.status()
            print("%-24s qubits=%-4s operational=%-5s pending=%s" % (
                _backend.name, _backend.num_qubits, getattr(_status, "operational", "unknown"),
                getattr(_status, "pending_jobs", "unknown")))
        except Exception:
            print(_backend.name)
    _sys.exit(0)

if _args.mode == "hardware":
    if not _args.confirm_spend:
        _parser.error("hardware mode requires --confirm-spend; review the QPU budget first.")
    if not (_os.getenv("IBM_QUANTUM_TOKEN") or _os.getenv("QISKIT_IBM_TOKEN")):
        _parser.error("hardware mode requires IBM_QUANTUM_TOKEN or QISKIT_IBM_TOKEN.")
elif _args.confirm_spend:
    _parser.error("--confirm-spend is only used with --mode hardware.")
if _args.smoke and _args.mode != "sim":
    _parser.error("--smoke is only available in sim mode.")

_os.environ["EQG_MODE"] = _args.mode
_os.environ["EQG_BACKEND"] = _args.backend
_os.environ["EQG_CONFIRM_SPEND"] = "true" if _args.confirm_spend else "false"
_os.environ["EQG_OUTPUT_DIR"] = _args.output_dir
if _args.smoke:
    _os.environ.update({
        "EQG_N_RESTARTS": "2", "EQG_SHOTS_WORK": "128", "EQG_REPS_PER_BLOCK": "1",
        "EQG_SHOTS_SNAP_FULL": "8", "EQG_SHOTS_SNAP_LIGHT": "8", "EQG_OVERHEAD_S": "0.05",
        "EQG_HARD_CAP_S": "24.0", "EQG_QPU_REMAINING_S": "40.0"
    })

import os, sys, time, json, math, uuid, warnings, argparse, getpass
from pathlib import Path
from typing import Dict, List, Optional, Sequence
import builtins as _builtins
import numpy as np
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ============================ PRE-REGISTRO ============================
CONFIRM_SPEND = os.getenv("EQG_CONFIRM_SPEND", "false").lower() in ("1", "true", "yes")
MODE = os.getenv("EQG_MODE", "sim").lower()
BACKEND_NAME = os.getenv("EQG_BACKEND", "ibm_kingston")
SEED = int(os.getenv("EQG_SEED", "7"))

N_QAOA, P_LAYERS, N_RESTARTS = 8, 2, int(os.getenv("EQG_N_RESTARTS", "40"))
SHOTS_WORK = int(os.getenv("EQG_SHOTS_WORK", "1500"))
REPS_PER_BLOCK = int(os.getenv("EQG_REPS_PER_BLOCK", "2"))
BLOCK_ORDERS = [["A", "C", "D", "E"], ["E", "D", "C", "A"]]
SHOTS_SNAP_FULL = int(os.getenv("EQG_SHOTS_SNAP_FULL", "128"))
SHOTS_SNAP_LIGHT = int(os.getenv("EQG_SHOTS_SNAP_LIGHT", "96"))
PROBE_DELAY_US = 20.0
DD_SEQUENCE = "CPMG"

T_SHOT_S = 331.6e-6
OVERHEAD_S = float(os.getenv("EQG_OVERHEAD_S", "2.5"))
QPU_REMAINING_S = float(os.getenv("EQG_QPU_REMAINING_S", "40.0"))
HARD_CAP_S = float(os.getenv("EQG_HARD_CAP_S", "24.0"))

HEALTH_STABLE, HEALTH_DEGRADED = 0.65, 0.45
REL_THR, FLAG_REL = 0.85, 0.75
TARGET_INTEGRITY, REMAP_TOL, EDGE_W = 0.35, 0.05, 8.0
Z_SIG = 2.0
JOB_TIMEOUT_S = 1800

OUT = Path(os.getenv("EQG_OUTPUT_DIR", "outputs/eqg_ablation"))
OUT.mkdir(parents=True, exist_ok=True)

from ddqpu.guard import FlowGuard
from ddqpu.privacy import create_run_key, write_encrypted_artifact, decrypt_artifact

def print(*args, **kwargs):
    """Default console output is deliberately non-sensitive; detailed metrics stay encrypted."""
    message = " ".join(str(arg) for arg in args)
    if message == "EQG_PIPELINE_COMPLETED":
        _builtins.print(message, **kwargs)
    elif message.startswith("Verified artifacts:"):
        _builtins.print("Private artifacts encrypted and verified.")
    elif message.startswith("Saved to"):
        _builtins.print("EQG private run prepared; key file:", KEY_PATH, "| run_id:", RUN_ID)

RUN_ID = uuid.uuid4().hex
RUN_OWNER = os.getenv("EQG_RUN_OWNER") or f"local:{getpass.getuser()}"
KEY_PATH = Path(os.getenv("EQG_KEY_OUTPUT", str(OUT.parent / f"{RUN_ID}.key")))
_legacy_plaintext = [OUT / "report.json", OUT / "ablation.png"]
if any(p.exists() for p in _legacy_plaintext):
    raise RuntimeError(
        "Legacy plaintext EQG artifacts were found. Move them to private storage "
        "or remove them before running this version: " +
        ", ".join(str(p) for p in _legacy_plaintext if p.exists())
    )
GUARD = FlowGuard(RUN_ID, RUN_OWNER, allow_community_publication=False)
GUARD.transition("PRECHECK", reason="validate policy and prepare per-run key")

def est_job_s(shots):
    return OVERHEAD_S + sum(shots) * T_SHOT_S

_n_arm_circ = 4 * REPS_PER_BLOCK
EST_PRE = est_job_s([SHOTS_SNAP_FULL] * 4 * 3)
EST_BLOCK = est_job_s([SHOTS_WORK] * _n_arm_circ + [SHOTS_SNAP_LIGHT] * 3)
EST_POST = est_job_s([SHOTS_SNAP_FULL] * 4 * 4)
EST_TOTAL = EST_PRE + len(BLOCK_ORDERS) * EST_BLOCK + EST_POST
print("Estimate: PRE %.2f + %d x block %.2f + POST %.2f = %.2f s (cap %.1f s, %.0f s remaining)" % (
    EST_PRE, len(BLOCK_ORDERS), EST_BLOCK, EST_POST, EST_TOTAL, HARD_CAP_S, QPU_REMAINING_S))
assert EST_TOTAL <= HARD_CAP_S, "The plan exceeds the hard cap"

KEY_INFO = create_run_key(RUN_ID, RUN_OWNER, KEY_PATH)
GUARD.send(
    "eqg->owner", "run_key_issued",
    json.dumps({"run_id": RUN_ID, "key_id": KEY_INFO["key_id"]}, sort_keys=True).encode(),
    visibility="private",
)
GUARD.transition("AUTHORIZED", reason="budget approved and unique key created")


def _try(fn, default=None):
    try:
        v = fn()
        return default if v is None else v
    except Exception:
        return default

def cal_health(t1_us, t2_us, ro):
    t1 = t1_us if t1_us else 100.0
    t2 = t2_us if t2_us else 80.0
    ro = ro if ro is not None else 0.03
    h = 0.35 * min(t1 / 200.0, 1.0) + 0.35 * min(t2 / 150.0, 1.0) + 0.30 * (1.0 - min(ro / 0.08, 1.0))
    return float(np.clip(h, 0.02, 1.0))

def estado_from_h(h):
    return "estable" if h >= HEALTH_STABLE else ("degradado" if h >= HEALTH_DEGRADED else "inestable")

def read_cal(backend, qs, refresh=False):
    props = None
    try:
        props = backend.properties(refresh=True) if refresh else backend.properties()
    except Exception:
        props = _try(lambda: backend.properties())
    tgt = getattr(backend, "target", None)
    out = {}
    for q in qs:
        t1 = _try(lambda: props.t1(q)) if props is not None else None
        t2 = _try(lambda: props.t2(q)) if props is not None else None
        ro = _try(lambda: props.readout_error(q)) if props is not None else None
        if (t1 is None or t2 is None) and tgt is not None:
            qp = _try(lambda: tgt.qubit_properties[q])
            if qp is not None:
                t1 = t1 if t1 is not None else getattr(qp, "t1", None)
                t2 = t2 if t2 is not None else getattr(qp, "t2", None)
        if ro is None and tgt is not None:
            ro = _try(lambda: tgt["measure"][(q,)].error)
        out[int(q)] = {"t1_us": None if t1 is None else float(t1) * 1e6,
                       "t2_us": None if t2 is None else float(t2) * 1e6,
                       "ro": None if ro is None else float(ro)}
    stamp = _try(lambda: str(props.last_update_date), "desconocido") if props is not None else "desconocido"
    return out, stamp

def read_edge_err(backend):
    err, tgt = {}, getattr(backend, "target", None)
    if tgt is None:
        return err
    for g in ("cz", "ecr", "cx"):
        if g in tgt.operation_names:
            for qargs, inst in tgt[g].items():
                if inst is not None and getattr(inst, "error", None) is not None and len(qargs) == 2:
                    err[frozenset((int(qargs[0]), int(qargs[1])))] = float(inst.error)
            if err:
                break
    return err

def coupling_edges(backend):
    edges = []
    try:
        cm = backend.coupling_map
        if cm is not None:
            edges = [(int(a), int(b)) for a, b in cm.get_edges()]
    except Exception:
        pass
    return edges or [(i, i + 1) for i in range(15)]

class Reflejos:
    """MORPH: mejor camino fisico conectado de k qubits. Con memoria: excluye qubits ya marcados."""
    def __init__(self):
        self.blacklist = set()
    def score_path(self, path, hm, edge_err):
        h = float(np.mean([hm[q] for q in path]))
        es = [edge_err.get(frozenset((a, b)), 0.01) for a, b in zip(path[:-1], path[1:])]
        return h - EDGE_W * (float(np.mean(es)) if es else 0.0)
    def select(self, hm, edges, edge_err, k, exclude=(), beam=200):
        excl = set(exclude)
        ok = {q for q, h in hm.items() if estado_from_h(h) != "inestable" and q not in excl}
        adj = {q: set() for q in ok}
        for a, b in edges:
            if a in ok and b in ok:
                adj[a].add(b); adj[b].add(a)
        frontier = [[q] for q in sorted(ok)]
        for _ in range(k - 1):
            nxt = [p + [n] for p in frontier for n in adj[p[-1]] if n not in p]
            if not nxt:
                return None
            nxt.sort(key=lambda p: -self.score_path(p, hm, edge_err))
            frontier = nxt[:beam]
        best = max(frontier, key=lambda p: self.score_path(p, hm, edge_err))
        return {"selected": list(best), "score": self.score_path(best, hm, edge_err)}

def layout_connected(layout, edges):
    es = {frozenset(e) for e in edges}
    return all(frozenset((a, b)) in es for a, b in zip(layout[:-1], layout[1:]))

class AOMMembrane:
    def __init__(self, capacity=4, lo=0.25, hi=0.45):
        self.buf, self.cap, self.lo, self.hi, self.regime = [], capacity, lo, hi, "ESTABLE"
    def push(self, f):
        self.buf = (self.buf + [f])[-self.cap:]
        sm = f if len(self.buf) == 1 else 0.6 * f + 0.4 * (sum(self.buf[:-1]) / (len(self.buf) - 1))
        r = self.regime
        if r == "ESTABLE":
            self.regime = "CONFLICTO" if sm >= 0.70 else ("INESTABLE" if sm >= self.hi else r)
        elif r == "INESTABLE":
            self.regime = "ESTABLE" if sm < self.lo else ("CONFLICTO" if sm >= 0.70 else r)
        else:
            self.regime = "ESTABLE" if sm < self.lo else ("INESTABLE" if sm < self.hi else r)
        return self.regime, sm

class Ojos:
    def __init__(self):
        self.membrane = AOMMembrane()
    def observe(self, qubits, hm, rel_mean=None, flagged=None):
        qs = [int(q) for q in qubits]
        raw = float(np.mean([1.0 - hm[q] for q in qs]))
        if rel_mean is not None:
            raw = 1.0 - float(np.clip(rel_mean, 0.0, 1.0))
        regime, sm = self.membrane.push(raw)
        est = [estado_from_h(hm[q]) for q in qs]
        return {"friction": raw, "smoothed": sm, "regime": regime,
                "n_degradado": est.count("degradado"), "n_inestable": est.count("inestable"),
                "n_estable": est.count("estable"), "health_mean": float(np.mean([hm[q] for q in qs])),
                "rel_mean": rel_mean, "flagged": list(flagged or [])}

def planificar(lh, layout, alt, cur_score):
    flagged = lh["flagged"]
    need_dd = ((lh["rel_mean"] is not None and lh["rel_mean"] < REL_THR) or (lh["n_degradado"] + lh["n_inestable"]) > 0
               or lh["health_mean"] < HEALTH_STABLE or bool(flagged))
    remap = bool(flagged) and alt is not None and alt["score"] >= cur_score - REMAP_TOL and set(alt["selected"]) != set(layout)
    calm = (not need_dd) and (not flagged)
    opts = [dict(tipo="ninguna", cost=0.0, gain=0.55 if calm else 0.0, reason="stable regime; no intervention" if calm else "no intervention")]
    if need_dd:
        opts.append(dict(tipo="dd_condicional", cost=0.25, gain=0.30 if flagged else 0.55, reason="conditional DD based on coherence/health"))
    if remap:
        opts.append(dict(tipo="remap_morph", cost=0.40, gain=0.90, reason="flagged qubits %s; remap to %s" % (flagged, alt["selected"])))
    if lh["regime"] == "CONFLICTO" and lh["n_estable"] == 0:
        opts.append(dict(tipo="abortar", cost=0.0, gain=0.1, reason="CONFLICT: no stable qubits"))
    elig = [o for o in opts if o["gain"] >= TARGET_INTEGRITY]
    ch = min(elig, key=lambda o: o["cost"]) if elig else max(opts, key=lambda o: o["gain"] / max(o["cost"], 0.01))
    t = ch["tipo"]
    return {"tipo": t, "layout": list(alt["selected"]) if t == "remap_morph" else list(layout),
            "activate_dd": t in ("dd_condicional", "remap_morph") and need_dd, "reason": ch["reason"]}


from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import XGate, YGate
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import ALAPScheduleAnalysis, PadDynamicalDecoupling

def apply_dd(tcs, backend, qubits):
    seq = [XGate(), XGate()]          # CPMG
    target = backend.target
    pm = PassManager([ALAPScheduleAnalysis(target=target),
                      PadDynamicalDecoupling(target=target, dd_sequence=seq, qubits=[int(q) for q in qubits],
                                             pulse_alignment=getattr(target, "pulse_alignment", 1), skip_reset_qubits=False)])
    out, added = [], 0
    cnt = lambda c: int(c.count_ops().get("x", 0) + c.count_ops().get("y", 0))
    for tc in tcs:
        try:
            tc2 = pm.run(tc)
        except Exception as e:
            print("[DD] ERROR (%s) -> circuit without DD" % e); tc2 = tc
        added += cnt(tc2) - cnt(tc); out.append(tc2)
    return out, added

def probe_delay(backend, us=PROBE_DELAY_US):
    dt = getattr(backend, "dt", None)
    if not dt:
        return float(us), "us"
    g = int(getattr(getattr(backend, "target", None), "granularity", 16) or 16)
    return max(g, int(round(us * 1e-6 / dt / g)) * g), "dt"

KINDS_LIGHT, KINDS_FULL = ["X", "Y", "Z1"], ["X", "Y", "Z1", "Z0"]

def snap_circuits(n, delay, unit, full):
    out = []
    for k in (KINDS_FULL if full else KINDS_LIGHT):
        qc = QuantumCircuit(n, n, name="snap_" + k)
        for i in range(n):
            if k in ("X", "Y"): qc.h(i)
            elif k == "Z1": qc.x(i)
        qc.barrier()
        for i in range(n): qc.delay(delay, i, unit=unit)
        qc.barrier()
        for i in range(n):
            if k == "Y": qc.sdg(i)
            if k in ("X", "Y"): qc.h(i)
        qc.measure(range(n), range(n))
        out.append(qc)
    return out

def bit_marginals(counts, n):
    tot = sum(counts.values()) or 1
    m = np.zeros(n)
    for k, v in counts.items():
        s = str(k).replace(" ", "")
        if s.startswith("0x"): s = format(int(s, 16), "0%db" % n)
        s = s.zfill(n)[-n:][::-1]
        for b in range(n):
            if s[b] == "1": m[b] += v
    return m / tot, tot

def analyze_snap(cts, layout, cal, delay_us=PROBE_DELAY_US):
    n = len(layout)
    pX, N = bit_marginals(cts["X"], n); pY, _ = bit_marginals(cts["Y"], n); p1, _ = bit_marginals(cts["Z1"], n)
    x, y = 1 - 2 * pX, 1 - 2 * pY
    coh = np.minimum(np.hypot(x, y), 1.0)
    sx = 2 * np.sqrt(np.clip(pX * (1 - pX), 1e-4, None) / N); sy = 2 * np.sqrt(np.clip(pY * (1 - pY), 1e-4, None) / N)
    se_coh = np.sqrt((x * sx) ** 2 + (y * sy) ** 2) / np.maximum(coh, 0.3)
    se_p1 = np.sqrt(np.clip(p1 * (1 - p1), 1e-4, None) / N)
    s = np.sqrt(np.clip(coh * p1, 1e-6, None))
    se_s = 0.5 * s * np.sqrt((se_coh / np.maximum(coh, 0.3)) ** 2 + (se_p1 / np.maximum(p1, 0.3)) ** 2)
    c = [cal.get(int(q), {}) for q in layout]
    t1 = np.array([(d.get("t1_us") or 100.0) for d in c]); t2 = np.array([(d.get("t2_us") or 80.0) for d in c])
    ro = np.array([(d.get("ro") if d.get("ro") is not None else 0.03) for d in c])
    exp_s = np.sqrt(np.exp(-delay_us / t2) * np.exp(-delay_us / t1) * (1 - ro))
    s_rel, se_rel = s / exp_s, se_s / exp_s
    res = {"layout": [int(q) for q in layout], "shots": int(N), "s": s.tolist(), "se_s": se_s.tolist(), "s_rel": s_rel.tolist(),
           "mean_s": float(s.mean()), "se_mean_s": float(np.sqrt((se_s ** 2).sum()) / n), "mean_rel": float(s_rel.mean()),
           "flagged": [int(q) for q, a, e in zip(layout, s_rel, se_rel) if a + Z_SIG * e < FLAG_REL]}
    if "Z0" in cts:
        e0, _ = bit_marginals(cts["Z0"], n); res["mean_e0"] = float(e0.mean())
    return res


from scipy.optimize import minimize

EDGES = [(i, i + 1) for i in range(N_QAOA - 1)]
_X = np.arange(2 ** N_QAOA)
BITS = ((_X[:, None] >> np.arange(N_QAOA)) & 1).astype(np.int8)
CV = np.zeros(2 ** N_QAOA)
for (i, j) in EDGES:
    CV += (BITS[:, i] != BITS[:, j])
C_OPT = float(CV.max()); OPT_SET = np.where(np.isclose(CV, C_OPT))[0]

def _mixer(psi, b, n):
    c, s = np.cos(b), -1j * np.sin(b)
    t = psi.reshape((2,) * n)
    for ax in range(n):
        t0, t1 = np.take(t, 0, axis=ax), np.take(t, 1, axis=ax)
        t = np.stack([c * t0 + s * t1, s * t0 + c * t1], axis=ax)
    return t.reshape(-1)

def qaoa_state(theta, n=N_QAOA, p=P_LAYERS):
    g, b = theta[:p], theta[p:]
    psi = np.full(2 ** n, 1.0 / np.sqrt(2 ** n), dtype=complex)
    for l in range(p):
        psi = psi * np.exp(-1j * g[l] * CV); psi = _mixer(psi, b[l], n)
    return psi

_rng = np.random.default_rng(SEED); _best = None
for _ in range(N_RESTARTS):
    th0 = np.concatenate([_rng.uniform(0, np.pi, P_LAYERS), _rng.uniform(0, np.pi / 2, P_LAYERS)])
    r = minimize(lambda th: -float(np.sum(np.abs(qaoa_state(th)) ** 2 * CV)), th0, method="COBYLA", options={"maxiter": 500})
    if _best is None or r.fun < _best.fun: _best = r
THETA = np.array(_best.x); GAMMAS, BETAS = THETA[:P_LAYERS], THETA[P_LAYERS:]
_P = np.abs(qaoa_state(THETA)) ** 2
IDEAL = {"ar": float(_P @ CV) / C_OPT, "p_opt": float(_P[OPT_SET].sum())}
print("QAOA N=%d p=%d  C_opt=%.1f  AR ideal=%.4f  P(opt) ideal=%.4f" % (N_QAOA, P_LAYERS, C_OPT, IDEAL["ar"], IDEAL["p_opt"]))

def qaoa_circuit():
    qc = QuantumCircuit(N_QAOA, N_QAOA, name="work_qaoa")
    for i in range(N_QAOA): qc.h(i)
    for l in range(P_LAYERS):
        for (i, j) in EDGES: qc.rzz(-float(GAMMAS[l]), i, j)
        for i in range(N_QAOA): qc.rx(2.0 * float(BETAS[l]), i)
    qc.measure(range(N_QAOA), range(N_QAOA))
    return qc

def analyze_work(counts):
    n = N_QAOA; P = np.zeros(2 ** n); tot = 0
    for k, v in counts.items():
        s = str(k).replace(" ", ""); x = int(s, 16) if s.startswith("0x") else int(s, 2)
        P[x] += v; tot += v
    N = max(tot, 1); P = P / N
    cost = float(P @ CV); var = max(float(P @ (CV ** 2)) - cost ** 2, 0.0); se = math.sqrt(var / N)
    return {"shots": int(N), "ar": cost / C_OPT, "se_ar": se / C_OPT, "p_opt": float(P[OPT_SET].sum())}

_job_log, _SIM = [], {}

def get_backend():
    if MODE == "sim":
        # Local 8-qubit backend: avoids expanding circuits to all 156 FakeFez wires
        # and lets the integration check run with modest CPU/RAM resources.
        from qiskit.providers.fake_provider import GenericBackendV2
        from qiskit.transpiler import CouplingMap
        return GenericBackendV2(
            num_qubits=N_QAOA,
            basis_gates=["id", "rz", "sx", "x", "cx", "reset", "measure"],
            coupling_map=CouplingMap.from_line(N_QAOA),
            seed=SEED,
            dt=1e-9,
        )
    from qiskit_ibm_runtime import QiskitRuntimeService
    tok = os.environ.get("IBM_QUANTUM_TOKEN") or os.environ.get("QISKIT_IBM_TOKEN")
    if not tok:
        raise RuntimeError("Falta IBM_QUANTUM_TOKEN o QISKIT_IBM_TOKEN.")
    try:
        svc = QiskitRuntimeService(channel="ibm_cloud", token=tok.strip(),
                                  instance=os.getenv("IBM_QUANTUM_INSTANCE", "open-instance"))
    except Exception:
        svc = QiskitRuntimeService(token=tok.strip())
    return svc.backend(BACKEND_NAME)

def _job_usage(job):
    for fn in (lambda: job.usage(), lambda: job.metrics()["usage"]["quantum_seconds"], lambda: job.metrics()["usage"]["seconds"]):
        v = _try(fn)
        if v is not None:
            try: return float(v), True
            except Exception: pass
    return None, False

USED_S = 0.0   # cumulative QPU account time (reported by IBM; estimated if unavailable)

def execute_pubs(tcs, shots_list, label):
    """Run one job containing PUBs. Enforce the hard cap BEFORE submission."""
    global USED_S
    est = est_job_s(shots_list)
    if GUARD.state == "AUTHORIZED":
        GUARD.transition("RUNNING", reason="first job approved by the guard")
    request_bytes = json.dumps({
        "label": label, "mode": MODE, "backend": BACKEND_NAME,
        "shots": [int(x) for x in shots_list], "circuit_count": len(tcs),
    }, sort_keys=True).encode("utf-8")
    GUARD.send("eqg->simulator" if MODE == "sim" else "eqg->backend",
               "job_request", request_bytes, visibility="private")
    if USED_S + est > HARD_CAP_S:
        raise RuntimeError("Hard cap: %.2f used + %.2f estimated > %.1f s. Not submitting %s" % (USED_S, est, HARD_CAP_S, label))
    t0 = time.time()
    if MODE == "sim":
        from qiskit_aer import AerSimulator
        if "sim" not in _SIM:
            _SIM["sim"] = AerSimulator()
        counts = [_SIM["sim"].run(tc, shots=int(s)).result().get_counts() for tc, s in zip(tcs, shots_list)]
        u, real = est, False; jid = "sim-" + label
    else:
        from qiskit_ibm_runtime import SamplerV2
        job = SamplerV2(mode=backend).run([(tc, None, int(s)) for tc, s in zip(tcs, shots_list)])
        jid = job.job_id(); print("  job %s: %s" % (label, jid))
        print("  (waiting in queue or running; status every 30s; do not cancel solely for QUEUED/RUNNING)", flush=True)
        t_last = time.time()
        while True:
            st = job.status()
            nm = st if isinstance(st, str) else getattr(st, "name", str(st))
            if nm in ("DONE", "CANCELLED", "ERROR"):
                break
            if time.time() - t0 > JOB_TIMEOUT_S:
                _try(lambda: job.cancel())
                raise TimeoutError(label)
            if time.time() - t_last >= 30.0:
                print("  … %s status=%s  waited=%.0fs (queue time ≠ QPU account time)" % (
                    label, nm, time.time() - t0), flush=True)
                t_last = time.time()
            time.sleep(2)
        if nm != "DONE": raise RuntimeError("job %s ended with status %s" % (jid, nm))
        res = job.result(); counts = []
        for i in range(len(tcs)):
            data = res[i].data; c = None
            for key in ("c", "meas"):
                if hasattr(data, key):
                    try: c = getattr(data, key).get_counts(); break
                    except Exception: pass
            if c is None:
                for key in data:
                    try: c = data[key].get_counts(); break
                    except Exception: continue
            counts.append(c or {})
        u, real = _job_usage(job)
        if u is None: u, real = est, False
    result_bytes = json.dumps(counts, sort_keys=True, default=str).encode("utf-8")
    GUARD.send("simulator->eqg" if MODE == "sim" else "backend->eqg",
               "job_result", result_bytes, visibility="private")
    USED_S += float(u)
    info = {"label": label, "job_id": jid, "usage_s": float(u), "usage_real": real, "est_s": est, "used_acum_s": USED_S}
    _job_log.append(info)
    print("  [%s] usage=%.2fs (%s) estimated=%.2fs cumulative=%.2fs" % (label, u, "IBM" if real else "estimated", est, USED_S))
    return counts, info

def snapshot_job(tag, variants):
    delay, unit = probe_delay(backend); tcs, shots, spec = [], [], []
    for name, layout, dd in variants:
        tc = transpile(snap_circuits(N_QAOA, delay, unit, True), backend, initial_layout=list(layout), optimization_level=1, seed_transpiler=SEED)
        if dd: tc, _ = apply_dd(tc, backend, layout)
        tcs += tc; shots += [SHOTS_SNAP_FULL] * len(tc); spec.append((name, layout, dd))
    counts, info = execute_pubs(tcs, shots, "snap-" + tag)
    out, i = {}, 0
    for name, layout, dd in spec:
        cts = {k: counts[i + j] for j, k in enumerate(KINDS_FULL)}; i += len(KINDS_FULL)
        a = analyze_snap(cts, layout, CAL0); a.update({"name": name, "dd": bool(dd)}); out[name] = a
        print("   %-5s s=%.3f+-%.3f s_rel=%.3f e0=%.3f flagged=%s" % (name, a["mean_s"], a["se_mean_s"], a["mean_rel"], a["mean_e0"], a["flagged"]))
    return {"tag": tag, "variants": out, "info": info}


assert CONFIRM_SPEND or MODE == "sim", "Set CONFIRM_SPEND = True to use QPU account time (estimated %.1f s)." % EST_TOTAL
backend = get_backend()
BACKEND = getattr(backend, "name", str(backend))
NQ = int(getattr(backend, "num_qubits", 156)); ALLQ = list(range(NQ))
CAL0, CAL_STAMP0 = read_cal(backend, ALLQ)
EDGE_ERR, EDGES_HW = read_edge_err(backend), coupling_edges(backend)
HEALTH0 = {q: cal_health(CAL0[q]["t1_us"], CAL0[q]["t2_us"], CAL0[q]["ro"]) for q in ALLQ}

reflejos = Reflejos()
_m = reflejos.select(HEALTH0, EDGES_HW, EDGE_ERR, N_QAOA)
LAYOUT_C = list(_m["selected"]); LAYOUT_A = list(range(N_QAOA))
print("Calibration:", CAL_STAMP0)
print("Layout A (naive):", LAYOUT_A, " Layout C/D (calibration):", LAYOUT_C, " connected:", layout_connected(LAYOUT_C, EDGES_HW))

def blend_health(hm0, layout, snap):
    hm = dict(hm0)
    for q, sr in zip(layout, snap["s_rel"]):
        hm[q] = 0.5 * hm0[q] + 0.5 * float(np.clip(sr, 0.0, 1.0))
    return hm

ojos_E = Ojos()
def reaction(layout, snap):
    """Eyes (measurement) -> Reflexes (alternative with memory) -> Judgment. Return a plan."""
    hm = blend_health(HEALTH0, layout, snap)
    lh = ojos_E.observe(layout, hm, rel_mean=snap["mean_rel"], flagged=snap["flagged"])
    reflejos.blacklist |= set(snap["flagged"])
    alt = reflejos.select(hm, EDGES_HW, EDGE_ERR, N_QAOA, exclude=reflejos.blacklist) if snap["flagged"] else None
    plan = planificar(lh, layout, alt, reflejos.score_path(layout, hm, EDGE_ERR))
    plan["regime"] = lh["regime"]
    return plan


print("=" * 60 + "\nPRE\n" + "=" * 60)
snap_pre = snapshot_job("PRE", [("C", LAYOUT_C, False), ("C+DD", LAYOUT_C, True), ("A", LAYOUT_A, False)])
plan0 = reaction(LAYOUT_C, snap_pre["variants"]["C"])
if plan0["tipo"] == "abortar":
    raise RuntimeError("Judgment aborted during PRE: " + plan0["reason"])
LAYOUT_E, DD_E = list(plan0["layout"]), bool(plan0["activate_dd"])
print("E plan inicial: %s | DD=%s | layout=%s | %s" % (plan0["tipo"], DD_E, LAYOUT_E, plan0["reason"]))


works, e_snaps, plans_E = [], [], [plan0]
dd_pulses = {"A": 0, "C": 0, "D": 0, "E": 0}
cz_count = {}

def arm_config(layout_e, dd_e):
    return {"A": (LAYOUT_A, False), "C": (LAYOUT_C, False), "D": (LAYOUT_C, True), "E": (layout_e, dd_e)}

def run_block(bi, order, layout_e, dd_e):
    cfg = arm_config(layout_e, dd_e); tcs_arm = {}
    for arm in "ACDE":
        layout, dd = cfg[arm]
        tc = transpile(qaoa_circuit(), backend, initial_layout=list(layout), optimization_level=1, seed_transpiler=SEED)
        n_dd = 0
        if dd:
            tcl, n_dd = apply_dd([tc], backend, layout); tc = tcl[0]
        dd_pulses[arm] += n_dd * REPS_PER_BLOCK
        ops = tc.count_ops(); cz_count[arm] = int(sum(v for k, v in ops.items() if k in ("cz", "cx", "ecr", "rzz")))
        tcs_arm[arm] = tc
    items = [(arm, rep) for rep in range(REPS_PER_BLOCK) for arm in order]
    tcs = [tcs_arm[a] for a, _ in items]; shots = [SHOTS_WORK] * len(items)
    delay, unit = probe_delay(backend)
    snap_tc = transpile(snap_circuits(N_QAOA, delay, unit, False), backend, initial_layout=list(layout_e), optimization_level=1, seed_transpiler=SEED)
    tcs += list(snap_tc); shots += [SHOTS_SNAP_LIGHT] * len(snap_tc)
    print("[block %d] order=%s  E: layout=%s DD=%s  CZ/circuit=%s" % (bi + 1, "".join(order) * REPS_PER_BLOCK, layout_e, dd_e, cz_count))
    counts, info = execute_pubs(tcs, shots, "bloque%d" % (bi + 1))
    for idx, (arm, rep) in enumerate(items):
        w = analyze_work(counts[idx]); w.update({"arm": arm, "block": bi, "rep": rep, "pos": idx, "layout": list(cfg[arm][0]), "dd": cfg[arm][1]})
        works.append(w)
        print("   %s b%d r%d pos%d AR=%.4f+-%.4f P(opt)=%.3f" % (arm, bi + 1, rep, idx, w["ar"], w["se_ar"], w["p_opt"]))
    k0 = len(items)
    cts = {k: counts[k0 + i] for i, k in enumerate(KINDS_LIGHT)}
    a = analyze_snap(cts, layout_e, CAL0); a["block"] = bi; e_snaps.append(a)
    return a

for bi, order in enumerate(BLOCK_ORDERS):
    snap_e = run_block(bi, order, LAYOUT_E, DD_E)
    if bi < len(BLOCK_ORDERS) - 1:
        pl = reaction(LAYOUT_E, snap_e); plans_E.append(pl)
        if pl["tipo"] == "abortar":
            print("Judgment: ABORT -> stopping"); break
        print("E response: %s | DD=%s | layout=%s | %s" % (pl["tipo"], pl["activate_dd"], pl["layout"], pl["reason"]))
        LAYOUT_E, DD_E = list(pl["layout"]), bool(pl["activate_dd"])


print("=" * 60 + "\nPOST\n" + "=" * 60)
VAR_POST = [("C", LAYOUT_C, False), ("C+DD", LAYOUT_C, True), ("A", LAYOUT_A, False)]
if set(LAYOUT_E) != set(LAYOUT_C): VAR_POST.append(("E", LAYOUT_E, False))
snap_post = snapshot_job("POST", VAR_POST)


def arm_stats(arm):
    ws = [w for w in works if w["arm"] == arm]
    ar = np.array([w["ar"] for w in ws]); se = np.array([w["se_ar"] for w in ws])
    return {"n": len(ws), "ar": float(ar.mean()), "se": float(np.sqrt((se ** 2).sum()) / len(se)),
            "p_opt": float(np.mean([w["p_opt"] for w in ws])), "shots": int(sum(w["shots"] for w in ws)),
            "by_block": {b: float(np.mean([w["ar"] for w in ws if w["block"] == b])) for b in sorted({w["block"] for w in ws})}}

def contrast(X, Y):
    wx = {(w["block"], w["rep"]): w for w in works if w["arm"] == X}
    wy = {(w["block"], w["rep"]): w for w in works if w["arm"] == Y}
    ks = sorted(set(wx) & set(wy))
    d = np.array([wx[k]["ar"] - wy[k]["ar"] for k in ks]); se = np.array([math.hypot(wx[k]["se_ar"], wy[k]["se_ar"]) for k in ks])
    dm, se_p = float(d.mean()), float(np.sqrt((se ** 2).sum()) / len(d)); z = dm / se_p
    sd = float(d.std(ddof=1)) if len(d) > 1 else float("nan")
    t = dm / (sd / math.sqrt(len(d))) if sd and sd == sd and sd > 0 else float("nan")
    npos = int((d > 0).sum())
    v = "SUPPORTED" if (z >= Z_SIG and npos == len(d)) else ("OPPOSITE_SIGN" if (z <= -Z_SIG and npos == 0) else "INCONCLUSIVE")
    return {"contrast": "%s-%s" % (X, Y), "delta": dm, "se": se_p, "z_shots": z, "t_replicas": t, "positivas": "%d/%d" % (npos, len(d)),
            "por_replica": d.tolist(), "veredicto": v}

STATS = {a: arm_stats(a) for a in "ACDE"}
print("=" * 78 + "\nAR by arm (ideal %.4f)\n" % IDEAL["ar"] + "=" * 78)
for a in "ACDE":
    s = STATS[a]
    print("%s  AR=%.4f+-%.4f  P(opt)=%.3f  shots=%d  by block=%s" % (a, s["ar"], s["se"], s["p_opt"], s["shots"],
          {b: round(v, 4) for b, v in s["by_block"].items()}))
CONTRASTS = [contrast(*p) for p in (("C", "A"), ("D", "C"), ("E", "C"), ("E", "D"), ("E", "A"))]
print("\n" + "=" * 78 + "\nContrasts (preregistered: z>=2 and positive sign in every replicate)\n" + "=" * 78)
for c in CONTRASTS:
    print("%-4s delta=%+.4f+-%.4f z=%+.1f t_rep=%+.1f positivas=%s  -> %s" % (
        c["contrast"], c["delta"], c["se"], c["z_shots"], c["t_replicas"], c["positivas"], c["veredicto"]))

print("\nDD pulses inserted (cumulative by arm):", dd_pulses, " | CZ per circuit:", cz_count)
print("E trajectory:", [(p["tipo"], p["activate_dd"], p["layout"]) for p in plans_E])
print("Final E layout: %s (DD=%s)" % (LAYOUT_E, DD_E))
print("PRE e0:", {k: round(v["mean_e0"], 3) for k, v in snap_pre["variants"].items()})
print("POST e0:", {k: round(v["mean_e0"], 3) for k, v in snap_post["variants"].items()})
print("\nQPU account time: used=%.2f s (reported by IBM for %d/%d jobs) | estimated=%.2f s | cap=%.1f s | approx. remaining=%.1f s" % (
    USED_S, sum(j["usage_real"] for j in _job_log), len(_job_log), EST_TOTAL, HARD_CAP_S, QPU_REMAINING_S - USED_S))


GUARD.transition("VERIFYING", reason="execution finished; validate artifacts and encrypt results")
report = {"experiment": "EQG ablation ABBA N=8 p=2", "run_id": RUN_ID, "owner_id": RUN_OWNER,
          "guard": GUARD.snapshot(), "calibration": CAL_STAMP0, "layouts": {"A": LAYOUT_A, "C": LAYOUT_C, "E_end": LAYOUT_E},
          "ideal": IDEAL, "stats": STATS, "contrasts": CONTRASTS, "works": works, "plans_E": plans_E, "dd_pulses": dd_pulses,
          "snap_pre": snap_pre, "snap_post": snap_post, "e_snaps": e_snaps, "jobs": _job_log, "used_s": USED_S, "est_s": EST_TOTAL}
report_bytes = json.dumps(report, indent=2, default=str).encode("utf-8")
report_meta = write_encrypted_artifact(
    OUT / "report.eqg.enc", report_bytes, KEY_INFO, artifact_name="report.json"
)
if decrypt_artifact((OUT / "report.eqg.enc").read_bytes(), KEY_PATH, requester_id=RUN_OWNER) != report_bytes:
    raise RuntimeError("Independent round-trip verification of the encrypted report failed")
GUARD.send("eqg->private-store", "encrypted_report", (OUT / "report.eqg.enc").read_bytes(), visibility="private")
col = {"A": "#c0392b", "C": "#e67e22", "D": "#16a085", "E": "#2980b9"}
fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
for k, a in enumerate("ACDE"):
    ws = [w for w in works if w["arm"] == a]
    ax[0].errorbar([k + 0.08 * (w["block"] * 2 + w["rep"] - 1.5) for w in ws], [w["ar"] for w in ws], yerr=[w["se_ar"] for w in ws],
                   fmt="o", color=col[a], capsize=3)
    ax[0].hlines(STATS[a]["ar"], k - 0.25, k + 0.25, color=col[a])
ax[0].axhline(IDEAL["ar"], color="gray", ls="--"); ax[0].set_xticks(range(4)); ax[0].set_xticklabels(["A naive", "C calibrated", "D calibrated+DD", "E EQG"])
ax[0].set_ylabel("AR"); ax[0].set_title("AR by arm (points = replicates)")
ax[1].barh([c["contrast"] for c in CONTRASTS], [c["delta"] for c in CONTRASTS], xerr=[2 * c["se"] for c in CONTRASTS], color="#7f8c8d")
ax[1].axvline(0, color="k"); ax[1].set_xlabel("delta AR (bar = 2 shot SE)"); ax[1].set_title("Contrasts")
plt.tight_layout(); plot_tmp = OUT / ".ablation.private.tmp.png"
fig.savefig(plot_tmp, dpi=140, bbox_inches="tight")
plot_bytes = plot_tmp.read_bytes()
plot_meta = write_encrypted_artifact(
    OUT / "ablation.eqg.enc", plot_bytes, KEY_INFO, artifact_name="ablation.png"
)
if decrypt_artifact((OUT / "ablation.eqg.enc").read_bytes(), KEY_PATH, requester_id=RUN_OWNER) != plot_bytes:
    raise RuntimeError("Independent round-trip verification of the encrypted figure failed")
plot_tmp.unlink()
GUARD.send("eqg->private-store", "encrypted_plot", (OUT / "ablation.eqg.enc").read_bytes(), visibility="private")
GUARD.transition("PACKAGED", reason="private artifacts encrypted and verified")
print("Saved to", OUT, "| run_id=", RUN_ID, "| private key=", KEY_PATH)


_required = [OUT / "report.eqg.enc", OUT / "ablation.eqg.enc"]
_missing = [str(p) for p in _required if not p.is_file() or p.stat().st_size == 0]
if _missing:
    raise RuntimeError("EQG output is incomplete; missing artifacts: " + ", ".join(_missing))
(OUT / "run_manifest.json").write_text(json.dumps({
    "schema_version": "eqg.private-run-manifest.v1",
    "run_id": RUN_ID,
    "visibility": "private",
    "guard_protocol": "eqg-flow-guard.v1",
    "artifacts": [report_meta, plot_meta],
    "completed": True,
    "integrity_status": "encrypted_and_roundtrip_verified_not_csg_signed"
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("EQG_PIPELINE_COMPLETED")
print("Verified artifacts:", ", ".join(str(p) for p in _required), "and", OUT / "run_manifest.json")
