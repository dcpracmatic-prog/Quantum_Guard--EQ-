"""Public EQG API: select a layout, execute one workload, and score counts."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Mapping, Sequence


def _backend_data(backend_props):
    """Accept a backend, or {friction: [...], edges: [...]} calibration snapshot."""
    if isinstance(backend_props, Mapping):
        friction = list(map(float, backend_props["friction"]))
        edges = backend_props["edges"]
        return friction, edges
    backend = backend_props
    calibration = backend.properties()
    friction = []
    for q in range(backend.num_qubits):
        try:
            readout = float(calibration.readout_error(q))
        except Exception:
            readout = 0.03
        try:
            x_error = float(calibration.gate_error("x", [q]))
        except Exception:
            x_error = 0.001
        friction.append(min(1.0, 6.0 * readout + 60.0 * x_error))
    return friction, list(backend.coupling_map.get_edges())


def select_layout(backend_props, n: int) -> list[int]:
    """Choose the connected n-qubit path with lowest mean calibration friction.

    `backend_props` is a backend object or a mapping containing `friction` and `edges`.
    The selected layout is heuristic and searches up to 400 paths.
    """
    friction, edges = _backend_data(backend_props)
    if n < 1 or n > len(friction):
        raise ValueError("n must be between 1 and the number of calibrated qubits")
    adjacency: dict[int, list[int]] = defaultdict(list)
    for edge in edges:
        a, b = map(int, edge)
        if a == b or min(a, b) < 0 or max(a, b) >= len(friction):
            raise ValueError(f"invalid coupling edge: {edge}")
        adjacency[a].append(b)
        adjacency[b].append(a)
    paths: list[list[int]] = []
    def visit(path: list[int]) -> None:
        if len(paths) >= 400:
            return
        if len(path) == n:
            paths.append(path.copy())
            return
        for q in sorted(adjacency[path[-1]], key=lambda x: friction[x]):
            if q not in path:
                visit(path + [q])
    for start in sorted(range(len(friction)), key=lambda x: friction[x]):
        visit([start])
        if len(paths) >= 400:
            break
    if not paths:
        raise ValueError(f"no connected path of {n} qubits is available")
    return min(paths, key=lambda p: sum(friction[q] for q in p) / n)


def score(counts: Mapping[str, int], n: int) -> dict[str, float]:
    """Score measured bitstrings as approximation ratio for MaxCut on a path."""
    if n < 2 or not counts or sum(counts.values()) <= 0:
        raise ValueError("score requires nonempty counts and n >= 2")
    cuts, weights = [], []
    for key, value in counts.items():
        bits = str(key).replace(" ", "")[-n:].zfill(n)
        cuts.append(sum(bits[i] != bits[i + 1] for i in range(n - 1)))
        weights.append(int(value))
    total = sum(weights)
    if any(w < 0 for w in weights) or total <= 0:
        raise ValueError("counts must be nonnegative with a positive total")
    mean = sum(w * c for w, c in zip(weights, cuts)) / total
    second = sum(w * c * c for w, c in zip(weights, cuts)) / total
    return {"approximation_ratio": mean / (n - 1),
            "standard_error": math.sqrt(max(0.0, second - mean * mean) / total) / (n - 1)}


def run(backend, circuit, shots: int, *, layout: Sequence[int] | None = None, tags: Sequence[str] | None = None) -> dict:
    """Transpile and execute one circuit on one backend; return job ID and score."""
    if shots < 1:
        raise ValueError("shots must be positive")
    from qiskit import transpile
    from qiskit_ibm_runtime import SamplerV2
    isa = transpile(circuit, backend, initial_layout=layout, optimization_level=1)
    sampler = SamplerV2(mode=backend)
    if tags:
        sampler.options.environment.job_tags = list(tags)
    job = sampler.run([(isa, None, shots)])
    result = job.result()
    counts = {k: int(v) for k, v in result[0].data.c.get_counts().items()}
    n = circuit.num_qubits
    return {"job_id": job.job_id(), "backend": backend.name, "layout": list(layout) if layout is not None else None,
            "shots": shots, "counts": counts, "score": score(counts, n), "usage_seconds": job.usage()}


def validate(backend, circuit, shots: int, candidate_layout: Sequence[int], reference_layout: Sequence[int], *, thresholds: Mapping[str, float] | None = None) -> dict:
    """Compare selected and reference layouts, returning scores and a threshold verdict."""
    if list(candidate_layout) == list(reference_layout):
        raise ValueError("candidate and reference layouts must differ")
    from qiskit import transpile
    from qiskit_ibm_runtime import SamplerV2
    isa_a = transpile(circuit, backend, initial_layout=list(candidate_layout), optimization_level=1)
    isa_b = transpile(circuit, backend, initial_layout=list(reference_layout), optimization_level=1)
    sampler = SamplerV2(mode=backend)
    job = sampler.run([(isa_a, None, shots), (isa_b, None, shots)])
    result = job.result()
    a = score({k: int(v) for k, v in result[0].data.c.get_counts().items()}, circuit.num_qubits)
    b = score({k: int(v) for k, v in result[1].data.c.get_counts().items()}, circuit.num_qubits)
    delta = a["approximation_ratio"] - b["approximation_ratio"]
    se = math.hypot(a["standard_error"], b["standard_error"])
    z = delta / se if se else float("inf")
    t = {"delta_min": 0.02, "z_min": 2.0, "lower_bound_min": 0.006}
    if thresholds:
        t.update(thresholds)
    lower = delta - 1.96 * se
    verdict = "PASS" if delta >= t["delta_min"] and z >= t["z_min"] and lower > t["lower_bound_min"] else "NO_PASS"
    return {"job_id": job.job_id(), "backend": backend.name, "candidate": a, "reference": b,
            "delta": delta, "z": z, "lower_bound": lower, "verdict": verdict,
            "layouts": {"candidate": list(candidate_layout), "reference": list(reference_layout)}}
