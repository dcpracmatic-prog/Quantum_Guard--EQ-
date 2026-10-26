# EQG

EQG selects a low-friction connected qubit layout from backend calibration, runs one workload, and returns a score with optional validation.

Install with `pip install .` (or clone this repository and run `pip install -e .`).

```python
from eqg import select_layout, run, score
layout = select_layout(backend, n=4)
result = run(backend, circuit, shots=2048, layout=layout)
print(result["score"])
```

Run the configured example with `run_eqg` after setting IBM credentials in the environment and reviewing `config/eqg.yaml`; hardware use is disabled until explicitly confirmed.

EQG selects connected layouts using available calibration data; it does not guarantee a universal performance improvement or remove backend queues. Selection is heuristic and results depend on backend, workload, and calibration time.

Licensed under Elastic License 2.0; see `LICENSE`.
