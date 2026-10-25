"""MORPH path selection and QAOA MaxCut execution shared by CPU and IBM modes."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Sequence


def morph_path(n_logical: int, friction: Sequence[float], edges: Iterable[Sequence[int]], *, maximize: bool = False, max_paths: int = 400) -> list[int]:
    """Return the lowest/highest-mean-friction simple connected path among enumerated paths."""
    if n_logical < 1 or len(friction) < n_logical:
        raise ValueError("n_logical must be positive and friction must cover candidate qubits")
    if max_paths < 1:
        raise ValueError("max_paths must be positive")
    adj: dict[int, list[int]] = defaultdict(list)
    for edge in edges:
        if len(edge) != 2:
            raise ValueError(f"invalid coupling edge: {edge}")
        a, b = map(int, edge)
        if a == b or min(a, b) < 0 or max(a, b) >= len(friction):
            raise ValueError(f"coupling edge outside friction vector: {edge}")
        adj[a].append(b)
        adj[b].append(a)
    found: list[list[int]] = []
    key = (lambda q: -float(friction[q])) if maximize else (lambda q: float(friction[q]))

    def visit(path: list[int]) -> None:
        if len(found) >= max_paths:
            return
        if len(path) == n_logical:
            found.append(path.copy())
            return
        for nxt in sorted(adj[path[-1]], key=key):
            if nxt not in path:
                visit(path + [nxt])
                if len(found) >= max_paths:
                    return

    for start in sorted(range(len(friction)), key=key):
        visit([start])
        if len(found) >= max_paths:
            break
    if not found:
        raise ValueError(f"no connected simple path of {n_logical} qubits exists")
    return min(found, key=lambda p: sum(float(friction[q]) for q in p) / n_logical) if not maximize else max(found, key=lambda p: sum(float(friction[q]) for q in p) / n_logical)


def build_qaoa_path(n: int, p: int, gammas: Sequence[float], betas: Sequence[float]):
    from qiskit import QuantumCircuit
    if n < 2 or p < 1 or len(gammas) != p or len(betas) != p:
        raise ValueError("invalid QAOA path dimensions")
    qc = QuantumCircuit(n, n)
    qc.h(range(n))
    for layer in range(p):
        for i in range(n - 1):
            qc.cx(i, i + 1)
            qc.rz(-2 * float(gammas[layer]), i + 1)
            qc.cx(i, i + 1)
        for q in range(n):
            qc.rx(2 * float(betas[layer]), q)
    qc.measure(range(n), range(n))
    return qc


def bitstring_cut(bitstring: str, n: int) -> int:
    bits = str(bitstring).replace(" ", "")[-n:].zfill(n)
    return sum(bits[i] != bits[i + 1] for i in range(n - 1))


def ar_from_counts(counts: dict[str, int], n: int, shots: int | None = None) -> tuple[float, float]:
    total = sum(counts.values()) if shots is None else int(shots)
    if total <= 0 or not counts:
        raise ValueError("counts must contain at least one positive shot")
    if any(int(c) < 0 for c in counts.values()) or sum(counts.values()) <= 0:
        raise ValueError("counts must be nonnegative with a positive sum")
    cuts = [bitstring_cut(k, n) for k in counts]
    weights = [int(v) for v in counts.values()]
    norm = sum(weights)
    mean = sum(w * c for w, c in zip(weights, cuts)) / norm
    second = sum(w * c * c for w, c in zip(weights, cuts)) / norm
    se = math.sqrt(max(0.0, second - mean * mean) / max(total, 1)) / (n - 1)
    return mean / (n - 1), se


def verdict(delta: float, se_delta: float, z: float, *, delta_min: float, z_min: float, ic95_low_min: float) -> tuple[str, float]:
    lower = delta - 1.96 * se_delta
    if delta >= delta_min and z >= z_min and lower > ic95_low_min:
        return "PRODUCTO_OK", lower
    if delta > 0 and (delta < delta_min or z < z_min):
        return "SENAL_DEBIL", lower
    return "NO_GO", lower
