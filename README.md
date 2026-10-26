# Edge Quantum Guard (EQG)

EQG selects a connected physical-qubit layout using backend calibration, executes a quantum circuit and returns its measurement results. The included example evaluates QAOA MaxCut on a path graph.

## Installation

```bash
pip install .
```

## Python API

```python
from eqg import select_layout, run
layout = select_layout(backend, n=4)
result = run(backend, circuit, shots=2048, layout=layout)
print(result["job_id"], result["score"])
```

`run()` reports a MaxCut-path approximation ratio; use `result["counts"]` and your own objective for other workloads.

## CLI

Set `IBM_QUANTUM_TOKEN` and `IBM_QUANTUM_INSTANCE` in your environment. Copy `config/eqg.yaml`, select a backend and review the parameters. Hardware submission requires `execution.confirm_spend: true`.

```bash
run_eqg --config config/eqg.yaml
```

Without `--config`, the installed command reads its bundled configuration, which disables hardware spending by default.

## Scope

Layout selection is heuristic (up to 400 connected paths). Performance depends on workload and calibration; EQG does not guarantee improvement over alternative layouts. The CLI's optional reference comparison requires an explicitly provided reference layout. QPU execution uses the customer's IBM credentials.

## License

Elastic License 2.0. See `LICENSE`.
