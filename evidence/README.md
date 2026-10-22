# Raw Evidence

**Important notice**

Files in `ibm_jobs/` contain results from jobs run on IBM Quantum hardware.
They are published **solely for scientific reproducibility**.
Their use is subject to IBM Quantum terms of service and policies.
This repository is not affiliated with or endorsed by IBM.

---

- `ibm_jobs/<job_id>/`: `*-info.json` and `*-result.json` files downloaded from IBM Quantum (`ibm_fez` backend, September 23, 2026).
- `notebooks_tempranos/`: earlier single-qubit CPMG iterations. Their metric, `|⟨X⟩_CPMG| / |⟨X⟩_free|`, diverges when `⟨X⟩_free ≈ 0` and **does not** represent a genuine extension of T2; see `results/reanalisis_previas.md`.
- Complete v1–v4 notebooks are in `data/notebooks_originales/`.
- The notebooks read the token from the `IBM_QUANTUM_TOKEN` secret; no credentials are stored in repository files.

## Included jobs

| Created (UTC) | Job ID | Backend | v4 run |
|---|---|---|---|
| 2026-09-23T00:38:03.808732Z | `daphuqr18flc739mb47g` | `ibm_fez` | |
| 2026-09-23T00:48:40.436143Z | `dapi3q2c505c73ci8v6g` | `ibm_fez` | |
| 2026-09-23T00:49:44.207824Z | `dapi4a318flc739mbatg` | `ibm_fez` | |
| 2026-09-23T01:37:24.089641Z | `dapiql318flc739mc7c0` | `ibm_fez` | |
| 2026-09-23T02:07:21.313643Z | `dapj8mac505c73ciad30` | `ibm_fez` | |
| 2026-09-23T02:56:28.656111Z | `dapjvn318flc739mdml0` | `ibm_fez` | |
| 2026-09-23T03:40:08.933520Z | `dapkk6318flc739metfg` | `ibm_fez` | |
| 2026-09-23T03:48:03.031814Z | `dapknsgr7bnc73b3k930` | `ibm_fez` | |
| 2026-09-23T03:48:47.131596Z | `dapko7sak42c73ciou90` | `ibm_fez` | |
| 2026-09-23T03:59:50.772194Z | `dapktdj18flc739mf8l0` | `ibm_fez` | A |
| 2026-09-23T04:01:02.436362Z | `dapktvgr7bnc73b3kg8g` | `ibm_fez` | B |
| 2026-09-23T04:13:24.669217Z | `dapl3p2c505c73cid330` | `ibm_fez` | C |
| 2026-09-23T04:14:46.992788Z | `dapl4dkak42c73cipd30` | `ibm_fez` | D |
