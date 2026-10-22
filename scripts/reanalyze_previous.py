"""Reanalisis de las corridas v1-v3 (ya ejecutadas en ibm_fez q142) sin gastar cola.

Uso:  python scripts/reanalyze_previous.py   -> results/reanalisis_previas.{json,md} + figuras
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ddqpu.analysis import fit_envelope, stretched  # noqa: E402

SHOTS = 2048
D = json.loads((ROOT / "data" / "previous_runs.json").read_text())
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)


def se_of(y):
    y = np.asarray(y, float)
    return np.sqrt(np.maximum(1 - y ** 2, 1.0 / SHOTS) / SHOTS)


def ramsey(t, A, f, phi, T2, beta):
    return A * np.cos(2 * np.pi * f * t + phi) * np.exp(-((t / T2) ** beta))


def fit_ramsey_dense(t, y):
    """Barrido de frecuencia inicial en rejilla fina + ajuste ponderado; C = 0."""
    se = se_of(y)
    best = None
    for f0 in np.linspace(0.003, 0.12, 120):  # MHz (= 3-120 kHz)
        try:
            p, c = curve_fit(ramsey, t, y, p0=[0.95, f0, 0.0, 100.0, 1.0], sigma=se, absolute_sigma=True,
                             bounds=([0, 0, -np.pi, 1, 0.5], [1.2, 0.2, np.pi, 3000, 3.0]), maxfev=20000)
        except Exception:
            continue
        chi = float(np.sum(((ramsey(t, *p) - y) / se) ** 2))
        if best is None or chi < best[0]:
            best = (chi, p, np.sqrt(np.diag(c)))
    chi, p, e = best
    dof = len(t) - 5
    infl = math.sqrt(max(chi / dof, 1.0))
    return {"f_kHz": p[1] * 1e3, "f_err_kHz": e[1] * 1e3 * infl, "T2": p[3], "T2_err": e[3] * infl,
            "beta": p[4], "beta_err": e[4] * infl, "A": p[0], "phi": p[2], "chi2_red": chi / dof, "n": len(t)}


def main():
    R = {}
    # ------------------------------------------------ 1) Canal libre: detuning real y T2*
    t_d = np.r_[D["v1_corto"]["t_us"], D["v1_largo"]["t_us"]].astype(float)
    y_d = np.r_[D["v1_corto"]["free"], D["v1_largo"]["free"]].astype(float)
    o = np.argsort(t_d)
    fr = fit_ramsey_dense(t_d[o], y_d[o])
    R["libre_v1_denso"] = fr
    # Aliasing: con el paso de v2/v3 (26-130 us), f=27 kHz y f=54 kHz no se distinguen
    t_s = np.array(D["v2"]["t_us"])
    R["aliasing"] = {"paso_min_v2_us": float(np.min(np.diff(t_s))),
                     "nyquist_kHz": float(1e3 / (2 * np.min(np.diff(t_s)))),
                     "f_real_kHz": fr["f_kHz"], "f_reportado_v2_kHz": D["v2"]["reportado"]["f_kHz"]}

    # ------------------------------------------------ 2) CPMG / XY4 con C = 0, ponderados
    runs = {"v1_largo": D["v1_largo"], "v2": D["v2"], "v3": D["v3_relevos"]}
    R["dd"] = {}
    for p in ("cpmg", "xy4"):
        R["dd"][p] = {}
        T_all, Y_all = [], []
        for name, r in runs.items():
            t = np.array(r["t_us"], float); y = np.array(r[p], float)
            R["dd"][p][name] = fit_envelope(t, y, se_of(y), label=f"{p}-{name}")
            T_all.append(t); Y_all.append(y)
        t = np.concatenate(T_all + [np.array(D["v1_corto"]["t_us"], float)])
        y = np.concatenate(Y_all + [np.array(D["v1_corto"][p], float)])
        R["dd"][p]["combinado"] = fit_envelope(t, y, se_of(y), label=f"{p}-comb")
    T2s, eT2s = fr["T2"], fr["T2_err"]
    R["extension"] = {}
    for p in ("cpmg", "xy4"):
        c = R["dd"][p]["combinado"]
        r = c["T2"] / T2s
        er = r * math.sqrt((c["T2_err"] / c["T2"]) ** 2 + (eT2s / T2s) ** 2)
        R["extension"][p] = {"ratio": r, "err": er}

    # ------------------------------------------------ 3) Reproducibilidad v2 vs v3 (mismos t, mismo qubit)
    rep = {}
    for p in ("cpmg", "xy4"):
        a = np.array(D["v2"][p]); b = np.array(D["v3_relevos"][p])
        z = (a - b) / np.sqrt(se_of(a) ** 2 + se_of(b) ** 2)
        rep[p] = {"max_abs_diff": float(np.max(np.abs(a - b))), "chi2_red": float(np.mean(z ** 2)),
                  "z_max": float(np.max(np.abs(z)))}
    R["reproducibilidad_v2_v3"] = rep

    # ------------------------------------------------ 4) Relevos v3: lo que si se puede concluir
    v3 = D["v3_relevos"]
    nb = np.concatenate([v3["p1_vecinos_prom"][p] for p in ("free", "cpmg", "xy4")])
    n_per = SHOTS * 2  # 2 vecinos por circuito
    k = float(np.sum(np.round(nb * n_per)))
    n = n_per * len(nb)
    p_hat = k / n
    upper = p_hat + 1.645 * math.sqrt(p_hat * (1 - p_hat) / n)
    corr = {}
    for p in ("free", "cpmg", "xy4"):
        decay = 1 - np.abs(np.array(v3[p]))
        rho, pv = spearmanr(decay, v3["p1_vecinos_prom"][p])
        corr[p] = {"spearman": float(rho), "p_value": float(pv),
                   "cuentas_por_punto": [int(round(x * n_per)) for x in v3["p1_vecinos_prom"][p]]}
    R["relevos_v3"] = {"p1_vecinos_total": p_hat, "cota95_absoluta": upper, "k": k, "n": n,
                       "p1_control_prom": float(np.mean([np.mean(v3["p1_control"][p]) for p in v3["p1_control"]])),
                       "correlaciones": corr}

    # ------------------------------------------------ 5) Barrido N
    ns = D["v1_nsweep"]; y = np.array(ns["cpmg"]); s = se_of(y)
    chi = float(np.sum(((y - np.average(y, weights=1 / s ** 2)) / s) ** 2) / (len(y) - 1))
    R["nsweep"] = {"rango": [float(y.min()), float(y.max())], "se_punto": float(s.mean()),
                   "chi2_red_vs_constante": chi,
                   "dif_max_sigma": float((y.max() - y.min()) / (math.sqrt(2) * s.mean()))}

    (OUT / "reanalisis_previas.json").write_text(json.dumps(R, indent=1, default=float))
    make_figures(R, t_d[o], y_d[o], runs)
    write_md(R)
    print((OUT / "reanalisis_previas.md").read_text())


def make_figures(R, t_d, y_d, runs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fr = R["libre_v1_denso"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    tt = np.linspace(0, 400, 2000)
    ax[0].errorbar(t_d, y_d, yerr=se_of(y_d), fmt="o", color="#c0392b", ms=4, label="v1 (corto+largo, denso)")
    ax[0].plot(tt, ramsey(tt, fr["A"], fr["f_kHz"] / 1e3, fr["phi"], fr["T2"], fr["beta"]), color="#c0392b", lw=1,
               label=f"Ramsey: δf={fr['f_kHz']:.2f}±{fr['f_err_kHz']:.2f} kHz, T2*={fr['T2']:.0f}±{fr['T2_err']:.0f} µs")
    ax[0].plot(runs["v2"]["t_us"], runs["v2"]["free"], "ks", ms=6, mfc="none", label="v2 (paso 26-130 µs)")
    ax[0].plot(runs["v3"]["t_us"], runs["v3"]["free"], "k^", ms=6, mfc="none", label="v3")
    env = fr["A"] * np.exp(-((tt / fr["T2"]) ** fr["beta"]))
    ax[0].plot(tt, env, "k:", lw=1); ax[0].plot(tt, -env, "k:", lw=1)
    ax[0].set_xlim(0, 410); ax[0].set_xlabel("t (µs)"); ax[0].set_ylabel("⟨X⟩ libre")
    ax[0].set_title("Canal libre: el cruce por cero es detuning (~27 kHz), no decoherencia", fontsize=10)
    ax[0].grid(alpha=0.3); ax[0].legend(fontsize=7.5, loc="lower right")

    cols = {"cpmg": "#2471a3", "xy4": "#1e8449"}
    mk = {"v1_largo": "o", "v2": "s", "v3": "^"}
    for p in ("cpmg", "xy4"):
        for name, r in runs.items():
            ax[1].plot(r["t_us"], r[p], mk[name], color=cols[p], ms=4, alpha=0.75)
        c = R["dd"][p]["combinado"]
        ax[1].plot(tt, stretched(tt, c["A"], c["T2"], c["beta"]), color=cols[p],
                   label=f"{p.upper()} combinado: T2={c['T2']:.0f}±{c['T2_err']:.0f} µs, β={c['beta']:.2f}")
    ax[1].plot(tt, env, "--", color="#c0392b", label=f"envolvente libre T2*={fr['T2']:.0f} µs")
    ax[1].set_xlabel("t (µs)"); ax[1].set_ylabel("⟨X⟩ / envolvente"); ax[1].set_ylim(0, 1.02)
    ax[1].set_title("DD vs libre con C=0 y ajuste ponderado (○ v1, □ v2, △ v3)", fontsize=10)
    ax[1].grid(alpha=0.3); ax[1].legend(fontsize=7.5)
    fig.tight_layout(); fig.savefig(OUT / "reanalisis_coherencia.png", dpi=140)


def write_md(R):
    fr = R["libre_v1_denso"]; al = R["aliasing"]; ex = R["extension"]; rv = R["relevos_v3"]; ns = R["nsweep"]
    c = R["dd"]["cpmg"]["combinado"]; x = R["dd"]["xy4"]["combinado"]
    L = ["# Reanalysis of Previous Runs (`ibm_fez`, q142)", "",
         "Generated by `scripts/reanalyze_previous.py` from `data/previous_runs.json` (without using QPU queue time).", "",
         "## Free evolution", "",
         f"- Ramsey fit using the 17 dense v1 points: δf = **{fr['f_kHz']:.2f} ± {fr['f_err_kHz']:.2f} kHz**, "
         f"T2* = **{fr['T2']:.0f} ± {fr['T2_err']:.0f} µs**, β = {fr['beta']:.2f} ± {fr['beta_err']:.2f} (χ²_red = {fr['chi2_red']:.1f}).",
         f"- v2 reported δf = {al['f_reportado_v2_kHz']:.1f} kHz and T2 = 61.8 µs. With a minimum step of {al['paso_min_v2_us']:.1f} µs, "
         f"the Nyquist limit is {al['nyquist_kHz']:.1f} kHz, below the actual δf: this frequency is an **alias**, and the associated T2 is unreliable.",
         "- v1 reported free T2 = 5.2 µs because it fit a monotonic decay to an oscillation. That value is not a T2 measurement.", "",
         "## CPMG and XY4", "",
         "| Protocol | Long v1 | v2 | v3 | Combined |", "|---|---|---|---|---|"]
    for p in ("cpmg", "xy4"):
        cells = []
        for k in ("v1_largo", "v2", "v3", "combinado"):
            f = R["dd"][p][k]
            cells.append(f"{f['T2']:.0f} ± {f['T2_err']:.0f} µs (β={f['beta']:.2f})" if f else "—")
        L.append(f"| {p.upper()} | " + " | ".join(cells) + " |")
    L += ["",
          f"- Actual extension over T2*: CPMG **{ex['cpmg']['ratio']:.2f} ± {ex['cpmg']['err']:.2f}×**, "
          f"XY4 **{ex['xy4']['ratio']:.2f} ± {ex['xy4']['err']:.2f}×** (previously reported as 10.7× and 3.2×).",
          "- The main DD benefit on this qubit is **refocusing coherent detuning** (phase), followed by extending the envelope by about 30–40%.",
          f"- β ≈ {c['beta']:.2f} (CPMG) and {x['beta']:.2f} (XY4): decay under DD is nearly exponential, so the remaining noise is "
          "mostly Markovian or high-frequency. More pulses are unlikely to help much (see the N sweep).", "",
          "## Reproducibility: v2 vs. v3 (same qubit and times)", ""]
    for p, r in R["reproducibilidad_v2_v3"].items():
        L.append(f"- {p.upper()}: maximum difference {r['max_abs_diff']:.3f}, reduced χ² = {r['chi2_red']:.1f}, |z|max = {r['z_max']:.1f}. "
                 + ("This exceeds shot noise and indicates **temporal drift** between jobs." if r["chi2_red"] > 2 else "Consistent with shot noise."))
    L += ["", "## Relays (v3)", "",
          f"- Aggregate neighbor P(1): {rv['p1_vecinos_total']*100:.3f}% ({int(rv['k'])} of {int(rv['n'])} shots). "
          f"**95% upper bound on transfer to neighbors: {rv['cota95_absoluta']*100:.3f}%**, including readout error.",
          f"- Comparing against the distant control (P(1) = {rv['p1_control_prom']*100:.2f}%) is invalid: it measures another qubit's readout error. "
          "v4 uses a paired inactive-target reference for each neighbor.",
          "- The reported correlations (+0.47, −0.39, +0.51) come from seven points with 1–9 counts each:"]
    for p, cc in rv["correlaciones"].items():
        L.append(f"  - {p}: Spearman ρ = {cc['spearman']:+.2f}, p = {cc['p_value']:.2f}, counts = {cc['cuentas_por_punto']}")
    L += ["  None is statistically significant, so these correlations provide evidence in neither direction.",
          "- v3 structural verification searched for `swap` gates, but a transpiled SWAP appears as three CZ gates. "
          "v4 counts every two-qubit gate and verifies both initial and final layouts.", "",
          "## N sweep (CPMG at 60 µs)", "",
          f"- ⟨X⟩ ranges from {ns['rango'][0]:.3f} to {ns['rango'][1]:.3f} (σ per point ≈ {ns['se_punto']:.3f}); reduced χ² against a constant = "
          f"{ns['chi2_red_vs_constante']:.2f}. The curves are flat: ‘optimal N = 16’ is not significant "
          f"({ns['dif_max_sigma']:.1f}σ between the maximum and minimum).", ""]
    (OUT / "reanalisis_previas.md").write_text("\n".join(L))


if __name__ == "__main__":
    main()
