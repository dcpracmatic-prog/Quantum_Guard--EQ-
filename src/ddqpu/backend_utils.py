"""Seleccion de qubits, layout de espectadores, transpilacion verificada y estimacion de tiempo QPU."""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np

TWO_Q_GATES = {"cz", "ecr", "cx", "swap", "rzz", "iswap", "cy", "cp", "rzx"}


def get_token() -> str:
    try:
        from kaggle_secrets import UserSecretsClient  # type: ignore
        t = UserSecretsClient().get_secret("IBM_QUANTUM_TOKEN")
        if t:
            return t.strip()
    except Exception:
        pass
    t = os.environ.get("QISKIT_IBM_TOKEN") or os.environ.get("IBM_QUANTUM_TOKEN")
    if not t:
        raise RuntimeError("Configure el secreto IBM_QUANTUM_TOKEN (Kaggle) o la variable QISKIT_IBM_TOKEN")
    return t.strip()


def get_service(channel: str = "ibm_cloud", instance: Optional[str] = "open-instance"):
    """Crea el servicio sin escribir el token en disco (save_account no es necesario en cada corrida)."""
    from qiskit_ibm_runtime import QiskitRuntimeService
    kw = {"channel": channel, "token": get_token()}
    if instance:
        kw["instance"] = instance
    return QiskitRuntimeService(**kw)


@dataclass
class QubitInfo:
    q: int
    t1_us: float
    t2_us: float
    sx_err: float
    ro_err: float
    score: float


def _qubit_info(backend, q: int) -> Optional[QubitInfo]:
    tgt = backend.target
    try:
        qp = tgt.qubit_properties[q]
        t1 = (qp.t1 or 0.0) * 1e6
        t2 = (qp.t2 or 0.0) * 1e6
    except Exception:
        return None
    if t2 <= 0 or t1 <= 0:
        return None

    def err(op):
        try:
            e = tgt[op][(q,)].error
            return float(e) if e is not None else None
        except Exception:
            return None

    sx = err("sx") or err("x") or 1e-2
    ro = err("measure") or 5e-2
    # T2 > 2*T1 no es fisico: calibracion sospechosa, se recorta
    t2_eff = min(t2, 2.0 * t1)
    score = t2_eff / (1.0 + 50.0 * sx + 10.0 * ro)
    return QubitInfo(q, t1, t2, sx, ro, score)


def rank_qubits(backend, top: int = 8) -> List[QubitInfo]:
    rows = [r for q in range(backend.num_qubits) if (r := _qubit_info(backend, q))]
    rows.sort(key=lambda r: -r.score)
    return rows[:top] if top else rows


def bfs_distances(backend, source: int) -> Dict[int, int]:
    adj: Dict[int, set] = {q: set() for q in range(backend.num_qubits)}
    for a, b in backend.coupling_map.get_edges():
        adj[a].add(b)
        adj[b].add(a)
    dist = {source: 0}
    frontier = [source]
    while frontier:
        nxt = []
        for u in frontier:
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    nxt.append(v)
        frontier = nxt
    return dist


@dataclass
class Layout:
    target: int
    target_t2_us: float
    target_t1_us: float
    neighbors: List[int]
    control: int
    control_distance: int

    @property
    def physical(self) -> List[int]:
        return [self.target] + list(self.neighbors) + [self.control]

    def to_dict(self):
        d = asdict(self)
        d["physical"] = self.physical
        return d


def choose_layout(backend, force_target: Optional[int] = None, n_neighbors: int = 2,
                  min_control_distance: int = 4) -> Layout:
    ranked = rank_qubits(backend, top=0)
    info = {r.q: r for r in ranked}
    if force_target is not None:
        tq = int(force_target)
    else:
        tq = ranked[0].q
    ti = info.get(tq) or _qubit_info(backend, tq)
    dist = bfs_distances(backend, tq)
    nbs = sorted([q for q, d in dist.items() if d == 1], key=lambda q: -(info[q].score if q in info else 0))
    if not nbs:
        raise RuntimeError(f"q{tq} no tiene vecinos en el mapa de acoplamiento")
    # Se miden TODOS los vecinos directos disponibles hasta n_neighbors (en heavy-hex son 2-3)
    nbs = nbs[:n_neighbors]
    # Control lejano: buena lectura (piso basal fiable) y lejos de objetivo y vecinos
    far = [q for q, d in dist.items() if d >= min_control_distance and q in info]
    if not far:
        far = [q for q, d in dist.items() if d >= 2 and q in info]
    far.sort(key=lambda q: (info[q].ro_err, -info[q].t1_us))
    cq = far[0]
    return Layout(tq, ti.t2_us, ti.t1_us, nbs, cq, dist[cq])


def transpile_locked(circuits, backend, layout: Layout, optimization_level: int = 1):
    """Transpila con layout fijo y SIN enrutado. Devuelve (transpilados, reporte_de_relevos)."""
    from qiskit.transpiler import generate_preset_pass_manager
    pm = generate_preset_pass_manager(optimization_level=optimization_level, backend=backend,
                                      initial_layout=layout.physical)
    tcs = pm.run(list(circuits))
    report = verify_no_relay(tcs, layout)
    return tcs, report


def verify_no_relay(transpiled, layout: Layout) -> dict:
    """Verificacion estructural de relevos.
    - Cuenta compuertas de 2 qubits (un SWAP transpilado aparece como 3 CZ/ECR, no como 'swap').
    - Verifica layout inicial y final de cada qubit logico.
    - Verifica que la medicion del bit 0 ocurre en el qubit fisico objetivo."""
    issues = []
    for i, tc in enumerate(transpiled):
        ops = tc.count_ops()
        n2q = sum(v for k, v in ops.items() if k in TWO_Q_GATES)
        if n2q:
            issues.append(f"circuito {i} ({tc.name}): {n2q} compuertas de 2 qubits")
        lay = tc.layout
        if lay is not None:
            try:
                init = lay.initial_index_layout(filter_ancillas=True)
                fin = lay.final_index_layout(filter_ancillas=True)
                if list(init) != layout.physical:
                    issues.append(f"circuito {i}: layout inicial {list(init)} != {layout.physical}")
                if list(fin) != layout.physical:
                    issues.append(f"circuito {i}: layout final {list(fin)} != {layout.physical}")
            except Exception as e:  # pragma: no cover
                issues.append(f"circuito {i}: no se pudo leer layout ({e})")
        for ins in tc.data:
            if ins.operation.name == "measure":
                pq = tc.find_bit(ins.qubits[0]).index
                cb = tc.find_bit(ins.clbits[0]).index
                if cb == 0 and pq != layout.target:
                    issues.append(f"circuito {i}: bit 0 medido en q{pq} (esperado q{layout.target})")
    return {"ok": not issues, "issues": issues, "n_circuits": len(transpiled)}


def estimate_qpu_seconds(specs, backend, rep_delay_s: Optional[float] = None) -> float:
    """Estimacion aproximada: sum(shots * (t_efectivo + medicion + rep_delay)) + ~2 s de overhead."""
    if rep_delay_s is None:
        rep_delay_s = getattr(backend, "default_rep_delay", None) or 250e-6
    try:
        meas = backend.target["measure"][(0,)].duration or 1.6e-6
    except Exception:
        meas = 1.6e-6
    total = sum(s.shots * (s.t_eff_us * 1e-6 + meas + rep_delay_s) for s in specs)
    return float(total + 2.0)


_ = np
