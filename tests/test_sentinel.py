import math
import sys
from pathlib import Path

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ddqpu.circuits import Timing  # noqa: E402
from ddqpu import sentinel as S  # noqa: E402

TM = Timing(dt=4e-9, granularity=1, min_length=1, x_duration_dt=6)


def _synthetic_counts(specs, qubits, T2s, f_kHz, T1, T2e, e0=0.01, e1=0.02, seed=0):
    """Conteos binomiales de un modelo con T2*, detuning, T2 eco y T1 conocidos por qubit."""
    rng = np.random.default_rng(seed)
    n = len(qubits)
    out = []
    for s in specs:
        p1 = np.zeros(n)
        for b in range(n):
            if s["kind"] == "cal0":
                p = 0.0
            elif s["kind"] == "cal1":
                p = 1.0
            elif s["kind"] == "t1":
                p = math.exp(-s["t_us"] / T1[b])
            else:
                T = T2s[b] if s["kind"] == "ramsey" else T2e[b]
                phi = 2 * math.pi * (f_kHz[b] if s["kind"] == "ramsey" else 0.0) * 1e-3 * s["t_us"]
                c = math.exp(-s["t_us"] / T)
                ev = c * (math.cos(phi) if s["basis"] == "X" else math.sin(phi))
                p = (1 - ev) / 2
            p1[b] = p * (1 - e1) + (1 - p) * e0
        bits = rng.random((s["shots"], n)) < p1
        counts = {}
        for row in bits:
            key = "".join("1" if row[b] else "0" for b in reversed(range(n)))
            counts[key] = counts.get(key, 0) + 1
        out.append(counts)
    return out


def test_probe_structure_and_cost():
    pc = S.ProbeConfig()
    circs, specs = S.build_probe(4, TM, pc)
    kinds = [s.kind for s in specs]
    assert kinds.count("ramsey") == 2 * (len(pc.ramsey_dense_us) + len(pc.ramsey_long_us))
    assert kinds.count("echo") == 2 * len(pc.echo_us) and kinds.count("t1") == len(pc.t1_us)
    assert all(qc.num_qubits == 4 for qc in circs)
    cost = S.probe_cost(specs)
    assert cost["qpu_s"] < 15 and cost["usd"] < 25


def test_probe_recovers_known_parameters():
    pc = S.ProbeConfig(shots=4096, shots_cal=8192)
    _, specs = S.build_probe(2, TM, pc)
    sd = [s.to_dict() for s in specs]
    qs = [142, 88]
    counts = _synthetic_counts(sd, qs, T2s=[155, 40], f_kHz=[-27.0, -21.0], T1=[150, 150], T2e=[210, 88])
    res = S.analyze_probe({"specs": sd, "candidates": qs}, counts)
    assert res[142]["detuning_kHz"] == pytest.approx(-27.0, abs=0.8)
    assert res[88]["detuning_kHz"] == pytest.approx(-21.0, abs=0.8)
    assert res[142]["T2star_us"] == pytest.approx(155, rel=0.15)
    assert res[88]["T2star_us"] == pytest.approx(40, rel=0.15)
    assert res[142]["T1_us"] == pytest.approx(150, rel=0.15)
    assert res[142]["T2echo_us"] == pytest.approx(210, rel=0.2)


def test_evaluate_flags_telegraph_state():
    ref = {"T2star_us": 155.0, "detuning_kHz": -27.05, "n": 2}
    good = {"T2star_us": 150.0, "detuning_kHz": -27.1, "detuning_err_kHz": 0.2, "T2echo_us": 210.0}
    bad = {"T2star_us": 40.0, "detuning_kHz": -21.0, "detuning_err_kHz": 0.4, "T2echo_us": 88.0}
    freq_only = {"T2star_us": 140.0, "detuning_kHz": -24.0, "detuning_err_kHz": 0.3, "T2echo_us": 200.0}
    assert S.evaluate(good, ref)["estado"] == "estable"
    assert S.evaluate(bad, ref)["estado"] == "degradado"
    assert S.evaluate(freq_only, ref)["estado"] == "degradado"   # el salto de frecuencia avisa antes


def test_reference_from_history_and_bitacora(tmp_path):
    b = S.Bitacora(tmp_path / "bitacora.jsonl")
    b.append("ibm_fez", {142: {"q": 142, "T2star_us": 158.6, "detuning_kHz": -27.04}}, {142: {"estado": "estable"}})
    b.append("ibm_fez", {142: {"q": 142, "T2star_us": 45.4, "detuning_kHz": -25.3}}, {142: {"estado": "degradado"}})
    b.append("ibm_fez", {142: {"q": 142, "T2star_us": 153.3, "detuning_kHz": -27.05}}, {142: {"estado": "estable"}})
    ref = S.reference_state(b.history("ibm_fez", 142))
    assert ref["n"] == 2 and ref["T2star_us"] == pytest.approx(155.95)
    assert S.reference_state([], T2_cal_us=265.1)["T2star_us"] == pytest.approx(132.55)


@pytest.mark.parametrize("with_dd", [False, True])
def test_virtual_z_compensation_cancels_detuning(with_dd):
    f_kHz = -27.0
    qc = QuantumCircuit(1)
    qc.h(0)
    segs = [1250, 2500, 1250] if with_dd else [5000]
    for i, d in enumerate(segs):
        qc.delay(d, 0, unit="dt")
        if with_dd and i < len(segs) - 1:
            qc.x(0)
    comp = S.compensate_detuning(qc, {0: f_kHz}, TM.dt)
    # simula: cada delay = rz(2*pi*f*tau) (detuning estatico)
    sim = QuantumCircuit(1)
    for ins in comp.data:
        if ins.operation.name == "delay":
            sim.rz(2 * math.pi * f_kHz * 1e3 * ins.operation.duration * TM.dt, 0)
        else:
            sim.append(ins.operation, [0])
    sv = Statevector(sim)
    x = float(np.real(sv.expectation_value(__import__("qiskit.quantum_info", fromlist=["Pauli"]).Pauli("X"))))
    assert abs(abs(x) - 1) < 1e-9


def test_choose_candidates_separation():
    from qiskit_ibm_runtime.fake_provider import FakeFez
    from ddqpu.backend_utils import bfs_distances
    be = FakeFez()
    c = S.choose_candidates(be, k=4, min_separation=3, must_include=[142])
    assert c[0] == 142 and len(c) == 4
    for i in range(4):
        d = bfs_distances(be, c[i])
        assert all(d[c[j]] >= 3 for j in range(4) if j != i)
