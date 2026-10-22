# Changelog

## 5.0.0
- Added `ddqpu.sentinel` (Sentinel): a 28-circuit probe with K candidates in parallel (~7 seconds of QPU time), quadrature Ramsey + CPMG + T1, Gamma_phi, a JSONL log, reference fingerprint, stable/degraded classification, and `compensate_detuning` (virtual RZ).
- Analyzed four v4 hardware runs: q142 showed two states (T2* 155 vs. 40 µs, with frequency shifts up to 6 kHz); DD removes ~65% of excess dephasing; ZZ remains at −4.05 kHz and is suppressed 93% by CPMG.
- Correction: combining runs from different states by inverse variance is invalid (section 13 of the user's notebook).
- Added `docs/producto_centinela.md`, `notebooks/centinela_preflight.ipynb`, and seven tests.

## v4.0.0
### Relays
- Structural verification counts **all** two-qubit gates (CZ/ECR/CX/SWAP/...). A transpiled SWAP appears as three CZ gates, which v3 did not detect.
- Verify the initial and final layouts of all logical qubits and confirm that bit 0 is measured on the target qubit.
- **Paired** test: compare each neighbor's P(1) with the target active or in |1⟩ against the inactive-target reference, at the same time, using a two-proportion test, Bonferroni correction, and a 95% upper bound. This replaces comparison with another qubit's readout floor and correlations based on seven points.
- Added a ZZ block: prepare neighbors in |1⟩ to measure the target's phase shift and test whether DD cancels it.
- Select the distant control qubit by lower readout error and distance >= 4.

### Results
- Quadrature coherence (X and Y measurements): |ρ01| does not oscillate with detuning.
- Time grid with a dense segment (step <= 5 µs up to 40 µs) and a segment scaled to T2 (0.2x to 1.6x): no aliasing.
- Per-qubit readout mitigation using calibration in the same job.
- Fits with C = 0, weighted by shot noise, with errors inflated by √χ²_red. Low confidence is flagged if the error exceeds 30% or the sweep does not reach 0.7 T2.
- Delays are expressed in dt units, in multiples of backend granularity: free/CPMG/XY4 use exactly the same wait time, with no rounding warnings. Effective time including pulses is reported.
- Randomized circuit order, shots per PUB, runtime estimation, and QPU time limit.
- `sim` (FakeFez) and `reuse` (reanalyze by job ID) modes.
- Qubit selection using target API: min(T2, 2T1), sx error, and readout error.
- The token is not stored on disk.

## v3 (notebook -9)
Neighbor and control measurements; SWAP verification by gate name.
## v2 (notebook -8)
Sweep scaled to T2; Ramsey fit for free evolution.
## v1 (notebook -7)
Free/CPMG/XY4 at 2–30 µs, long sweep, and N sweep.
