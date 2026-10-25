> **Archived research-era overview — not the current MVP description.** Preserved for provenance. Its stack-level claims describe earlier DD/Sentinel/A-C-D-E research, not the two MORPH MVP runs. For the current product boundary and evidence, see the repository [README](../../README.md) and [MORPH MVP evidence note](../eqg-product-mvp.md).

---

[![EQG full pipeline Docker smoke test](https://github.com/dcpracmatic-prog/Quantum_Guard--EQ-/actions/workflows/docker-smoke.yml/badge.svg)](https://github.com/dcpracmatic-prog/Quantum_Guard--EQ-/actions/workflows/docker-smoke.yml)
# Edge Quantum Guard (EQG)

**Edge Quantum Guard (EQG)** is a low-level control layer between a quantum workload and its backend. It combines layout selection, health measurement, conditional dynamical decoupling (DD), and causal outcome evaluation.

This repository contains EQG experiments and the `ddqpu` package, which is used to validate CPMG/XY4, coherence, and relay control. The evidence summarized here is **experimental and limited**: it is not product certification and does not demonstrate generalization to other algorithms, system sizes, or providers.

> **Confidentiality:** The included PDF reports are marked “Confidential.” Keep this repository private unless you are authorized to make them public.

## How EQG works

| Role | Module | Function |
|---|---|---|
| Eyes | AOM / Health | Combines calibration and live measurements to estimate operating regime and per-qubit health. |
| Reflexes | MORPH | Selects a connected physical path based on qubit health and CZ gate error rates. |
| Judgment | Minimal-action plan + causal verdict | Decides whether to hold, remap, or conditionally enable DD, and records the reason. |
| Hands | DD + execution | Inserts CPMG/XY4 into idle windows and executes the workload. |

**Sentinel** is a complementary probe that characterizes coherence states and helps decide when DD may be useful. Its results inform the policy; they do not replace validation on each backend.

## Documented experimental evidence

The QAOA runs use MaxCut on an 8-node path (`N=8`, `p=2`). The preregistered criterion for the A/B comparison was `z ≥ 2` for `AR`, the approximation ratio; `ΔAR = AR(EQG) − AR(baseline)` and `SE` is the standard error. The values in this section are those reported in the attached reports.

### IBM Quantum `ibm_fez`: crossover order

| Run | Order | Budget per arm | AR with EQG | Baseline AR | ΔAR ± SE | z |
|---|---|---:|---:|---:|---:|---:|
| R1 | EQG first (B→A) | 7 s | 0.8147 ± 0.0027 | 0.7923 ± 0.0029 | +0.0224 ± 0.0040 | 5.7 |
| R2 | Baseline first (A→B) | 15 s | 0.8092 ± 0.0009 | 0.7713 ± 0.0010 | +0.0379 ± 0.0014 | 27.7 |

The positive effect remained when the arm order was reversed. This reduces, but does not eliminate, the possible effect of chip drift over time. PRE/MID/POST snapshots attribute stability improvements to MORPH and DD in these runs.

### Four-arm ablations: `ibm_marrakesh` and `ibm_kingston`

A = naive layout; C = calibration-selected MORPH layout; D = MORPH with forced DD; E = full EQG. The preregistered criterion for each ablation requires `z ≥ 2` and a positive sign in all four experimental repetitions.

| Backend | AR A | AR C | AR D | AR E |
|---|---:|---:|---:|---:|
| `ibm_marrakesh` | 0.7189 ± 0.0023 | 0.7925 ± 0.0020 | 0.7898 ± 0.0020 | 0.8126 ± 0.0019 |
| `ibm_kingston` | 0.7700 ± 0.0019 | 0.8216 ± 0.0018 | 0.8150 ± 0.0019 | 0.8157 ± 0.0019 |

| Backend | C−A: layout | D−C: isolated DD | E−C: live response | E−A: full stack |
|---|---:|---:|---:|---:|
| `ibm_marrakesh` | +0.0736 (supported) | −0.0027 (inconclusive) | +0.0200 (supported) | +0.0937 (supported) |
| `ibm_kingston` | +0.0516 (supported) | −0.0066 (opposite sign) | −0.0059 (opposite sign) | +0.0458 (supported) |

In both ablations, calibration-based layout selection was the large, consistent contribution. DD and live response varied by device and should not be presented as universal benefits. On `ibm_kingston`, an identical-configuration comparison varied by about 0.006 AR; the report itself cautions against treating effects of this size as conclusive.

**Limitations:** The reports cover three backends and one workload, with runs from a single day/calibration cycle. The four ablation repetitions are not an independent multi-day series. PRE/MID/POST reduces drift but does not eliminate it. More days, formalized ablations, and tests on other backends and workloads are needed before making general claims.

### Full reports

- [Technical Validation Report — IBM Fez (PDF)](docs/eqg/reports/eqg-technical-validation-ibm-fez-2026-10-12.pdf)
- [Validation and Cross-Hardware Reproducibility Plan (PDF)](docs/eqg/reports/eqg-cross-hardware-reproducibility-plan-2026-10-12.pdf)

## EQG notebooks

The four submitted notebooks were preserved as received in `notebooks/eqg/`. For execution, use the reviewed copies in `notebooks/eqg/safe/`:

| Safe notebook | Experiment |
|---|---|
| [QAOA Fez, 7 s, EQG first](notebooks/eqg/safe/qaoa-ibm-fez-7s-eqg-first.ipynb) | A/B run in B→A order. |
| [QAOA Fez, 15 s, baseline first](notebooks/eqg/safe/qaoa-ibm-fez-15s-baseline-first.ipynb) | Replication in A→B order. |
| [Marrakech ablation, ABBA](notebooks/eqg/safe/ablation-ibm-marrakesh-abba.ipynb) | Four arms: A/C/D/E. |
| [Kingston ablation, ABBA](notebooks/eqg/safe/ablation-ibm-kingston-abba.ipynb) | Four arms: A/C/D/E. |

### Setup and security

```bash
pip install -e ".[dev]"
pytest -q
```

The safe copies **do not install packages automatically**. Prepare the environment before opening them. By default, `MODE = "sim"`; simulation checks the workflow but **is not experimental evidence**. These notebooks were not run when added to the repository.

For hardware runs, review the backend, shot plan, and budget, then enable both controls in the relevant notebook:

- ABBA ablations: `MODE = "hardware"` and `CONFIRM_SPEND = True`.
- Fez A/B runs: `MODE = "hardware"` and `CONFIRM_HARDWARE_RUN = True`.

QPU access remains blocked until confirmation is provided. Set the IBM token as an environment secret (for example, a Kaggle secret); **do not paste it into a notebook or commit it to the repository**. Queue wait time and QPU account time are different quantities.

## `ddqpu` package and existing validation

The repository's preflight validation implementation is in `src/ddqpu/`:

- `circuits.py`: circuits aligned to `dt`, spectators, and relay references.
- `backend_utils.py`: qubit ranking, layout, transpilation, and runtime estimation.
- `analysis.py`: readout mitigation, coherence, fitting, and relay testing.
- `experiment.py`: orchestration and experimental analysis.
- `plots.py`: figures.
- `sentinel.py`: Sentinel probing, logging, decisions, and phase correction.

Version 5.0.0 includes free-evolution, CPMG, and XY4 measurements; relay controls; `hardware`, `sim`, and `reuse` modes; automated tests; and reanalysis scripts. Sentinel documentation is in [docs/producto_centinela.md](docs/producto_centinela.md). Earlier package notebooks are in `notebooks/`.

## Sentinel results

The documented analysis for `ibm_fez`, qubit q142, reports two coherence states (`T2*` of 155 ± 5 µs and 40 ± 4 µs), coherence extension under DD, reduced excess dephasing, and a neighboring-qubit transfer upper bound below 0.18% (95% upper bound). See the [Sentinel report](docs/producto_centinela.md) and files in `results/` for context, methods, and limitations.

## Repository structure

```text
src/ddqpu/          DD/Sentinel validation package
notebooks/          Existing package notebooks
notebooks/eqg/      Original submitted EQG notebooks
notebooks/eqg/safe/ EQG copies with simulation mode and explicit QPU lock
docs/eqg/reports/   EQG reports and reproducibility plan
results/            Processed results and figures
evidence/ibm_jobs/  IBM Quantum job evidence
tests/              pytest suite
tools/              Notebook regeneration tools
```

## Data and attribution

Files in `evidence/ibm_jobs/` contain results obtained on IBM Quantum hardware and are retained for scientific reproducibility. Their use remains subject to IBM Quantum terms and policies; the project is not affiliated with or endorsed by IBM. IBMid, email, account identifiers, or CRNs in usage analytics exports are kept out of version control. The `user_id` field was removed from the included evidence.

Qiskit is licensed under Apache-2.0, and dependencies retain their own licenses.

## License and copyright

Copyright (c) 2026 **Arturo Salvador Balderas Hernández**.

The first-party original content in this repository—including code, documentation, notebooks, reports, and results—is distributed under the **Elastic License 2.0 (ELv2)**. See [`LICENSE`](LICENSE) and the [licensing scope and exceptions](docs/licensing-scope.md). Third-party components, data, and materials retain their own terms. ELv2 restricts offering the software as a hosted or managed service that provides access to a substantial portion of its functionality; review the [license text](https://www.elastic.co/licensing/elastic-license) before deploying it that way. The terms of previously distributed versions or copies are not changed retroactively.

## Citation

If you use the code or results in academic or technical work, please cite the repository and its author. To interpret the findings, also retain the protocol, job identifiers, and limitations described in the reports.

## Running the full EQG pipeline (not only DD-QPU)

The `main.py` entry point reproduces the four-arm ablation workflow from the EQG notebook: A (naive layout), C (calibration-based MORPH), D (MORPH + forced DD), and E (full adaptive EQG). It integrates Eyes/AOM, Reflexes/MORPH, causal Judgment, Hands/DD, a QAOA MaxCut workload (`N=8`, `p=2`), PRE/POST snapshots, budget limits, and preregistered contrasts.

### Local simulation with Docker

```bash
docker build -t eqg-sentinel:latest .
docker run --rm -v "$PWD/outputs:/app/outputs" eqg-sentinel:latest \
  --mode sim --smoke --output-dir /app/outputs/eqg_ablation
```

The smoke test reduces shots and repetitions while retaining all four arms. It generates `report.json`, `ablation.png`, and `run_manifest.json`. GitHub Actions builds the image and checks the five contrasts: C−A, D−C, E−C, E−D, and E−A.

### Connecting to the IBM Quantum catalog

```bash
export IBM_QUANTUM_TOKEN="..."
docker run --rm --env IBM_QUANTUM_TOKEN eqg-sentinel:latest --list-backends
```

To run the experiment on hardware, select an available backend and explicitly confirm QPU spend:

```bash
docker run --rm --env IBM_QUANTUM_TOKEN -v "$PWD/outputs:/app/outputs" eqg-sentinel:latest \
  --mode hardware --backend ibm_kingston --confirm-spend \
  --output-dir /app/outputs/eqg_ablation
```

The token is read from the environment and is not stored in the repository or image. Simulation is the default mode and does not submit jobs to IBM.

## Flow guard and per-run private results

The `src/ddqpu/guard.py` module adapts the egress detector to the EQG state machine: preflight, authorization, execution, verification, and packaging. It rejects out-of-order events, nonce replays, unrelated owners or runs, unauthorized channels, and community publication that has not been enabled. Its audit log records hashes and metadata, never payloads or keys.

Full results and figures are encrypted as `report.eqg.enc` and `ablation.eqg.enc` using AES-256-GCM. Each run's random key is written to a separate file with private permissions; its path is displayed when the run completes. Store that file outside repositories and shared directories. To decrypt your own artifact:

```bash
python -m ddqpu.privacy decrypt --input outputs/eqg_ablation/report.eqg.enc --key-file PATH/RUN_ID.key --output PRIVATE_PATH/report.json
```

Each key is bound to a single `run_id`. Community publication remains disabled. The local owner label does not replace an authenticated identity: a multi-user deployment must integrate authentication and key delivery with an identity/KMS service. Encryption and the guard are not equivalent to a CSG seal; the manifest explicitly states that it has not yet been CSG-signed.
