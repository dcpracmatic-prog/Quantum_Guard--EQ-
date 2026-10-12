#!/usr/bin/env python3
"""EQG Centinela: ejecuta el preflight de qubits y guarda diagnóstico reproducible.

Por defecto usa FakeFez local; el hardware real solo se activa con --mode hardware
(y requiere IBM_QUANTUM_TOKEN o QISKIT_IBM_TOKEN en el entorno).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline EQG Centinela (simulación local o IBM Quantum).")
    parser.add_argument("--mode", choices=("sim", "hardware"), default="sim",
                        help="sim usa FakeFez local; hardware envía un sondeo real a IBM Quantum.")
    parser.add_argument("--backend", default="ibm_fez", help="Nombre de backend IBM para --mode hardware.")
    parser.add_argument("--channel", default="ibm_cloud", help="Canal de Qiskit IBM Runtime.")
    parser.add_argument("--instance", default="open-instance", help="Instancia de IBM Cloud; usa '' para omitirla.")
    parser.add_argument("--candidates", type=int, default=2, help="Cantidad de qubits candidatos (2–8).")
    parser.add_argument("--shots", type=int, default=128, help="Shots por circuito de sondeo.")
    parser.add_argument("--shots-cal", type=int, default=256, help="Shots para calibración de lectura.")
    parser.add_argument("--max-qpu-seconds", type=float, default=20.0, help="Freno de duración estimada en hardware.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/centinela"), help="Directorio de artefactos.")
    return parser.parse_args()


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, Path):
        return str(value)
    return value


def main() -> int:
    args = parse_args()
    if not 2 <= args.candidates <= 8:
        print("ERROR: --candidates debe estar entre 2 y 8.", file=sys.stderr)
        return 2
    if args.shots < 1 or args.shots_cal < 1:
        print("ERROR: shots debe ser un entero positivo.", file=sys.stderr)
        return 2

    from ddqpu import sentinel as S
    from ddqpu.backend_utils import get_service, _qubit_info

    if args.mode == "sim":
        from qiskit_ibm_runtime.fake_provider import FakeFez
        backend = FakeFez()
        print("Modo: simulación local FakeFez; no se enviará ningún trabajo a hardware.")
    else:
        if not (os.environ.get("IBM_QUANTUM_TOKEN") or os.environ.get("QISKIT_IBM_TOKEN")):
            print("ERROR: define IBM_QUANTUM_TOKEN o QISKIT_IBM_TOKEN para usar hardware.", file=sys.stderr)
            return 2
        service = get_service(args.channel, args.instance.strip() or None)
        backend = service.backend(args.backend)
        print(f"Modo: hardware IBM Quantum; backend solicitado: {args.backend}.")

    candidates = S.choose_candidates(backend, k=args.candidates, min_separation=3)
    if len(candidates) < 2:
        raise RuntimeError(f"No se encontraron suficientes candidatos separados: {candidates}")
    print(f"Backend: {backend.name} | candidatos: {candidates}")
    for q in candidates:
        info = _qubit_info(backend, q)
        if info:
            print(f"  q{q}: T1={info.t1_us:.1f} us, T2={info.t2_us:.1f} us, lectura={info.ro_err:.4f}, score={info.score:.2f}")

    pc = S.ProbeConfig(shots=args.shots, shots_cal=args.shots_cal, n_candidates=len(candidates))
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    manifest, counts = S.run_probe(backend, candidates, out, pc,
                                   max_qpu_seconds=args.max_qpu_seconds, mode=args.mode)
    probe = S.analyze_probe(manifest, counts)
    bitacora = S.Bitacora(out / "bitacora.jsonl")
    verdicts = {}
    for q, reading in probe.items():
        info = _qubit_info(backend, q)
        reference = S.reference_state(bitacora.history(backend.name, q), info.t2_us if info else None)
        verdicts[q] = {**S.evaluate(reading, reference), "referencia": reference}
    bitacora.append(backend.name, probe, verdicts, when=manifest.get("created_utc"))

    summary = S.summarize_probe(backend.name, probe, verdicts, manifest["cost"])
    (out / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    report = {
        "mode": args.mode,
        "backend": str(backend.name),
        "candidates": candidates,
        "recommended_qubit": S.rank_live(probe, verdicts)[0] if probe else None,
        "manifest": manifest,
        "probe": probe,
        "verdicts": verdicts,
        "structural_check": "passed" if manifest else "unknown",
    }
    (out / "report.json").write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + summary)
    print(f"\nQubit recomendado: q{report['recommended_qubit']}")
    print(f"Artefactos guardados en: {out.resolve()}")
    print("Estado: PIPELINE_COMPLETADO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrumpido por el usuario.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: pipeline fallido: {exc}", file=sys.stderr)
        raise
