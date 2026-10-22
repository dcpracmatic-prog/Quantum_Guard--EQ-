# v4 Hardware Runs: Two States of Qubit q142

Data: `data/v4_runs.json` (four jobs from September 23, 2026, using the same layout).

| Run | UTC time | Free T2* (µs) | CPMG T2 (µs) | XY4 T2 (µs) | Detuning (kHz) | State |
|---|---|---|---|---|---|---|
| A | 04:00 | 158.6 ± 7.6 | 207.5 ± 12.2 | 220.4 ± 21.4 | −27.04 ± 0.21 | Good |
| B | 04:02 | 45.4 ± 3.7 | 86.2 ± 10.8 | 98.0 ± 11.7 | −25.32 ± 0.38 | Degraded |
| C | 04:14 | 37.6 ± 2.4 | 90.2 ± 10.1 | 87.9 ± 13.1 | −20.81 ± 0.36 | Degraded |
| D | 04:16 | 153.3 ± 6.3 | 217.0 ± 10.6 | 228.3 ± 23.0 | −27.05 ± 0.17 | Good |

## By state (weighted mean; error inflated by sqrt(chi²) when there is tension)

| Quantity | Good state (A, D) | Degraded state (B, C) |
|---|---|---|
| Free T2* (µs) | 155.46 ± 4.85 (χ²=0.3) | 39.91 ± 3.56 (χ²=3.1) |
| CPMG T2 (µs) | 212.91 ± 8.00 (χ²=0.3) | 88.33 ± 7.38 (χ²=0.1) |
| XY4 T2 (µs) | 224.07 ± 15.67 (χ²=0.1) | 93.52 ± 8.73 (χ²=0.3) |
| Detuning (kHz) | −27.05 ± 0.13 (χ²=0.0) | −22.94 ± 2.25 (χ²=74.2) |
| CPMG/free extension | 1.37 ± 0.07 (χ²=0.7) | 2.12 ± 0.25 (χ²=1.4) |
| XY4/free extension | 1.44 ± 0.11 (χ²=0.2) | 2.23 ± 0.24 (χ²=0.1) |

## Decoherence rates (1/T2, in 1/ms)

| Protocol | Good state | Degraded state | Excess in degraded state |
|---|---|---|---|
| Free evolution | 6.43 ± 0.20 | 25.06 ± 2.24 | 18.62 ± 2.24 |
| CPMG | 4.70 ± 0.18 | 11.32 ± 0.95 | 6.62 ± 0.96 |
| XY4 | 4.46 ± 0.31 | 10.69 ± 1.00 | 6.23 ± 1.05 |

CPMG removes 64 ± 7% of the excess dephasing in the degraded state.

XY4 removes 67 ± 7% of the excess dephasing in the degraded state.

## Other invariants

- Correlation between |detuning| and 1/T2* across runs: r = −0.88 (n = 4; indicative, not conclusive).
- ZZ with neighbors in |1⟩ (free evolution): −4.05 ± 0.20 kHz in both states; the degraded state is therefore not caused by the neighbors.
- ZZ under CPMG: −0.27 ± 0.18 kHz; DD suppresses ZZ by 93%.
- 95% upper bound on relay to neighbors: 0.081–0.182% across all four runs.

## Corrections to section 13 of the notebook

- Combining A–D by inverse variance mixes two distinct physical states (χ² up to 294); the average describes neither state.
- The claim “XY4 > CPMG in both runs” does not hold for C (87.9 vs. 90.2 µs); XY4 and CPMG are compatible in all runs.
- Section 11 cites an extension of 0.90–0.94×, which does not appear in any output shown.
- DD extension depends on the state: ~1.4× in the good state and ~2.1× in the degraded state. Reporting it without the state is ambiguous.
