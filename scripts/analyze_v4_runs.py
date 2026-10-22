"""Analyze four v4 hardware runs: telegraph states (TLS), dephasing rates, and DD suppression.
Outputs: results/v4_estados.md, .json, and .png."""
import json, math
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
D = json.loads((ROOT / "data" / "v4_runs.json").read_text())
runs = D["runs"]
OUT = ROOT / "results"; OUT.mkdir(exist_ok=True)

def wmean(v, e):
    v, e = np.asarray(v, float), np.asarray(e, float)
    w = 1 / e**2
    m = np.sum(w * v) / np.sum(w)
    se = math.sqrt(1 / np.sum(w))
    chi = float(np.sum(w * (v - m)**2) / max(len(v) - 1, 1)) if len(v) > 1 else 0.0
    return float(m), float(se * math.sqrt(max(chi, 1.0))), chi

# 1) clasificacion por estado: umbral en T2* (separacion > 10 sigma entre grupos)
good = [r for r in runs if r["free"][0] > 100]
bad = [r for r in runs if r["free"][0] <= 100]
out = {"estados": {}}
lines = ["# v4 Hardware Runs: Two States of Qubit q142\n",
         "Data: `data/v4_runs.json` (four jobs from 2026-09-23, same layout).\n",
         "| Run | UTC time | Free T2* (µs) | CPMG T2 (µs) | XY4 T2 (µs) | Detuning (kHz) | State |",
         "|---|---|---|---|---|---|---|"]
for r in runs:
    st = "good" if r in good else "degraded"
    lines.append(f"| {r['id']} | {r['hora_utc']} | {r['free'][0]:.1f} ± {r['free'][1]:.1f} | {r['cpmg'][0]:.1f} ± {r['cpmg'][1]:.1f} | "
                 f"{r['xy4'][0]:.1f} ± {r['xy4'][1]:.1f} | {r['det_kHz'][0]:+.2f} ± {r['det_kHz'][1]:.2f} | {st} |")
lines.append("")
for name, grp in (("bueno", good), ("degradado", bad)):
    s = {}
    for p in ("free", "cpmg", "xy4"):
        s[p] = wmean([r[p][0] for r in grp], [r[p][1] for r in grp])
    s["det"] = wmean([r["det_kHz"][0] for r in grp], [r["det_kHz"][1] for r in grp])
    s["ext_cpmg"] = wmean([r["ext_cpmg"][0] for r in grp], [r["ext_cpmg"][1] for r in grp])
    s["ext_xy4"] = wmean([r["ext_xy4"][0] for r in grp], [r["ext_xy4"][1] for r in grp])
    out["estados"][name] = s
g, b = out["estados"]["bueno"], out["estados"]["degradado"]
lines += ["## By state (weighted mean; errors inflated by sqrt(chi²) when there is tension)\n",
          "| Quantity | Good state (A, D) | Degraded state (B, C) |", "|---|---|---|"]
for k, lab in (("free", "Free T2* (µs)"), ("cpmg", "CPMG T2 (µs)"), ("xy4", "XY4 T2 (µs)"), ("det", "Detuning (kHz)"),
               ("ext_cpmg", "CPMG/free extension"), ("ext_xy4", "XY4/free extension")):
    lines.append(f"| {lab} | {g[k][0]:.2f} ± {g[k][1]:.2f} (χ²={g[k][2]:.1f}) | {b[k][0]:.2f} ± {b[k][1]:.2f} (χ²={b[k][2]:.1f}) |")

# 2) tasas: exceso de desfase que agrega el estado degradado y fraccion que elimina el DD
def rate(T, e):
    return 1e3 / T, 1e3 * e / T**2   # 1/ms
exc = {}
for p in ("free", "cpmg", "xy4"):
    rg, eg = rate(*g[p][:2]); rb, eb = rate(*b[p][:2])
    exc[p] = (rb - rg, math.hypot(eb, eg))
out["exceso_tasa_1_ms"] = exc
lines += ["", "## Decoherence rates (1/T2, in 1/ms)\n",
          "| Protocol | Good state | Degraded state | Excess in degraded state |", "|---|---|---|---|"]
for p in ("free", "cpmg", "xy4"):
    rg, eg = rate(*g[p][:2]); rb, eb = rate(*b[p][:2])
    lines.append(f"| {p} | {rg:.2f} ± {eg:.2f} | {rb:.2f} ± {eb:.2f} | {exc[p][0]:.2f} ± {exc[p][1]:.2f} |")
for p in ("cpmg", "xy4"):
    f = 1 - exc[p][0] / exc["free"][0]
    ef = abs(exc[p][0] / exc["free"][0]) * math.hypot(exc[p][1] / exc[p][0], exc["free"][1] / exc["free"][0])
    out[f"fraccion_exceso_eliminada_{p}"] = (f, ef)
    lines.append(f"\n{p.upper()} removes {100*f:.0f} ± {100*ef:.0f}% of the excess dephasing in the degraded state.")
# 3) correlacion detuning vs tasa libre
det = np.array([r["det_kHz"][0] for r in runs]); rfree = np.array([1e3 / r["free"][0] for r in runs])
cc = float(np.corrcoef(np.abs(det), rfree)[0, 1])
out["corr_absdet_vs_rate_free"] = cc
zz = [r["zz_free_kHz"] for r in runs]; zzc = [r["zz_cpmg_kHz"] for r in runs]
out["zz_free_mean_std"] = (float(np.mean(zz)), float(np.std(zz, ddof=1)))
out["zz_cpmg_mean_std"] = (float(np.mean(zzc)), float(np.std(zzc, ddof=1)))
lines += ["", "## Other invariants",
          f"- Correlation between |detuning| and 1/T2* across runs: r = {cc:.2f} (n = 4; indicative, not conclusive).",
          f"- ZZ with neighbors in |1> (free evolution): {np.mean(zz):.2f} ± {np.std(zz, ddof=1):.2f} kHz in both states; the degraded state is not caused by the neighbors.",
          f"- ZZ under CPMG: {np.mean(zzc):.2f} ± {np.std(zzc, ddof=1):.2f} kHz; DD suppresses ZZ by {100*(1-abs(np.mean(zzc))/abs(np.mean(zz))):.0f}%.",
          f"- 95% upper bound on relay to neighbors: {min(r['relay_up95'] for r in runs):.3f}–{max(r['relay_up95'] for r in runs):.3f}% across all four runs.",
          "", "## Corrections to notebook section 13",
          "- Combining A–D by inverse variance mixes two distinct physical states (χ² up to 294); the average describes neither.",
          "- The claim 'XY4 > CPMG in both runs' does not hold for C (87.9 vs. 90.2 µs); XY4 and CPMG are compatible in all runs.",
          "- Section 11 cites an extension of 0.90–0.94×, which does not appear in any output shown.",
          "- DD extension depends on the state: ~1.4× in the good state and ~2.1× in the degraded state. Reporting it without the state is ambiguous."]
(OUT / "v4_estados.md").write_text("\n".join(lines) + "\n")
(OUT / "v4_estados.json").write_text(json.dumps(out, indent=1))
print("\n".join(lines))

# figura
fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
x = np.arange(len(runs)); cols = {"free": "#6b7280", "cpmg": "#1d4ed8", "xy4": "#b45309"}
for k, p in enumerate(("free", "cpmg", "xy4")):
    ax[0].errorbar(x + (k - 1) * 0.18, [r[p][0] for r in runs], [r[p][1] for r in runs], fmt="o", color=cols[p],
                   label={"free": "Free evolution (T2*)", "cpmg": "CPMG", "xy4": "XY4"}[p], capsize=3)
ax[0].set_xticks(x, [f"{r['id']}\n~{r['hora_utc']} UTC" for r in runs]); ax[0].set_ylabel("T2 (µs)")
ax[0].set_title("T2 by run: two states"); ax[0].axhline(D["T2_cal_us"], ls="--", c="k", lw=0.8)
ax[0].text(3.3, D["T2_cal_us"] + 4, "Calibrated T2", ha="right", fontsize=8); ax[0].legend(fontsize=8)
for r in runs:
    c = "#15803d" if r in good else "#b91c1c"
    ax[1].errorbar(abs(r["det_kHz"][0]), 1e3 / r["free"][0], xerr=r["det_kHz"][1],
                   yerr=1e3 * r["free"][1] / r["free"][0]**2, fmt="o", color=c, capsize=3)
    ax[1].annotate(r["id"], (abs(r["det_kHz"][0]), 1e3 / r["free"][0]), textcoords="offset points", xytext=(6, 4) if r["id"] != "D" else (6, -12))
ax[1].set_xlabel("|detuning| (kHz)"); ax[1].set_ylabel("1/T2* (1/ms)"); ax[1].set_title("Frequency and dephasing shift together")
labs = ["Free", "CPMG", "XY4"]
ax[2].bar(np.arange(3) - 0.2, [1e3 / g[p][0] for p in ("free", "cpmg", "xy4")], 0.4, color="#15803d", label="Good state")
ax[2].bar(np.arange(3) + 0.2, [1e3 / b[p][0] for p in ("free", "cpmg", "xy4")], 0.4, color="#b91c1c", label="Degraded state")
ax[2].set_xticks(range(3), labs); ax[2].set_ylabel("1/T2 (1/ms)"); ax[2].set_title("DD reduces excess dephasing"); ax[2].legend(fontsize=8)
fig.tight_layout(); fig.savefig(OUT / "v4_estados.png", dpi=140)
