"""Construccion de circuitos DD con espectadores (vecinos + control) y tiempos alineados a dt.

Convencion de bits: bit 0 = objetivo, bits 1..k = vecinos, ultimo bit = control lejano.
Todos los qubits del layout se miden en todos los circuitos, asi cada circuito aporta datos
de "relevo" (poblacion en espectadores) sin coste extra de circuitos.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import List, Sequence

import numpy as np
from qiskit import QuantumCircuit

PROTOCOLS = ("free", "cpmg", "xy4")
BASES = ("X", "Y")


@dataclass
class Timing:
    """Restricciones de tiempo del backend (todo en unidades de dt)."""
    dt: float                 # segundos por muestra
    granularity: int = 16     # multiplo obligatorio de duracion de delay
    min_length: int = 64
    x_duration_dt: int = 0    # duracion de un pulso X/Y (para t_efectivo)

    def us_to_dt(self, t_us: float) -> int:
        """Redondea t_us al multiplo de granularidad mas cercano (evita los UserWarning de redondeo
        y garantiza que libre/CPMG/XY4 tengan exactamente el mismo tiempo de espera)."""
        n = int(round(t_us * 1e-6 / self.dt))
        g = max(int(self.granularity), 1)
        return int(round(n / g) * g)

    def dt_to_us(self, n: int) -> float:
        return n * self.dt * 1e6


def timing_from_backend(backend) -> Timing:
    target = backend.target
    dt = float(target.dt or backend.dt)
    gran, minlen = 16, 64
    try:
        tc = target.timing_constraints()
        gran, minlen = int(tc.granularity), int(tc.min_length)
    except Exception:
        pass
    xdur = 0
    try:
        q0 = next(iter(target["x"].keys()))
        d = target["x"][q0].duration
        if d:
            xdur = int(round(d / dt))
    except Exception:
        pass
    return Timing(dt=dt, granularity=max(gran, 1), min_length=max(minlen, 1), x_duration_dt=xdur)


@dataclass
class CircuitSpec:
    """Metadatos de un circuito del lote (se serializan en el manifiesto del job)."""
    kind: str                 # main | cal0 | cal1 | idle | exc1 | zz | nsweep
    protocol: str = "none"    # free | cpmg | xy4 | none
    basis: str = "Z"          # X | Y | Z
    t_us: float = 0.0         # tiempo de espera nominal alineado a dt
    t_eff_us: float = 0.0     # tiempo total incluyendo pulsos DD
    n_pulses: int = 0
    spectator_state: str = "0"  # estado preparado en los vecinos
    shots: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _pulse_sequence(protocol: str, n_cpmg: int, n_xy4_cycles: int) -> List[str]:
    if protocol == "cpmg":
        return ["x"] * n_cpmg
    if protocol == "xy4":
        return ["x", "y", "x", "y"] * max(n_xy4_cycles, 1)
    return []


def _dd_block(qc: QuantumCircuit, q: int, total_dt: int, pulses: Sequence[str], timing: Timing):
    """tau/2 - P - tau - P - ... - P - tau/2, con todos los delays en dt y multiplos de granularidad.
    El residuo de redondeo se absorbe en el ultimo tramo para conservar el tiempo total exacto."""
    if total_dt <= 0:
        return
    if not pulses:
        qc.delay(total_dt, q, unit="dt")
        return
    n = len(pulses)
    g = timing.granularity
    half = int((total_dt / (2 * n)) // g * g)
    full = 2 * half
    used = half + full * (n - 1) + half
    last = half + (total_dt - used)
    if half > 0:
        qc.delay(half, q, unit="dt")
    for i, p in enumerate(pulses):
        getattr(qc, p)(q)
        seg = full if i < n - 1 else last
        if seg > 0:
            qc.delay(seg, q, unit="dt")


def build_coherence_circuit(
    protocol: str,
    t_us: float,
    basis: str,
    n_spectators: int,
    timing: Timing,
    n_cpmg: int = 6,
    n_xy4_cycles: int = 2,
    spectator_state: str = "0",
    n_neighbors: int = 2,
):
    """Objetivo en |+>, espera con/sin DD, lectura en base X o Y. Espectadores inactivos."""
    n = 1 + n_spectators
    t_dt = timing.us_to_dt(t_us)
    pulses = _pulse_sequence(protocol, n_cpmg, n_xy4_cycles) if t_dt > 0 else []
    qc = QuantumCircuit(n, n, name=f"{protocol}_{basis}_{t_dt}dt_s{spectator_state}")
    if spectator_state == "1":
        for k in range(1, 1 + n_neighbors):
            qc.x(k)
    qc.h(0)
    qc.barrier()
    _dd_block(qc, 0, t_dt, pulses, timing)
    qc.barrier()
    if basis == "Y":
        qc.sdg(0)
    qc.h(0)
    qc.measure(range(n), range(n))
    t_eff = timing.dt_to_us(t_dt + len(pulses) * timing.x_duration_dt)
    spec = CircuitSpec(kind="main" if spectator_state == "0" else "zz", protocol=protocol, basis=basis,
                       t_us=timing.dt_to_us(t_dt), t_eff_us=t_eff, n_pulses=len(pulses),
                       spectator_state=spectator_state)
    return qc, spec


def build_readout_cal(n_qubits: int, state: str):
    qc = QuantumCircuit(n_qubits, n_qubits, name=f"cal{state}")
    if state == "1":
        qc.x(range(n_qubits))
    qc.barrier()
    qc.measure(range(n_qubits), range(n_qubits))
    return qc, CircuitSpec(kind=f"cal{state}")


def build_relay_reference(t_us: float, n_spectators: int, timing: Timing, target_state: str):
    """Referencia pareada para relevos.
    target_state='0' -> objetivo inactivo (linea base de cada vecino a igual t).
    target_state='1' -> objetivo excitado |1> (caso mas sensible a transferencia por intercambio)."""
    n = 1 + n_spectators
    t_dt = timing.us_to_dt(t_us)
    qc = QuantumCircuit(n, n, name=f"relay_t{target_state}_{t_dt}dt")
    if target_state == "1":
        qc.x(0)
    qc.barrier()
    if t_dt > 0:
        qc.delay(t_dt, 0, unit="dt")
    qc.barrier()
    qc.measure(range(n), range(n))
    kind = "idle" if target_state == "0" else "exc1"
    return qc, CircuitSpec(kind=kind, t_us=timing.dt_to_us(t_dt), t_eff_us=timing.dt_to_us(t_dt))


def default_time_grid(t2_ref_us: float, fractions: Sequence[float] | None = None, t_max_us: float = 450.0,
                      dense_us: Sequence[float] | None = None):
    """Rejilla en dos tramos:
    - tramo denso absoluto (paso <= 5 us hasta 40 us): resuelve la fase sin aliasing para |detuning| < ~100 kHz
      (en v2/v3 el paso era de 26-130 us y el detuning real de ~27 kHz aparecia como ~54 kHz);
    - tramo escalado a T2 calibrado (0.2x .. 1.6x): resuelve la envolvente y beta."""
    if dense_us is None:
        dense_us = [2, 5, 10, 15, 20, 25, 30, 40]
    if fractions is None:
        fractions = [0.2, 0.3, 0.45, 0.6, 0.8, 1.0, 1.3, 1.6]
    grid = set(float(t) for t in dense_us)
    grid |= set(round(min(f * t2_ref_us, t_max_us), 1) for f in fractions)
    grid = sorted(g for g in grid if g > 0)
    # elimina puntos casi duplicados (< 3 us)
    out = []
    for g in grid:
        if not out or g - out[-1] >= 3.0:
            out.append(g)
    return out


def expected_parity_z(qc: QuantumCircuit) -> int:
    """Utilidad para pruebas: numero de X/Y en el objetivo (debe ser par para volver a |+>)."""
    return sum(1 for ins in qc.data if ins.operation.name in ("x", "y") and qc.find_bit(ins.qubits[0]).index == 0)


__all__ = [
    "PROTOCOLS", "BASES", "Timing", "timing_from_backend", "CircuitSpec",
    "build_coherence_circuit", "build_readout_cal", "build_relay_reference", "default_time_grid",
]
_ = np  # numpy reservado para extensiones
