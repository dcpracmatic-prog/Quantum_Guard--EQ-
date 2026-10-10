"""Orquestacion: un unico job con barrido principal + referencias de relevo + ZZ + calibracion de lectura."""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

import numpy as np

from .circuits import (PROTOCOLS, BASES, build_coherence_circuit, build_readout_cal,
                       build_relay_reference, default_time_grid, timing_from_backend)
from .backend_utils import choose_layout, transpile_locked, estimate_qpu_seconds, Layout
from . import analysis as A


@dataclass
class Config:
    backend_name: str = "ibm_fez"
    force_target: Optional[int] = None       # p.ej. 142 para comparar con corridas previas
    n_neighbors: int = 2
    n_cpmg: int = 6
    n_xy4_cycles: int = 2
    shots_main: int = 1024                   # por base; X+Y => 2048 efectivos por punto
    shots_ref: int = 2048                    # referencias de relevo (se agregan entre tiempos)
    shots_cal: int = 4096
    t2_fractions: Optional[List[float]] = None
    t_max_us: float = 450.0
    relay_fractions: List[float] = field(default_factory=lambda: [0.1, 0.5, 1.0])
    zz_fractions: List[float] = field(default_factory=lambda: [0.05, 0.10, 0.20])
    enable_zz: bool = True
    shuffle_seed: Optional[int] = 1234       # orden aleatorio => la deriva no se correlaciona con t
    optimization_level: int = 1
    max_qpu_seconds: float = 240.0           # freno de seguridad para el plan Open (10 min/mes)


def build_batch(cfg: Config, backend, layout: Optional[Layout] = None):
    layout = layout or choose_layout(backend, cfg.force_target, cfg.n_neighbors)
    timing = timing_from_backend(backend)
    n_spec = len(layout.physical) - 1
    grid = default_time_grid(layout.target_t2_us, cfg.t2_fractions, cfg.t_max_us)
    circs, specs = [], []

    def add(qc, spec, shots):
        spec.shots = shots
        circs.append(qc)
        specs.append(spec)

    n = len(layout.physical)
    for st in ("0", "1"):
        add(*build_readout_cal(n, st), cfg.shots_cal)
    for prot in PROTOCOLS:
        for t in grid:
            for b in BASES:
                add(*build_coherence_circuit(prot, t, b, n_spec, timing, cfg.n_cpmg, cfg.n_xy4_cycles,
                                             "0", cfg.n_neighbors), cfg.shots_main)
    for f in cfg.relay_fractions:
        t = f * layout.target_t2_us
        add(*build_relay_reference(t, n_spec, timing, "0"), cfg.shots_ref)
        add(*build_relay_reference(t, n_spec, timing, "1"), cfg.shots_ref)
    if cfg.enable_zz:
        # se usan puntos EXACTOS de la rejilla principal para comparar fase a igual t
        zz_t = sorted(set(min(grid, key=lambda g: abs(g - f * layout.target_t2_us)) for f in cfg.zz_fractions))
        for prot in ("free", "cpmg"):
            for t in zz_t:
                for b in BASES:
                    add(*build_coherence_circuit(prot, t, b, n_spec, timing, cfg.n_cpmg, cfg.n_xy4_cycles,
                                                 "1", cfg.n_neighbors), cfg.shots_main)
    order = list(range(len(circs)))
    if cfg.shuffle_seed is not None:
        random.Random(cfg.shuffle_seed).shuffle(order)
    circs = [circs[i] for i in order]
    specs = [specs[i] for i in order]
    return circs, specs, layout, timing, grid


def run_batch(cfg: Config, backend, circs, specs, layout, out_dir: Path, mode: str = "hardware"):
    """Transpila con layout bloqueado, verifica relevos estructurales y envia UN job.
    mode: 'hardware' | 'sim' (backend falso local)."""
    from qiskit_ibm_runtime import SamplerV2
    tcs, report = transpile_locked(circs, backend, layout, cfg.optimization_level)
    if not report["ok"]:
        raise RuntimeError("Verificacion estructural fallo (posible relevo):\n" + "\n".join(report["issues"][:10]))
    est = estimate_qpu_seconds(specs, backend)
    print(f"Circuitos: {len(tcs)} | shots totales: {sum(s.shots for s in specs)} | QPU estimado ~{est:.0f} s")
    if mode == "hardware" and est > cfg.max_qpu_seconds:
        raise RuntimeError(f"Estimacion {est:.0f}s > max_qpu_seconds={cfg.max_qpu_seconds}. Reduce shots o puntos.")
    sampler = SamplerV2(mode=backend)
    pubs = [(tc, None, s.shots) for tc, s in zip(tcs, specs)]
    job = sampler.run(pubs)
    job_id = job.job_id()
    print("Job ID:", job_id)
    manifest = {"job_id": job_id, "backend": backend.name, "layout": layout.to_dict(),
                "config": asdict(cfg), "specs": [s.to_dict() for s in specs],
                "structural_check": report, "qpu_estimate_s": est, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    t0 = time.time()
    result = job.result()
    print(f"Job completado en {time.time() - t0:.0f} s (incluye cola)")
    counts = [A.counts_from_pub(result[i]) for i in range(len(specs))]
    save_counts(out_dir, manifest, counts)
    return manifest, counts


def save_counts(out_dir: Path, manifest: dict, counts: list):
    raw = dict(manifest)
    raw["counts"] = counts
    (out_dir / "raw_counts.json").write_text(json.dumps(raw))


def reload_from_job(service, job_id: str, manifest_path: Path):
    """Reanalisis sin volver a hacer cola: recupera el resultado de un job ya ejecutado."""
    manifest = json.loads(Path(manifest_path).read_text())
    res = service.job(job_id).result()
    counts = [A.counts_from_pub(res[i]) for i in range(len(manifest["specs"]))]
    return manifest, counts


# ------------------------------------------------------------------ analisis completo
def analyze(manifest: dict, counts: list) -> dict:
    specs = manifest["specs"]
    lay = manifest["layout"]
    n_bits = len(lay["physical"])
    recs = [{"spec": s, "counts": c} for s, c in zip(specs, counts)]
    cal0 = next(r["counts"] for r in recs if r["spec"]["kind"] == "cal0")
    cal1 = next(r["counts"] for r in recs if r["spec"]["kind"] == "cal1")
    e0, e1 = A.readout_errors(cal0, cal1, n_bits)

    def series(kind, prot):
        pts = {}
        for r in recs:
            s = r["spec"]
            if s["kind"] == kind and s["protocol"] == prot:
                ez, se = A.mitigated_expectation(r["counts"], 0, e0[0], e1[0])
                pts.setdefault(round(s["t_us"], 4), {"t_eff": s["t_eff_us"]})[s["basis"]] = (ez, se)
        ts = sorted(k for k, v in pts.items() if "X" in v and "Y" in v)
        t = np.array(ts)
        teff = np.array([pts[k]["t_eff"] for k in ts])
        x = np.array([pts[k]["X"][0] for k in ts]); sx = np.array([pts[k]["X"][1] for k in ts])
        y = np.array([pts[k]["Y"][0] for k in ts]); sy = np.array([pts[k]["Y"][1] for k in ts])
        mag, smag, ph = A.coherence_from_xy(x, y, sx, sy)
        return {"t": t, "t_eff": teff, "X": x, "sX": sx, "Y": y, "sY": sy, "mag": mag, "smag": smag, "phase": ph}

    out = {"readout": {"e0": e0.tolist(), "e1": e1.tolist()}, "series": {}, "fits": {}, "fits_exp": {}}
    for p in PROTOCOLS:
        s = series("main", p)
        out["series"][p] = s
        out["fits"][p] = A.fit_envelope(s["t_eff"], s["mag"], s["smag"], label=p)
        out["fits_exp"][p] = A.fit_envelope(s["t_eff"], s["mag"], s["smag"], beta_fixed=1.0, label=p + "_exp")
    out["detuning"] = A.detuning_from_phase(out["series"]["free"]["t"], out["series"]["free"]["phase"],
                                           out["series"]["free"]["mag"])
    # Extension de coherencia (con barras de error)
    ext = {}
    ff = out["fits"]["free"]
    for p in ("cpmg", "xy4"):
        fp = out["fits"][p]
        if ff and fp:
            r, er = A.ratio_with_err(fp["T2"], fp["T2_err"], ff["T2"], ff["T2_err"])
            ext[p] = {"ratio": r, "err": er, "significant": bool(r - 1 > 2 * er)}
    out["extension"] = ext
    # Relevos
    nb_bits = list(range(1, 1 + len(lay["neighbors"])))
    rs = A.relay_statistics(recs, nb_bits, n_bits - 1)
    out["relay"] = rs
    out["relay_verdict"] = A.relay_verdict(rs)
    # ZZ: comparar fase y coherencia con vecinos en |1> vs |0> a los mismos t
    zz = {}
    if any(r["spec"]["kind"] == "zz" for r in recs):
        for p in ("free", "cpmg"):
            s1 = series("zz", p)
            s0 = out["series"][p]
            rows = []
            for i, t in enumerate(s1["t"]):
                j = np.argmin(np.abs(s0["t"] - t))
                if abs(s0["t"][j] - t) > 1e-3:
                    continue
                dphi = float(np.angle(np.exp(1j * (s1["phase"][i] - s0["phase"][j]))))
                rows.append({"t": float(t), "dphi": dphi, "mag1": float(s1["mag"][i]), "mag0": float(s0["mag"][j])})
            if rows:
                tt = np.array([r["t"] for r in rows]); dp = np.array([r["dphi"] for r in rows])
                slope = float(np.sum(tt * dp) / np.sum(tt * tt))
                zz[p] = {"rows": rows, "zz_kHz": slope / (2 * np.pi) * 1e3}
    out["zz"] = zz
    return out


def to_jsonable(o):
    if isinstance(o, dict):
        return {k: to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    return o


def summarize(res: dict, manifest: dict) -> str:
    L = []
    lay = manifest["layout"]
    L.append(f"Backend={manifest['backend']}  objetivo=q{lay['target']} (T2 cal={lay['target_t2_us']:.1f} us, "
             f"T1 cal={lay['target_t1_us']:.1f} us)  vecinos={lay['neighbors']}  control=q{lay['control']}  "
             f"job={manifest['job_id']}")
    L.append(f"Error de lectura objetivo: P(1|0)={res['readout']['e0'][0]:.4f}  P(0|1)={res['readout']['e1'][0]:.4f}")
    for p in PROTOCOLS:
        f = res["fits"][p]
        if f:
            tag = "" if f["reliable"] else "  [baja confianza]"
            L.append(f"T2[{p:>4}] = {f['T2']:7.1f} +/- {f['T2_err']:5.1f} us  beta={f['beta']:.2f}+/-{f['beta_err']:.2f}"
                     f"  chi2_red={f['chi2_red']:.1f}{tag}")
        else:
            L.append(f"T2[{p:>4}] = sin ajuste")
    d = res.get("detuning")
    if d:
        L.append(f"Detuning (fase desenvuelta, {d['n_points']} pts hasta {d['t_max_us']:.0f} us): "
                 f"{d['f_kHz']:+.2f} +/- {d['f_err_kHz']:.2f} kHz")
    for p, e in res["extension"].items():
        L.append(f"Extension {p}/libre = {e['ratio']:.2f} +/- {e['err']:.2f}  -> "
                 f"{'significativa (>2 sigma)' if e['significant'] else 'NO significativa'}")
    rv = res["relay_verdict"]
    L.append("Relevos: " + ("DETECTADO en " + str(rv["flagged"]) if rv["relay_detected"] else
                             f"no detectado; cota superior 95% de transferencia a vecinos = {rv['worst_upper95']*100:.3f} %"))
    for p, z in res.get("zz", {}).items():
        L.append(f"ZZ efectivo (vecinos en |1>) con {p}: {z['zz_kHz']:+.2f} kHz")
    return "\n".join(L)
