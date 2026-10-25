# Edge Quantum Guard (EQG)

**EQG MVP — hardware-aware QAOA layout selection with MORPH.**

The current MVP loop is:

`Backend properties → connected low-friction MORPH path → QAOA MaxCut → approximation-ratio score → contract verdict`

The MVP's demonstrated actuator in the two runs below is **physical layout selection only**. These runs did **not** apply dynamical decoupling (DD), the E1/E1rev policy, or the four-arm adaptive stack. Historical DD, Sentinel, and full-stack experiments remain in the repository as research evidence; they are not the implementation or evidence source for these two MVP results.

## Hardware results in the MVP evidence set

Preserved source reports, summaries, and the submitted notebook snapshots are grouped under [`evidence/product_mvp/`](evidence/product_mvp/); they are unchanged from the original artifacts.

Both records are single-job, paired comparisons: the same QAOA circuit parameters and shot count were executed with a MORPH-selected path and a connected reference path. The reference is selected by the notebook's **maximum-friction connected-path heuristic**; it is not a neutral random or ordinary production baseline.

| Backend | Job | MORPH AR | Reference AR | ΔAR (MORPH − reference) | z | 95% lower bound |
|---|---|---:|---:|---:|---:|---:|
| `ibm_kingston` | `dbe6il7gdj9s73fl9o40` | 0.69808 | 0.60254 | +0.09554 | 11.16 | +0.07875 |
| `ibm_fez` | `dbe6r97sstms73fbj220` | 0.69271 | 0.63867 | +0.05404 | 6.25 | +0.03709 |

The recorded configuration is 4 logical qubits, QAOA depth `p=1`, and 2,048 shots per layout. Both reports meet the recorded gate: ΔAR ≥ 0.02, z ≥ 2, and lower bound > 0.006. The scores and job identifiers below are preserved from the submitted run artifacts; see the [MVP evidence note](docs/eqg-product-mvp.md) for methods, exact source files, and interpretation limits.

- Kingston: [report](evidence/product_mvp/report-4.json) · [summary](evidence/product_mvp/summary-2.txt) · [reviewed notebook](notebooks/eqg_product/ibm_kingston.ipynb) · [original submitted notebook snapshot](evidence/product_mvp/kaggle.ipynb-20.txt)
- Fez: [report](evidence/product_mvp/report-5.json) · [summary](evidence/product_mvp/summary-3.txt) · [reviewed notebook](notebooks/eqg_product/ibm_fez.ipynb) · [original submitted notebook snapshot](evidence/product_mvp/kaggle.ipynb-21.txt)
- [Validate that the report/summary pairs agree](scripts/validate_product_evidence.py)

## Clone-and-run pre-production check

The default pre-production runner is CPU-only and performs an **operational smoke test** of the canonical MORPH/QAOA path. It checks that the engine can select paths, construct/transpile the circuit, execute it in Qiskit Aer, score the output, and write a run record. The configured CSG complement also runs a signing-and-verification preflight, then signs the output record. CPU mode uses clearly labeled ephemeral keys for integration tests only; this is not a production identity, durable trust anchor, or hardware performance claim. The smoke uses a synthetic topology fixture, not Kingston/Fez calibration data.

```bash
python -m pip install -e ".[eqg-mvp,dev]"
# Rust/Cargo and Git are needed once to build the pinned CSG companion bridge.
python scripts/run_eqg_mvp.py
```

Configuration lives in [`config/eqg_mvp.yaml`](config/eqg_mvp.yaml). By default, `execution.mode: cpu`, `validation.workload_mvp: true`, and `validation.pytest: false`; the MVP operational smoke runs without requiring IBM credentials. Set `validation.pytest: true` to run the code test suite first, and `validation.verify_evidence: true` to check the saved report/summary pairs. These are separate checks. For a user workload, set `workload_mvp: false` and provide a repository-local Python file exposing `run(config)`.

Hardware is opt-in only: set `execution.mode: hardware`, configure the instance through `IBM_QUANTUM_INSTANCE`, provide the secret in the environment variable named by `token_env`, and set `confirm_spend: true` after reviewing the budget. The runner refuses to submit without these gates. When CSG is enabled for hardware, provision `EQG_CSG_SIGNER_KEY_HEX` and `EQG_CSG_NOTARY_KEY_HEX` from the user's secret manager, and configure/enroll the signer explicitly before production use. The bridge is pinned to the companion [CSG Rust crate](https://github.com/dcpracmatic-prog/CSG/tree/main/sello-integridad-rust); it is not vendored into EQG. Before a hardware submission, the CSG preflight checks the configured persistent notary and authorized signer; its signed preflight record is appended to the CSG chain. After execution, the CSG attestation signs the report bytes and includes the seal, public keys, and verification result; trust in notary identity/public keys must be anchored out of band. A CPU smoke confirms operational execution and the local CSG integration path only; it cannot guarantee provider, queue, access, calibration, service, hardware, or deployment security.

## What the evidence does and does not establish

These are **two positive hardware runs**, one on each named backend, under one small workload and one execution/calibration window per backend. Their z-scores use the notebooks' shot-noise standard errors for each arm. They do not estimate day-to-day or calibration-to-calibration variability, and they do not establish a universal improvement, independent multi-day replication, production readiness, or security certification.

MORPH's reported friction score is a heuristic built from readout and X-gate calibration errors; the submitted run records say `observe_source=backend_props` and `char_job_id=null`. Thus the two reported runs used provider properties, not a Sentinel characterization artifact. The reference path is selected to have high mean friction from a capped path search (up to 400 paths), so interpret the contrast as MORPH versus that specified reference heuristic—not MORPH versus a neutral baseline.

## Research and supporting modules (separate from the MVP claim)

- [MVP scope, evidence audit, and sanitizer notes](docs/eqg-product-mvp.md)
- [Legacy research README, retained for provenance](docs/archive/README-research-legacy.md)
- [Sentinel characterization notes](docs/producto_centinela.md)
- [DD/relay technical reports](docs/eqg/reports/)
- `src/ddqpu/`, `main.py`, `notebooks/eqg/`, and `results/` contain earlier DD validation, Sentinel, and A/C/D/E full-stack experiments. Their results and limitations are distinct from the MVP table above.

## Running tests and the historical full-stack simulation

```bash
pip install -e ".[dev]"
pytest -q
```

The existing Docker workflow exercises the separate A/C/D/E full-stack simulation path. That smoke test verifies software workflow; simulation is not QPU evidence for the MORPH MVP. Hardware notebooks require review of the estimated QPU use and an explicit `CONFIRM_SPEND=True` before job submission.

## Confidentiality and third-party terms

This repository is public. Some historical PDFs in `docs/eqg/reports/` are marked “Confidential.” Their continued public distribution requires authorization from the rights holder; this documentation update does not establish that authorization or remove the PDFs. IBM Quantum hardware evidence remains subject to IBM's terms and policies. The project is not affiliated with or endorsed by IBM.

## License

First-party original content is distributed under Elastic License 2.0 (ELv2), subject to the scope and exceptions in [docs/licensing-scope.md](docs/licensing-scope.md). Third-party components and evidence retain their own terms. See [LICENSE](LICENSE).
