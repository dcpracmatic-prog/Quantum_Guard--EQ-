#!/usr/bin/env python3
"""Read-only consistency check for the preserved EQG MORPH MVP artifacts."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [
    ("report-4.json", "summary-2.txt", "ibm_kingston", "dbe6il7gdj9s73fl9o40"),
    ("report-5.json", "summary-3.txt", "ibm_fez", "dbe6r97sstms73fbj220"),
]
CONTRACT = {"DELTA_MIN": 0.02, "Z_MIN": 2.0, "IC95_LOW_MIN": 0.006}


def parse_summary(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def close(a: float, b: float, *, tol: float = 1e-10) -> bool:
    return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)


def validate(report_name: str, summary_name: str, backend: str, job_id: str) -> list[str]:
    report = json.loads((ROOT / "evidence" / "product_mvp" / report_name).read_text(encoding="utf-8"))
    summary = parse_summary(ROOT / "evidence" / "product_mvp" / summary_name)
    errors = []
    if report.get("backend") != backend:
        errors.append(f"{report_name}: backend mismatch")
    if report.get("job_id") != job_id or summary.get("JOB") != job_id:
        errors.append(f"{report_name}/{summary_name}: job ID mismatch")
    if summary.get("VERSION") != report.get("version"):
        errors.append(f"{report_name}/{summary_name}: version mismatch")
    if summary.get("VEREDICTO") != report.get("veredicto"):
        errors.append(f"{report_name}/{summary_name}: verdict mismatch")
    for report_key, summary_key in (
        ("delta_AR", "DELTA_AR"), ("z", "Z"), ("AR_EQG", "AR_EQG"), ("AR_REF", "AR_REF")
    ):
        if summary_key not in summary or not close(report[report_key], summary[summary_key]):
            errors.append(f"{report_name}/{summary_name}: {report_key} mismatch")
    if report.get("n_logical") != 4 or report.get("qaoa_p") != 1 or report.get("shots") != 2048:
        errors.append(f"{report_name}: unexpected workload configuration")
    if report.get("observe_source") != "backend_props" or report.get("char_job_id") is not None:
        errors.append(f"{report_name}: observation provenance differs from documented MVP run")
    if report.get("note") != "Producto único EQG: MORPH layout vs ref. Sin DD. Sin ley E1.":
        errors.append(f"{report_name}: scope note mismatch")
    if report.get("contract") != CONTRACT:
        errors.append(f"{report_name}: contract mismatch")
    delta = float(report["AR_EQG"]) - float(report["AR_REF"])
    se_delta = math.sqrt(float(report["se_EQG"]) ** 2 + float(report["se_REF"]) ** 2)
    z = delta / se_delta
    lower = delta - 1.96 * se_delta
    if not close(delta, report["delta_AR"]):
        errors.append(f"{report_name}: delta arithmetic mismatch")
    if not close(se_delta, report["se_delta"]):
        errors.append(f"{report_name}: combined standard error mismatch")
    if not close(z, report["z"]):
        errors.append(f"{report_name}: z arithmetic mismatch")
    if not close(lower, report["ic95_low"]):
        errors.append(f"{report_name}: lower-bound arithmetic mismatch")
    if not (delta >= CONTRACT["DELTA_MIN"] and z >= CONTRACT["Z_MIN"] and lower > CONTRACT["IC95_LOW_MIN"]):
        errors.append(f"{report_name}: reported run does not meet the recorded MVP contract")
    return errors


def main() -> int:
    errors = []
    for pair in PAIRS:
        errors.extend(validate(*pair))
    if errors:
        print("EVIDENCE CHECK FAILED")
        for error in errors:
            print("-", error)
        return 1
    print("EVIDENCE CHECK PASS: 2 preserved report/summary pairs agree and meet the stored contract.")
    print("Scope: within-run shot-noise arithmetic only; this is not an independent hardware reanalysis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
