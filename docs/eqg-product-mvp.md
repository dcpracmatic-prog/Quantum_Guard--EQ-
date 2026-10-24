# EQG MORPH MVP: scope, evidence, and interpretation

## Product boundary

The current MVP evidenced by `report-4.json` and `report-5.json` is a small, hardware-aware QAOA path-selection loop:

1. Read backend calibration properties (readout error and X-gate error).
2. Convert them to a per-qubit friction proxy: `min(1, 6 × readout_error + 60 × X_error)`.
3. Search connected physical paths of four qubits and select the path with the lowest mean friction (MORPH).
4. Transpile and run the same seeded QAOA MaxCut circuit using the MORPH path and a connected high-friction reference path.
5. Compute approximation ratio (AR), shot-noise standard errors, ΔAR, z, a normal-approximation 95% lower bound, and the recorded contract verdict.

The product actuator in these runs is **MORPH layout selection**. The runs explicitly report “Sin DD. Sin ley E1.” Do not describe these two records as tests of DD, E1/E1rev, Sentinel-guided decision-making, causal attribution, or the full adaptive A/C/D/E stack.

## Preserved hardware evidence

| File pair | Backend | Job ID | MORPH AR ± SE | Reference AR ± SE | ΔAR ± SE | z | 95% lower bound | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| `report-4.json` + `summary-2.txt` | `ibm_kingston` | `dbe6il7gdj9s73fl9o40` | 0.698079 ± 0.006039 | 0.602539 ± 0.006073 | +0.095540 ± 0.008565 | 11.155 | +0.078754 | `PRODUCTO_OK` |
| `report-5.json` + `summary-3.txt` | `ibm_fez` | `dbe6r97sstms73fbj220` | 0.692708 ± 0.006111 | 0.638672 ± 0.006115 | +0.054036 ± 0.008645 | 6.251 | +0.037093 | `PRODUCTO_OK` |

Both records report `n_logical=4`, `qaoa_p=1`, `shots=2048`, `observe_source=backend_props`, and `char_job_id=null`. They meet the stored thresholds ΔAR ≥ 0.02, z ≥ 2, and lower bound > 0.006. `scripts/validate_product_evidence.py` checks report-summary identity and arithmetic consistency without rewriting the source files.

## Comparison definition

The reference is not “naive” without qualification. The notebooks construct it using the same physical coupling graph, searching connected paths and maximizing the mean of the same friction proxy. The search stops after at most 400 paths are found, so the selected result is the best among the enumerated paths, not a proven global maximum over all paths. If the MORPH and reference paths coincide, the notebook falls back to `[0, ..., N-1]`, which may not be a connected path on every backend; this fallback is a condition to validate before treating the notebook as a general runner.

Therefore, report the result as **MORPH-selected low-friction path versus the notebook's high-friction connected-path reference heuristic**. This is a useful internal contrast, but it is not the same as comparison to a randomly selected layout or a prespecified operational baseline.

## Statistical scope

The notebooks calculate arm-level uncertainty from shot counts and combine the two standard errors as if the arm estimates were independent. They report `z = ΔAR / SEΔ` and `ΔAR − 1.96 × SEΔ`. Those calculations support the stated within-job, shot-noise contract. They do not include backend drift, calibration uncertainty, repeated-day variability, multiple-testing adjustment, or an independent replication distribution. The contract verdict is an operational threshold, not a general product certification or universal causal claim.

## Provenance and known notebook hygiene

The submitted files `kaggle.ipynb-20.txt` and `kaggle.ipynb-21.txt` are retained unchanged as run snapshots. Their saved outputs contain the respective Kingston and Fez job evidence. They also contain metadata inconsistencies that should not be copied into future reports: the Fez notebook inherits the Kingston product version/output directory and Kingston runtime-estimate annotation, while both notebooks' fingerprint omits backend identity. The reviewed copies under `notebooks/eqg_product/` correct those labels, include backend in the fingerprint, clear stale execution outputs, and default to no QPU submission. They preserve the algorithm and thresholds; the original reports and summaries remain untouched.

The reviewer notebooks are templates, not new experimental results. Their source changes have not been run against QPU hardware. The Fez timing estimate is explicitly left unset until a backend-specific planning value is supplied; do not reuse the Kingston estimate as a Fez measurement.

## Positioning in the wider repository

The earlier `ddqpu` package, Sentinel probe, DD/coherence studies, and `main.py` A/C/D/E pipeline are retained research lines. Their documented results may motivate future product features, but they are not silently folded into the MVP evidence above. Present them under their own experimental scope and preserve their negative, mixed, or inconclusive findings.

## Public-distribution review gate

The repository is public while the two PDFs under `docs/eqg/reports/` are marked “Confidential.” This PR preserves them to avoid deleting research records. The repository owner should confirm distribution rights or move those documents to appropriately restricted storage before public release. This is not a technical finding about EQG.
