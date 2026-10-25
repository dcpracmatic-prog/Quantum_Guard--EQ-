#!/usr/bin/env python3
"""Static safety/structure checks for reviewed MORPH MVP notebook templates."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "ibm_kingston.ipynb": ("ibm_kingston", "eqg_product_kingston_reviewed"),
    "ibm_fez.ipynb": ("ibm_fez", "eqg_product_fez_reviewed"),
}


def source(cell: dict) -> str:
    value = cell.get("source", "")
    return "".join(value) if isinstance(value, list) else value


def main() -> int:
    errors: list[str] = []
    for name, (backend, outdir) in EXPECTED.items():
        path = ROOT / "notebooks" / "eqg_product" / name
        try:
            notebook = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{name}: invalid JSON: {exc}")
            continue
        if notebook.get("nbformat") != 4 or not notebook.get("cells"):
            errors.append(f"{name}: invalid or empty notebook format")
            continue
        all_src = "\n".join(source(c) for c in notebook["cells"])
        if f'BACKEND_NAME = "{backend}"' not in all_src:
            errors.append(f"{name}: backend label mismatch")
        if "CONFIRM_SPEND = False" not in all_src:
            errors.append(f"{name}: QPU confirmation must default to False")
        if f'OUT = Path("{outdir}")' not in all_src:
            errors.append(f"{name}: output path mismatch")
        if '"backend": BACKEND_NAME' not in all_src:
            errors.append(f"{name}: fingerprint must include backend identity")
        if "Sin DD" not in all_src and "without DD" not in all_src and "does not apply DD" not in all_src:
            errors.append(f"{name}: missing scope note clarifying no DD in MVP run")
        for idx, cell in enumerate(notebook["cells"]):
            if cell.get("cell_type") != "code":
                continue
            if cell.get("outputs") or cell.get("execution_count") is not None:
                errors.append(f"{name}: stale output/execution state in cell {idx}")
            code = source(cell)
            cleaned = []
            for line in code.splitlines():
                if line.lstrip().startswith(("!", "%")):
                    continue
                cleaned.append(line)
            try:
                ast.parse("\n".join(cleaned), filename=f"{name}:cell{idx}")
            except SyntaxError as exc:
                errors.append(f"{name}: syntax error in cell {idx}: {exc}")
    if errors:
        print("NOTEBOOK CHECK FAILED")
        for e in errors:
            print("-", e)
        return 1
    print("NOTEBOOK CHECK PASS: both reviewed templates parse, identify the correct backend, and default to no QPU submission.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
