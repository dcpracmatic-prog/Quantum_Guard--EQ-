import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ddqpu.circuits import Timing, build_coherence_circuit, build_relay_reference, default_time_grid  # noqa: E402
from ddqpu import analysis as A  # noqa: E402

TM = Timing(dt=4e-9, granularity=16, min_length=64, x_duration_dt=6)


def _delay_total(qc, q=0):
    return sum(i.operation.duration for i in qc.data
               if i.operation.name == "delay" and qc.find_bit(i.qubits[0]).index == q)


@pytest.mark.parametrize("prot", ["free", "cpmg", "xy4"])
@pytest.mark.parametrize("t", [2.0, 13.3, 79.5, 397.6])
def test_same_wait_time_all_protocols(prot, t):
    qc, spec = build_coherence_circuit(prot, t, "X", 3, TM)
    assert _delay_total(qc) == TM.us_to_dt(t)
    for i in qc.data:
        if i.operation.name == "delay":
            assert i.operation.unit == "dt"


def test_delays_are_granular_except_last():
    qc, _ = build_coherence_circuit("cpmg", 79.5, "X", 3, TM)
    ds = [i.operation.duration for i in qc.data if i.operation.name == "delay"]
    assert all(d % TM.granularity == 0 for d in ds)


def test_even_pulses_return_to_plus():
    for prot, n in (("cpmg", 6), ("xy4", 8)):
        qc, spec = build_coherence_circuit(prot, 50, "X", 3, TM)
        assert spec.n_pulses == n and n % 2 == 0


def test_ideal_simulation_plus_state():
    from qiskit.quantum_info import Statevector
    for prot in ("free", "cpmg", "xy4"):
        qc, _ = build_coherence_circuit(prot, 20, "X", 0, TM)
        qc.remove_final_measurements()
        qc = qc.copy()
        # quitar delays para statevector
        from qiskit import QuantumCircuit
        c2 = QuantumCircuit(1)
        for ins in qc.data:
            if ins.operation.name not in ("delay", "barrier"):
                c2.append(ins.operation, [0])
        p0 = abs(Statevector(c2).data[0]) ** 2
        assert p0 == pytest.approx(1.0, abs=1e-9)


def test_grid_dense_start_no_alias():
    g = default_time_grid(265.1)
    dense = [x for x in g if x <= 40]
    assert max(np.diff(dense)) <= 10
    assert g[-1] >= 1.3 * 265.1 * 0.99


def test_bit_order():
    counts = {"0001": 10, "0010": 5}
    assert A.bit_counts(counts, 0) == (5, 10)
    assert A.bit_counts(counts, 1) == (10, 5)


def test_readout_mitigation_inverts_assignment():
    e0, e1 = 0.02, 0.05
    p1_true = 0.3
    n = 100000
    pm1 = e0 + p1_true * (1 - e0 - e1)
    counts = {"1": int(pm1 * n), "0": n - int(pm1 * n)}
    ez, _ = A.mitigated_expectation(counts, 0, e0, e1)
    assert ez == pytest.approx(1 - 2 * p1_true, abs=1e-3)


def test_fit_recovers_t2():
    rng = np.random.default_rng(0)
    t = np.array(default_time_grid(200.0))
    y = 0.95 * np.exp(-(t / 180.0) ** 1.0)
    se = np.full_like(y, 0.02)
    f = A.fit_envelope(t, y + rng.normal(0, 0.02, len(t)), se)
    assert abs(f["T2"] - 180) < 3 * f["T2_err"] + 5
    assert abs(f["beta"] - 1) < 0.2


def test_quadrature_removes_detuning():
    t = np.linspace(0, 100, 30)
    f = 0.027  # MHz
    env = np.exp(-t / 140)
    x, y = env * np.cos(2 * np.pi * f * t), env * np.sin(2 * np.pi * f * t)
    s = np.full_like(t, 1e-3)
    mag, _, ph = A.coherence_from_xy(x, y, s, s)
    assert np.allclose(mag, env, atol=1e-3)
    d = A.detuning_from_phase(t, ph, mag)
    assert d["f_kHz"] == pytest.approx(27.0, abs=0.5)


def test_relay_test_flags_transfer_and_not_noise():
    no = A.two_proportion_test(3, 2048, 2, 2048)
    assert no["p_value"] > 0.05
    yes = A.two_proportion_test(60, 2048, 2, 2048)
    assert yes["p_value"] < 1e-6 and yes["delta"] > 0.02


def test_relay_reference_circuit():
    qc, spec = build_relay_reference(50, 3, TM, "1")
    assert spec.kind == "exc1" and qc.num_qubits == 4


def test_structural_check_detects_hidden_swap():
    """Un SWAP transpilado se convierte en CZs: la verificacion debe detectarlo."""
    from qiskit_ibm_runtime.fake_provider import FakeFez
    from ddqpu.backend_utils import choose_layout, transpile_locked
    from ddqpu.circuits import timing_from_backend
    b = FakeFez()
    lay = choose_layout(b)
    tm = timing_from_backend(b)
    good, _ = build_coherence_circuit("cpmg", 20, "X", 3, tm)
    _, rep = transpile_locked([good], b, lay)
    assert rep["ok"], rep
    bad, _ = build_coherence_circuit("free", 20, "X", 3, tm)
    bad.data.insert(3, bad.data[0].replace(operation=__import__("qiskit").circuit.library.SwapGate(),
                                          qubits=(bad.qubits[0], bad.qubits[1])))
    _, rep = transpile_locked([bad], b, lay)
    assert not rep["ok"]
