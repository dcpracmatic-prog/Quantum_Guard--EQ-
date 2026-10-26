"""The single EQG command-line entry point."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from importlib.resources import files
import numpy as np
import yaml
from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService
from . import run, select_layout, validate


def _workload(n: int, depth: int, seed: int):
    rng = np.random.default_rng(seed)
    gammas, betas = rng.uniform(.25, .85, size=depth), rng.uniform(.15, .45, size=depth)
    qc = QuantumCircuit(n, n)
    qc.h(range(n))
    for layer in range(depth):
        for q in range(n - 1):
            qc.cx(q, q + 1)
            qc.rz(-2 * float(gammas[layer]), q + 1)
            qc.cx(q, q + 1)
        for q in range(n):
            qc.rx(2 * float(betas[layer]), q)
    qc.measure(range(n), range(n))
    return qc


def main(argv=None):
    parser = argparse.ArgumentParser(description="Select a calibrated layout and run one EQG workload")
    bundled_config = files("eqg").joinpath("default.yaml")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    config_path = Path(args.config) if args.config else Path(str(bundled_config))
    cfg = yaml.safe_load(config_path.read_text())
    ex = cfg["execution"]
    if not ex.get("confirm_spend", False):
        raise SystemExit("Hardware execution is disabled. Review usage and set execution.confirm_spend=true.")
    token_name = ex.get("token_env", "IBM_QUANTUM_TOKEN")
    instance_name = ex.get("instance_env", "IBM_QUANTUM_INSTANCE")
    token, instance = os.getenv(token_name), os.getenv(instance_name)
    if not token:
        raise SystemExit(f"Missing {token_name} environment variable")
    if not instance:
        raise SystemExit(f"Missing {instance_name} environment variable")
    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token, instance=instance)
    backend = service.backend(ex["backend"])
    n, shots = int(ex["qubits"]), int(ex["shots"])
    if n < 2:
        raise SystemExit("EQG workload needs at least 2 qubits for scoring; no job was submitted.")
    if shots < 1:
        raise SystemExit("shots must be positive; no job was submitted.")
    layout = select_layout(backend, n)
    circuit = _workload(n, int(ex["depth"]), int(ex["seed"]))
    validation = cfg.get("validation", {})
    if validation.get("enabled", False):
        reference = validation.get("reference_layout")
        if not reference:
            raise SystemExit("Set validation.reference_layout when validation.enabled is true")
        result = validate(backend, circuit, shots, layout, reference, thresholds=validation)
    else:
        result = run(backend, circuit, shots, layout=layout, tags=["eqg"])
    summary = {key: value for key, value in result.items() if key not in {"counts"}}
    print(json.dumps(summary, indent=2, default=str))
    return 0
