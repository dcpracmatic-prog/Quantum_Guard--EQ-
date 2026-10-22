import base64
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ddqpu.guard import FlowGuard, GuardViolation, sha3_256
from ddqpu.privacy import _cli, create_run_key, decrypt_artifact, encrypt_artifact


def _guard():
    guard = FlowGuard("run-001", "user-a")
    guard.transition("PRECHECK", reason="test preflight")
    guard.transition("AUTHORIZED", reason="test policy approved")
    guard.transition("RUNNING", reason="test execution started")
    return guard


def _event(guard, *, seq=1, nonce="0123456789abcdef", channel="backend->eqg",
           run_id="run-001", owner_id="user-a", visibility="private"):
    payload = b"synthetic-results"
    return {
        "run_id": run_id,
        "owner_id": owner_id,
        "sequence": seq,
        "nonce": nonce,
        "channel": channel,
        "kind": "result",
        "visibility": visibility,
        "payload_bytes": len(payload),
        "payload_sha3_256": sha3_256(payload),
    }


def test_valid_state_machine_and_event():
    g = _guard()
    event = g.accept_event(_event(g))
    assert event["sequence"] == 1
    assert g.sequence == 1
    assert g.snapshot()["accepted_events"] == 1


@pytest.mark.parametrize("changes,match", [
    ({"run_id": "someone-elses-run"}, "run_id"),
    ({"owner_id": "user-b"}, "owner"),
    ({"sequence": 2}, "secuencia"),
        ({"channel": "eqg->community-index", "visibility": "public"}, "community publication"),
    ({"payload_sha3_256": "not-a-hash"}, "hash"),
])
def test_rejects_invalid_protocol_event(changes, match):
    g = _guard()
    event = _event(g)
    event.update(changes)
    with pytest.raises(GuardViolation, match=match):
        g.accept_event(event)
    assert g.state == "QUARANTINED"


def test_rejects_replayed_nonce():
    g = _guard()
    g.accept_event(_event(g))
    event = _event(g, seq=2)
    with pytest.raises(GuardViolation, match="nonce"):
        g.accept_event(event)


def test_rejects_out_of_order_sequence():
    g = _guard()
    with pytest.raises(GuardViolation, match="secuencia"):
        g.accept_event(_event(g, seq=3))


def test_private_egress_budget_quarantines_and_logs_no_payload():
    g = _guard()
    meter = g.meter_channel("eqg", "unexpected", allowed=False, max_bytes=0)
    assert meter.inspect(b"secret-benchmark-payload") is False
    assert meter.state == "QUARANTINED"
    assert meter.delivered_bytes == 0
    event = meter.audit_events[0]
    assert "payload_bytes" not in event
    assert "secret-benchmark-payload" not in repr(event)
    assert event["payload_sha3_256"] == sha3_256(b"secret-benchmark-payload")


def test_send_records_authorized_channel_without_payload():
    g = _guard()
    payload = b"private request"
    event = g.send("eqg->backend", "job_request", payload)
    assert event["payload_sha3_256"] == sha3_256(payload)
    meter = g.channel_meters["eqg->backend"]
    assert meter.delivered_bytes == len(payload)
    assert "private request" not in repr(g.snapshot())


def test_send_blocks_unauthorized_channel_before_forwarding():
    g = _guard()
    with pytest.raises(GuardViolation, match="channel is blocked"):
        g.send("eqg->external-spy", "exfiltration", b"private results")
    assert g.state == "QUARANTINED"
    assert g.channel_meters["eqg->external-spy"].delivered_bytes == 0


def test_artifact_hash_detects_mutation():
    g = _guard()
    payload = b"manifest bytes"
    assert g.verify_artifact(payload, sha3_256(payload))
    with pytest.raises(GuardViolation, match="hash"):
        g.verify_artifact(payload + b"x", sha3_256(payload))


def test_run_key_is_scoped_and_roundtrip(tmp_path):
    key_path = tmp_path / "run-001.key"
    info = create_run_key("run-001", "user-a", key_path)
    plaintext = b'{"private":"benchmark"}'
    envelope = encrypt_artifact(plaintext, info, artifact_name="report.json")
    assert decrypt_artifact(envelope, key_path, requester_id="user-a") == plaintext
    with pytest.raises(PermissionError):
        decrypt_artifact(envelope, key_path, requester_id="user-b")
    create_run_key("run-002", "user-a", tmp_path / "run-002.key")
    with pytest.raises(ValueError, match="run_id"):
        decrypt_artifact(envelope, tmp_path / "run-002.key", requester_id="user-a")
    assert (key_path.stat().st_mode & 0o777) == 0o600


def test_ciphertext_tamper_fails(tmp_path):
    info = create_run_key("run-001", "user-a", tmp_path / "run.key")
    envelope = json.loads(encrypt_artifact(b"private", info, artifact_name="report.json"))
    ciphertext = bytearray(base64.b64decode(envelope["ciphertext_b64"]))
    ciphertext[-1] ^= 1
    envelope["ciphertext_b64"] = base64.b64encode(ciphertext).decode()
    encoded = json.dumps(envelope).encode()
    with pytest.raises(ValueError, match="ciphertext"):
        decrypt_artifact(encoded, tmp_path / "run.key", requester_id="user-a")


def test_publication_requires_explicit_policy():
    g = FlowGuard("run-001", "user-a", allow_community_publication=False)
    g.transition("PRECHECK", reason="test")
    g.transition("AUTHORIZED", reason="test")
    g.transition("RUNNING", reason="test")
    with pytest.raises(GuardViolation, match="community publication"):
        g.emit("eqg->community-index", "publish", b"benchmark", visibility="public")



def test_cli_decrypt_works_with_key_delivered_from_container(tmp_path, monkeypatch):
    key_path = tmp_path / "run.key"
    info = create_run_key("run-container", "local:root", key_path)
    envelope_path = tmp_path / "report.eqg.enc"
    envelope_path.write_bytes(encrypt_artifact(b"private report", info, artifact_name="report.json"))
    output_path = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", [
        "eqg-privacy", "decrypt", "--input", str(envelope_path),
        "--key-file", str(key_path), "--output", str(output_path),
    ])
    assert _cli() == 0
    assert output_path.read_bytes() == b"private report"
