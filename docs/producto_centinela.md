# QPU Sentinel: From Experiment to Practical Tool

Public summary document. Based on notebooks v1–v4 and four hardware runs performed on September 23, 2026, on the `ibm_fez` backend (qubit q142).

## Summary

The experimental data show something more valuable than a simple extension of $T_2$ through dynamical decoupling (DD): qubit q142 changes state on a timescale of minutes. The provider's published calibration does not reflect these fluctuations.

Two runs showed $T_2^* \approx 155\,\mu\mathrm{s}$, while two others showed $T_2^* \approx 40\,\mu\mathrm{s}$, accompanied by frequency shifts of up to 6 kHz. This behavior is consistent with the known physics of two-level systems (TLSs) coupled to the qubit.

Sentinel is an approximately 7-second QPU preflight probe that measures several candidate qubits in parallel and answers three questions before an expensive job is submitted:

- Which qubit is currently in a good state?
- Should dynamical decoupling be enabled, and how much improvement is expected?
- Which phase correction (a zero-cost virtual Z rotation) should be applied?

Each probe can contribute to a per-qubit log. Over time, the observed states, dwell times, and frequency fingerprints form a useful knowledge asset.

The working prototype is in this repository: `src/ddqpu/sentinel.py` and `notebooks/centinela_preflight.ipynb`.

## Main experimental results (v4 runs)

| Run | Approx. time (UTC) | Free $T_2^*$ (µs) | CPMG $T_2$ (µs) | XY4 $T_2$ (µs) | Detuning (kHz) | State |
|---|---:|---:|---:|---:|---:|---|
| A | 04:00 | 158.6 ± 7.6 | 207.5 ± 12.2 | 220.4 ± 21.4 | −27.04 ± 0.21 | Good |
| B | 04:02 | 45.4 ± 3.7 | 86.2 ± 10.8 | 98.0 ± 11.7 | −25.32 ± 0.38 | Degraded |
| C | 04:14 | 37.6 ± 2.4 | 90.2 ± 10.1 | 87.9 ± 13.1 | −20.81 ± 0.36 | Degraded |
| D | 04:16 | 153.3 ± 6.3 | 217.0 ± 10.6 | 228.3 ± 23.0 | −27.05 ± 0.17 | Good |

## Summary by state

| Quantity | Good state (A, D) | Degraded state (B, C) |
|---|---:|---:|
| Free $T_2^*$ | 155 ± 5 µs | 40 ± 4 µs |
| CPMG $T_2$ | 213 ± 8 µs | 88 ± 7 µs |
| CPMG/free extension | 1.37 ± 0.07× | 2.12 ± 0.25× |
| XY4/free extension | 1.44 ± 0.11× | 2.23 ± 0.24× |
| Detuning | −27.05 ± 0.13 kHz | −21 to −25 kHz |

## Main physical observations

- Two discrete states are observed, rather than continuous drift. Runs within each state are statistically compatible; the states differ by more than 10σ.
- The frequency shifts together with the dephasing, a characteristic signature of a TLS coupled to the qubit.
- CPMG removes approximately 64–65% of the excess dephasing associated with the degraded state.
- The ZZ coupling to neighboring qubits, measured with neighbors in |1⟩, is −4.05 ± 0.20 kHz and remains unchanged between states. DD suppresses it by approximately 93%.
- The 95% upper bound on relay (leakage or crosstalk) to neighboring qubits is below 0.18% in all runs.

More quantitative detail is available in `results/v4_estados.md` and `results/v4_estados.json`.

## What Sentinel implements

The `src/ddqpu/sentinel.py` module provides:

- Parallel probing of multiple candidate qubits (quadrature Ramsey, CPMG, and $T_1$).
- Estimation of detuning ($\Delta f$), $T_2^*$, echo $T_2$, $T_1$, and the pure-dephasing rate ($\Gamma_\varphi$).
- Qubit-state classification (stable/degraded).
- Reference-fingerprint generation and logging.
- Phase correction through a virtual Z rotation (`compensate_detuning`).

The `notebooks/centinela_preflight.ipynb` notebook can run standalone in simulation or hardware mode.

## Scope of this document

This document presents experimental results and a high-level description of the Sentinel tool. It does not include market projections, detailed cost-savings estimates, or commercial validation plans. Those topics are outside the scope of this public repository.

## Reproducibility

Raw IBM Quantum job data used in this study are included in `evidence/ibm_jobs/` solely for scientific reproducibility. Their use remains subject to the IBM Quantum terms of service.

Copyright (c) 2026 Arturo Salvador Balderas Hernández

Licensed under Elastic License 2.0 (see the root `LICENSE` file).
