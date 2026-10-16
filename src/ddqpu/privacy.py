"""Per-run authenticated encryption for private EQG artifacts.

AES-GCM protects confidentiality and integrity of each artifact. The random
key is scoped to one run and is stored separately from encrypted artifacts.
This local key-file mechanism is not a substitute for an authenticated remote
identity provider or a KMS in a multi-user hosted deployment.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCHEMA = "eqg.private-artifact.v1"
KEY_SCHEMA = "eqg.run-key.v1"
ALGORITHM = "AES-256-GCM"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()


def local_owner_id() -> str:
    return os.environ.get("EQG_RUN_OWNER") or f"local:{getpass.getuser()}"


def create_run_key(run_id: str, owner_id: str, key_path: str | Path) -> dict[str, Any]:
    """Create a fresh, single-run 256-bit key in a separate private file."""
    key_path = Path(key_path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    record = {
        "schema_version": KEY_SCHEMA,
        "run_id": run_id,
        "owner_id": owner_id,
        "key_id": _key_id(key),
        "algorithm": ALGORITHM,
        "key_b64": base64.b64encode(key).decode("ascii"),
        "warning": "Secret: never publish, commit, log, or place beside shared ciphertext.",
    }
    data = _canonical(record) + b"\n"
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            key_path.unlink()
        except OSError:
            pass
        raise
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return {
        "run_id": run_id,
        "owner_id": owner_id,
        "key_id": record["key_id"],
        "key": key,
        "key_path": str(key_path),
    }


def load_key_record(path: str | Path) -> tuple[dict[str, Any], bytes]:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("schema_version") != KEY_SCHEMA:
        raise ValueError("formato de clave EQG desconocido")
    key = base64.b64decode(record["key_b64"], validate=True)
    if len(key) != 32 or _key_id(key) != record.get("key_id"):
        raise ValueError("clave EQG inválida o key_id incorrecto")
    return record, key


def encrypt_artifact(
    plaintext: bytes, key_info: dict[str, Any], *, artifact_name: str
) -> bytes:
    if not isinstance(plaintext, bytes):
        raise TypeError("plaintext debe ser bytes")
    run_id, owner_id, key = key_info["run_id"], key_info["owner_id"], key_info["key"]
    header = {
        "schema_version": SCHEMA,
        "algorithm": ALGORITHM,
        "run_id": run_id,
        "owner_id": owner_id,
        "key_id": key_info["key_id"],
        "artifact_name": artifact_name,
    }
    aad = _canonical(header)
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    envelope = {
        **header,
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }
    return _canonical(envelope) + b"\n"


def decrypt_artifact(
    envelope_bytes: bytes,
    key_file: str | Path,
    *,
    requester_id: str | None = None,
) -> bytes:
    envelope = json.loads(envelope_bytes.decode("utf-8"))
    key_record, key = load_key_record(key_file)
    if envelope.get("schema_version") != SCHEMA or envelope.get("algorithm") != ALGORITHM:
        raise ValueError("sobre EQG o algoritmo no reconocido")
    for field in ("run_id", "owner_id", "key_id"):
        if envelope.get(field) != key_record.get(field):
            raise ValueError(f"la clave no está vinculada a este artefacto ({field})")
    if requester_id is not None and requester_id != key_record.get("owner_id"):
        raise PermissionError("la identidad solicitante no coincide con el propietario de la corrida")
    ciphertext = base64.b64decode(envelope["ciphertext_b64"], validate=True)
    if hashlib.sha256(ciphertext).hexdigest() != envelope.get("ciphertext_sha256"):
        raise ValueError("hash del ciphertext incorrecto")
    nonce = base64.b64decode(envelope["nonce_b64"], validate=True)
    header = {
        key: envelope[key]
        for key in (
            "schema_version", "algorithm", "run_id", "owner_id", "key_id", "artifact_name"
        )
    }
    aad = _canonical(header)
    return AESGCM(key).decrypt(nonce, ciphertext, aad)


def write_encrypted_artifact(
    path: str | Path, plaintext: bytes, key_info: dict[str, Any], *, artifact_name: str
) -> dict[str, str]:
    path = Path(path)
    encoded = encrypt_artifact(plaintext, key_info, artifact_name=artifact_name)
    path.write_bytes(encoded)
    return {
        "name": path.name,
        "ciphertext_sha256": hashlib.sha256(
            base64.b64decode(json.loads(encoded)["ciphertext_b64"])
        ).hexdigest(),
        "envelope_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Descifra un artefacto privado de una única corrida EQG.")
    sub = parser.add_subparsers(dest="command", required=True)
    dec = sub.add_parser("decrypt")
    dec.add_argument("--input", required=True, help="Archivo .eqg.enc")
    dec.add_argument("--key-file", required=True, help="Clave privada de esa corrida")
    dec.add_argument("--output", required=True, help="Destino privado para el contenido descifrado")
    args = parser.parse_args()
    if args.command == "decrypt":
        plaintext = decrypt_artifact(
            Path(args.input).read_bytes(), args.key_file
        )
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(plaintext)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        print(f"Descifrado en ubicación privada: {target}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
