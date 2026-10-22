"""Offline analysis: readout mitigation, quadrature coherence, weighted fits,
relay statistics (paired tests), and spectator-induced ZZ shifts."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import norm


# ---------------------------------------------------------------- conteos
def counts_from_pub(pub) -> dict:
    data = pub.data
    for key in ("c", "meas"):
        if hasattr(data, key):
            return getattr(data, key).get_counts()
    for key in data:
        try:
            return data[key].get_counts()
        except Exception:
            continue
    return {}


def bit_counts(counts: dict, bit: int):
    """Return (n0, n1) for classical bit `bit` (0 is the rightmost bit)."""
    n0 = n1 = 0
    for k, v in counts.items():
        b = str(k).replace(" ", "")[-1 - bit]
        if b == "0":
            n0 += int(v)
        else:
            n1 += int(v)
    return n0, n1


# ---------------------------------------------------------------- lectura
def readout_errors(cal0: dict, cal1: dict, n_bits: int):
    """Return per-qubit e0[b] = P(1|0), e1[b] = P(0|1) from same-job calibration circuits."""
    e0, e1 = [], []
    for b in range(n_bits):
        a0, a1 = bit_counts(cal0, b)
        c0, c1 = bit_counts(cal1, b)
        e0.append(a1 / max(a0 + a1, 1))
        e1.append(c0 / max(c0 + c1, 1))
    return np.array(e0), np.array(e1)


def mitigated_expectation(counts: dict, bit: int, e0: float, e1: float):
    """Return <Z> corrected by the single-qubit assignment matrix and its standard error."""
    n0, n1 = bit_counts(counts, bit)
    n = max(n0 + n1, 1)
    pm1 = n1 / n
    denom = max(1.0 - e0 - e1, 0.5)
    p1 = float(np.clip((pm1 - e0) / denom, 0.0, 1.0))
    ez = 1.0 - 2.0 * p1
    se = 2.0 * math.sqrt(max(pm1 * (1 - pm1), 1.0 / n) / n) / denom
    return ez, se


# ---------------------------------------------------------------- coherencia
def coherence_from_xy(x, y, sx, sy):
    """Return |rho01| = sqrt(<X>^2 + <Y>^2), shot-noise bias correction, and phase."""
    x, y, sx, sy = map(lambda a: np.asarray(a, float), (x, y, sx, sy))
    mag2 = x ** 2 + y ** 2 - (sx ** 2 + sy ** 2)
    mag = np.sqrt(np.clip(mag2, 0.0, None))
    se = np.sqrt((x * sx) ** 2 + (y * sy) ** 2) / np.maximum(mag, 1e-3)
    se = np.maximum(se, np.sqrt(0.5 * (sx ** 2 + sy ** 2)))
    phase = np.arctan2(y, x)
    return mag, se, phase


def stretched(t, A, T2, beta):
    return A * np.exp(-((np.maximum(t, 0.0) / T2) ** beta))


def fit_envelope(t, y, se, beta_fixed: Optional[float] = None, label: str = "") -> Optional[dict]:
    """Fit weighted A*exp(-(t/T2)^beta) with C = 0 (coherence physically decays to zero).
    Fixing C removes the T2<->C degeneracy that produced error bars larger than estimates in v1-v3.
    Inflate the error by sqrt(chi2_red) when temporal drift is present (chi2_red > 1)."""
    t, y, se = map(lambda a: np.asarray(a, float), (t, y, se))
    ok = np.isfinite(y) & np.isfinite(se)
    t, y, se = t[ok], y[ok], np.maximum(se[ok], 1e-3)
    if len(t) < 3 or np.nanmax(y) < 0.05:
        return None
    # Initial T0: first 1/e crossing
    below = np.where(y < y[0] / math.e)[0]
    T0 = float(t[below[0]]) if len(below) else float(t[-1] * 2)
    try:
        if beta_fixed is None:
            f = stretched
            p0, lo, hi = [min(y[0], 1.0), T0, 1.0], [0.0, 0.5, 0.5], [1.2, 20 * t[-1], 3.0]
        else:
            f = lambda tt, A, T2: stretched(tt, A, T2, beta_fixed)  # noqa: E731
            p0, lo, hi = [min(y[0], 1.0), T0], [0.0, 0.5], [1.2, 20 * t[-1]]
        popt, pcov = curve_fit(f, t, y, p0=p0, sigma=se, absolute_sigma=True, bounds=(lo, hi), maxfev=20000)
    except Exception as e:
        print(f"Fit {label} failed: {e}")
        return None
    perr = np.sqrt(np.diag(pcov))
    dof = max(len(t) - len(popt), 1)
    chi2 = float(np.sum(((f(t, *popt) - y) / se) ** 2) / dof)
    infl = math.sqrt(max(chi2, 1.0))
    out = {"A": float(popt[0]), "T2": float(popt[1]), "T2_err": float(perr[1] * infl),
           "beta": float(popt[2]) if beta_fixed is None else float(beta_fixed),
           "beta_err": float(perr[2] * infl) if beta_fixed is None else 0.0,
           "chi2_red": chi2, "n_points": int(len(t))}
    out["reliable"] = bool(out["T2_err"] < 0.3 * out["T2"] and t[-1] > 0.7 * out["T2"])
    return out


def detuning_from_phase(t, phase, mag, min_mag: float = 0.25, max_gap_us: float = 10.0):
    """Estimate detuning frequency (kHz) by unwrapping phase in the dense portion of the grid.
    Use only consecutive points separated by <= max_gap_us (alias-free when |f| < 1/(2*gap))."""
    t, phase, mag = map(lambda a: np.asarray(a, float), (t, phase, mag))
    sel = [0] if len(t) else []
    for i in range(1, len(t)):
        if mag[i] < min_mag or (t[i] - t[sel[-1]]) > max_gap_us:
            break
        sel.append(i)
    if len(sel) < 3:
        return None
    ts, ph = t[sel], np.unwrap(phase[sel])
    A = np.vstack([ts, np.ones_like(ts)]).T
    coef, res, *_ = np.linalg.lstsq(A, ph, rcond=None)
    slope = coef[0]
    resid = ph - A @ coef
    s2 = float(np.sum(resid ** 2) / max(len(ts) - 2, 1))
    cov = s2 * np.linalg.inv(A.T @ A)
    f_khz = slope / (2 * math.pi) * 1e3
    f_err = math.sqrt(max(cov[0, 0], 0)) / (2 * math.pi) * 1e3
    return {"f_kHz": float(f_khz), "f_err_kHz": float(f_err), "n_points": len(sel),
            "t_max_us": float(ts[-1])}


def ratio_with_err(a, ea, b, eb):
    r = a / b
    return r, abs(r) * math.sqrt((ea / a) ** 2 + (eb / b) ** 2)


# ---------------------------------------------------------------- relevos
def two_proportion_test(k1, n1, k0, n0):
    """Compute the proportion difference (p1 - p0), error, z, and one-sided p-value (p1 > p0)
    y cota superior al 95%."""
    p1, p0 = k1 / max(n1, 1), k0 / max(n0, 1)
    p = (k1 + k0) / max(n1 + n0, 1)
    se_pool = math.sqrt(max(p * (1 - p), 1e-12) * (1 / max(n1, 1) + 1 / max(n0, 1)))
    se = math.sqrt(max(p1 * (1 - p1), 1 / max(n1, 1) ** 2) / max(n1, 1)
                   + max(p0 * (1 - p0), 1 / max(n0, 1) ** 2) / max(n0, 1))
    z = (p1 - p0) / se_pool if se_pool > 0 else 0.0
    return {"delta": p1 - p0, "se": se, "z": z, "p_value": float(1 - norm.cdf(z)),
            "upper95": (p1 - p0) + 1.645 * se, "p_active": p1, "p_ref": p0}


def relay_statistics(records: List[dict], neighbor_bits: Sequence[int], control_bit: int) -> dict:
    """Records are dictionaries with 'spec' (CircuitSpec dictionary) and 'counts'.
    Compare each spectator's P(1) with the target active (main, in |+>) or excited (exc1)
    against the idle-target reference, aggregating across circuits."""
    def pool(kinds, bit):
        k = n = 0
        for r in records:
            if r["spec"]["kind"] in kinds:
                n0, n1 = bit_counts(r["counts"], bit)
                k += n1
                n += n0 + n1
        return k, n

    out = {}
    for label, bit in [*[(f"vecino_bit{b}", b) for b in neighbor_bits], ("control", control_bit)]:
        k_ref, n_ref = pool(("idle",), bit)
        k_act, n_act = pool(("main",), bit)
        k_exc, n_exc = pool(("exc1",), bit)
        out[label] = {
            "activo_vs_idle": two_proportion_test(k_act, n_act, k_ref, n_ref),
            "excitado_vs_idle": two_proportion_test(k_exc, n_exc, k_ref, n_ref),
            "n_ref": n_ref, "n_act": n_act, "n_exc": n_exc,
        }
    return out


def relay_verdict(stats: dict, alpha: float = 0.01, max_transfer: float = 0.005) -> dict:
    """A relay is detected if any neighbor shows a significant excess in P(1) (p < alpha, with
    Bonferroni) Y de magnitud relevante (> max_transfer). Si no, se reporta la cota superior."""
    tests = [(lab, key, s[key]) for lab, s in stats.items() if lab.startswith("vecino")
             for key in ("activo_vs_idle", "excitado_vs_idle")]
    m = max(len(tests), 1)
    flagged = [(lab, key, t) for lab, key, t in tests
               if t["p_value"] < alpha / m and t["delta"] > max_transfer]
    worst_upper = max((t["upper95"] for _, _, t in tests), default=float("nan"))
    return {"relay_detected": bool(flagged), "flagged": [(a, b) for a, b, _ in flagged],
            "worst_upper95": worst_upper, "bonferroni_m": m}


__all__ = [n for n in dir() if not n.startswith("_")]
