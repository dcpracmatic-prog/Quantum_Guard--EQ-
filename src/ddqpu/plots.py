"""Plot coherence and relay measurements."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from .analysis import stretched
from .circuits import PROTOCOLS

COLORS = {"free": "#c0392b", "cpmg": "#2471a3", "xy4": "#1e8449"}
LABELS = {"free": "Free evolution (Ramsey)", "cpmg": "CPMG", "xy4": "XY4"}


def plot_coherence(res, manifest, path=None):
    lay = manifest["layout"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    ax = axes[0]
    for p in PROTOCOLS:
        s = res["series"][p]
        ax.errorbar(s["t_eff"], s["mag"], yerr=s["smag"], fmt="o", ms=4, color=COLORS[p], label=LABELS[p], capsize=2)
        f = res["fits"][p]
        if f:
            tt = np.linspace(0, max(s["t_eff"]) * 1.05, 300)
            ax.plot(tt, stretched(tt, f["A"], f["T2"], f["beta"]), "-", color=COLORS[p], alpha=0.8,
                    label=f"{LABELS[p]}: T2={f['T2']:.0f}±{f['T2_err']:.0f} µs, β={f['beta']:.2f}")
    ax.set_xlabel("Effective time (µs)"); ax.set_ylabel("|ρ01| = √(⟨X⟩²+⟨Y⟩²)")
    ax.set_title(f"Coherence (quadrature, readout-mitigated) — {manifest['backend']} q{lay['target']}")
    ax.set_ylim(-0.03, 1.05); ax.grid(alpha=0.3); ax.legend(fontsize=7.5)

    ax = axes[1]
    s = res["series"]["free"]
    ax.errorbar(s["t"], s["X"], yerr=s["sX"], fmt="o-", ms=3, color="#c0392b", label="⟨X⟩ free")
    ax.errorbar(s["t"], s["Y"], yerr=s["sY"], fmt="s-", ms=3, color="#7d3c98", label="⟨Y⟩ free")
    ax.plot(s["t"], s["mag"], "k--", lw=1, label="|ρ01| free")
    ax.axhline(0, color="gray", lw=0.8)
    d = res.get("detuning")
    ttl = "Free evolution: X/Y (zero crossing is phase, not signal loss)"
    if d:
        ttl += f"\nδf = {d['f_kHz']:+.1f} ± {d['f_err_kHz']:.1f} kHz"
    ax.set_title(ttl, fontsize=10); ax.set_xlabel("t (µs)"); ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=140)
    return fig


def plot_relay(res, manifest, path=None):
    rs = res["relay"]
    labs = list(rs.keys())
    lay = manifest["layout"]
    names = [f"q{q}" for q in lay["neighbors"]] + [f"q{lay['control']} (control)"]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(labs))
    for k, (key, lab, col) in enumerate([("activo_vs_idle", "target in |+> (DD/free) − idle", "#2471a3"),
                                         ("excitado_vs_idle", "target in |1> − idle", "#c0392b")]):
        d = [rs[l][key]["delta"] * 100 for l in labs]
        e = [rs[l][key]["se"] * 100 for l in labs]
        ax.bar(x + (k - 0.5) * 0.36, d, 0.36, yerr=e, capsize=3, color=col, label=lab)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel("Δ spectator P(1) (%)")
    v = res["relay_verdict"]
    ax.set_title("Relays: excess spectator population (paired test)\n"
                 + ("RELAY DETECTED" if v["relay_detected"] else f"no relay; 95% upper bound = {v['worst_upper95']*100:.3f}%"),
                 fontsize=10)
    ax.grid(alpha=0.3, axis="y"); ax.legend(fontsize=8)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=140)
    return fig
