"""Deterministic core for the EQG N=4 MORPH + QAOA MaxCut product experiment.

This module is provider-independent: it scores physical paths from observed friction,
computes MaxCut-path approximation ratios from counts, and applies a preregistered
statistical gate. It does not submit jobs or incur QPU cost.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite, sqrt
from typing import Mapping, Sequence


def select_morph_path(
    n_logical: int,
    friction: Sequence[float],
    edges: Sequence[Sequence[int]],
    *,
    max_paths: int = 100_000,
) -> list[int]:
    """Return the connected simple path of length n_logical with lowest mean friction.

    Ties are resolved lexicographically. Unlike the notebook's capped DFS traversal,
    this explores all simple paths up to max_paths and fails closed if capped.
    """
    if n_logical < 1:
        raise ValueError("n_logical must be >= 1")
    if not friction:
        raise ValueError("friction cannot be empty")
    if any(not isfinite(float(x)) or not 0 <= float(x) <= 1 for x in friction):
        raise ValueError("friction values must be finite and in [0, 1]")
    adjacency: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        if len(edge) != 2:
            raise ValueError("each edge must contain exactly two node indices")
        a, b = int(edge[0]), int(edge[1])
        if a == b or min(a, b) < 0 or max(a, b) >= len(friction):
            raise ValueError(f"invalid edge: {edge}")
        adjacency[a].add(b)
        adjacency[b].add(a)
    if n_logical > len(friction):
        raise ValueError("logical path cannot exceed number of physical qubits")

    candidates: list[tuple[float, tuple[int, ...]]] = []
    visited_paths = 0

    def dfs(path: tuple[int, ...]) -> None:
        nonlocal visited_paths
        if len(path) == n_logical:
            visited_paths += 1
            if visited_paths > max_paths:
                raise RuntimeError("path search limit exceeded; refusing partial optimum")
            score = sum(float(friction[q]) for q in path) / n_logical
            candidates.append((score, path))
            return
        for nxt in sorted(adjacency[path[-1]] - set(path)):
            dfs(path + (nxt,))

    for start in range(len(friction)):
        dfs((start,))
    if not candidates:
        raise ValueError("no connected simple path satisfies n_logical")
    candidates.sort(key=lambda item: (item[0], item[1]))
    return list(candidates[0][1])


def path_cut(bitstring: str, n: int) -> int:
    """Count cut edges for a path graph represented by an n-bit measurement."""
    bits = str(bitstring).replace(" ", "")
    if n < 1 or len(bits) != n or any(bit not in "01" for bit in bits):
        raise ValueError("bitstring must contain exactly n binary digits")
    return sum(bits[i] != bits[i + 1] for i in range(n - 1))


def approximation_ratio(counts: Mapping[str, int], n: int) -> tuple[float, float]:
    """Return mean MaxCut approximation ratio and its shot-level standard error."""
    if n < 2:
        raise ValueError("n must be >= 2 for a path MaxCut ratio")
    if not counts or any(int(c) != c or c < 0 for c in counts.values()):
        raise ValueError("counts must be a non-empty mapping of non-negative integers")
    total = sum(int(c) for c in counts.values())
    if total <= 0:
        raise ValueError("total shot count must be positive")
    max_cut = n - 1
    mean_cut = sum(path_cut(k, n) * int(v) for k, v in counts.items()) / total
    second = sum(path_cut(k, n) ** 2 * int(v) for k, v in counts.items()) / total
    variance = max(0.0, second - mean_cut * mean_cut)
    return mean_cut / max_cut, sqrt(variance / total) / max_cut


def evaluate_product(
    ar_eqg: float,
    se_eqg: float,
    ar_ref: float,
    se_ref: float,
    *,
    delta_min: float = 0.02,
    z_min: float = 2.0,
    ci95_low_min: float = 0.006,
) -> dict[str, float | str]:
    """Apply the N=4 product gate to independent-arm AR estimates."""
    values = (ar_eqg, se_eqg, ar_ref, se_ref, delta_min, z_min, ci95_low_min)
    if any(not isfinite(float(v)) for v in values):
        raise ValueError("all inputs must be finite")
    if se_eqg < 0 or se_ref < 0 or delta_min < 0 or z_min < 0:
        raise ValueError("standard errors and thresholds must be non-negative")
    delta = ar_eqg - ar_ref
    se_delta = sqrt(se_eqg**2 + se_ref**2)
    z = delta / se_delta if se_delta > 0 else (float("inf") if delta > 0 else 0.0)
    low = delta - 1.96 * se_delta
    if delta >= delta_min and z >= z_min and low > ci95_low_min:
        verdict = "PRODUCTO_OK"
    elif delta > 0:
        verdict = "SENAL_DEBIL"
    else:
        verdict = "NO_GO"
    return {
        "ar_eqg": float(ar_eqg), "ar_reference": float(ar_ref),
        "delta_ar": delta, "se_delta": se_delta, "z": z,
        "ic95_low": low, "veredicto": verdict,
    }
