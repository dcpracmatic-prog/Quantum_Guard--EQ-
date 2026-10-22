"""EQG in-flight protocol guard adapted from the channel-duplication PoC.

This module is a fail-closed protocol monitor, not a QPU attestation oracle or
a replacement for CSG signatures, process isolation, or provider-side controls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import secrets
from typing import Any, Iterable


class GuardViolation(RuntimeError):
    """Raised when an event violates the active EQG protocol policy."""


_TRANSITIONS = {
    "INIT": {"PRECHECK", "REJECTED"},
    "PRECHECK": {"AUTHORIZED", "REJECTED", "QUARANTINED"},
    "AUTHORIZED": {"RUNNING", "REJECTED", "QUARANTINED"},
    "RUNNING": {"VERIFYING", "REJECTED", "QUARANTINED"},
    "VERIFYING": {"PACKAGED", "REJECTED", "QUARANTINED"},
    "PACKAGED": set(),
    "REJECTED": set(),
    "QUARANTINED": set(),
}

_DEFAULT_CHANNELS = {
    "eqg->backend", "backend->eqg", "eqg->simulator", "simulator->eqg",
    "eqg->private-store", "eqg->owner", "eqg->community-index",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False, default=str,
    ).encode("utf-8")


def sha3_256(data: bytes) -> str:
    return hashlib.sha3_256(data).hexdigest()


@dataclass
class ChannelMeter:
    """Payload-free egress boundary; records hashes and counts, never content."""

    source: str
    destination: str
    allowed: bool
    max_bytes: int
    state: str = "OPEN"
    attempted_bytes: int = 0
    delivered_bytes: int = 0
    dropped_bytes: int = 0
    audit_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.source}->{self.destination}"

    def inspect(self, payload: bytes, *, visibility: str = "private") -> bool:
        size = len(payload)
        self.attempted_bytes += size
        if self.state != "OPEN":
            self.dropped_bytes += size
            return False
        if not self.allowed or self.delivered_bytes + size > self.max_bytes:
            self.state = "QUARANTINED"
            self.dropped_bytes += size
            self.audit_events.append({
                "event": "unexpected_egress_blocked",
                "channel": self.name,
                "visibility": visibility,
                "payload_sha3_256": sha3_256(payload),
                "attempted_bytes": size,
                "delivered_bytes_before_block": self.delivered_bytes,
                "max_bytes": self.max_bytes,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            })
            return False
        self.delivered_bytes += size
        return True


class FlowGuard:
    """Strict per-run state machine and protocol event guard.

    Events contain no payload. They bind run/owner, monotonic sequence, nonce,
    channel, event kind, visibility, payload length and SHA3-256 digest.
    """

    def __init__(
        self,
        run_id: str,
        owner_id: str,
        *,
        allowed_channels: Iterable[str] = _DEFAULT_CHANNELS,
        max_event_bytes: int = 64 * 1024 * 1024,
        allow_community_publication: bool = False,
    ) -> None:
        if not run_id or not owner_id:
            raise ValueError("run_id y owner_id son obligatorios")
        if max_event_bytes < 1:
            raise ValueError("max_event_bytes debe ser positivo")
        self.run_id = run_id
        self.owner_id = owner_id
        self.state = "INIT"
        self.sequence = 0
        self.max_event_bytes = max_event_bytes
        self.allowed_channels = set(allowed_channels)
        self.allow_community_publication = allow_community_publication
        self._nonces: set[str] = set()
        self.audit_events: list[dict[str, Any]] = []
        self.channel_meters: dict[str, ChannelMeter] = {}

    def _fail(self, reason: str) -> None:
        if self.state not in {"PACKAGED", "REJECTED", "QUARANTINED"}:
            self.state = "QUARANTINED"
        self.audit_events.append({
            "event": "guard_violation",
            "state": self.state,
            "reason": reason,
            "sequence": self.sequence,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        })
        raise GuardViolation(reason)

    def transition(self, target: str, *, reason: str) -> None:
        if target not in _TRANSITIONS.get(self.state, set()):
            self._fail(f"transición inválida: {self.state}->{target}")
        self.audit_events.append({
            "event": "state_transition",
            "from": self.state,
            "to": target,
            "reason": reason,
            "sequence": self.sequence,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        })
        self.state = target

    def accept_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Validate an externally supplied event; rejects replay and reordering."""
        required = {
            "run_id", "owner_id", "sequence", "nonce", "channel", "kind",
            "visibility", "payload_bytes", "payload_sha3_256",
        }
        if not isinstance(event, dict) or not required.issubset(event):
            self._fail("esquema de evento incompleto")
        if event["run_id"] != self.run_id:
            self._fail("run_id does not match the active run")
        if event["owner_id"] != self.owner_id:
            self._fail("owner does not match the active run")
        if type(event["sequence"]) is not int or event["sequence"] != self.sequence + 1:
            self._fail("secuencia repetida, omitida o fuera de orden")
        nonce = event["nonce"]
        if not isinstance(nonce, str) or len(nonce) < 16 or nonce in self._nonces:
            self._fail("nonce inválido o repetido")
        channel = event["channel"]
        if channel not in self.allowed_channels:
            self._fail(f"unauthorized channel: {channel}")
        if event["visibility"] not in {"private", "public"}:
            self._fail("visibilidad inválida")
        if event["visibility"] == "public":
            if channel != "eqg->community-index" or not self.allow_community_publication:
                self._fail("community publication is not authorized by policy")
        if channel == "eqg->community-index" and (
            event["visibility"] != "public" or not self.allow_community_publication
        ):
            self._fail("the community index is disabled for this run")
        size = event["payload_bytes"]
        digest = event["payload_sha3_256"]
        if type(size) is not int or size < 0 or size > self.max_event_bytes:
            self._fail("tamaño de evento fuera de límites")
        if not isinstance(digest, str) or len(digest) != 64 or any(
            c not in "0123456789abcdef" for c in digest
        ):
            self._fail("hash de payload inválido")
        accepted = dict(event)
        accepted["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        self.audit_events.append({
            "event": "protocol_event_accepted",
            **{k: accepted[k] for k in required},
            "timestamp_utc": accepted["timestamp_utc"],
        })
        self.sequence += 1
        self._nonces.add(nonce)
        return accepted

    def emit(
        self,
        channel: str,
        kind: str,
        payload: bytes,
        *,
        visibility: str = "private",
    ) -> dict[str, Any]:
        """Create and validate an in-process event before forwarding it."""
        if not isinstance(payload, bytes):
            raise TypeError("payload debe ser bytes")
        if len(payload) > self.max_event_bytes:
            self._fail("payload supera el límite del guardián")
        event = {
            "run_id": self.run_id,
            "owner_id": self.owner_id,
            "sequence": self.sequence + 1,
            "nonce": secrets.token_hex(16),
            "channel": channel,
            "kind": kind,
            "visibility": visibility,
            "payload_bytes": len(payload),
            "payload_sha3_256": sha3_256(payload),
        }
        return self.accept_event(event)

    def send(
        self,
        channel: str,
        kind: str,
        payload: bytes,
        *,
        visibility: str = "private",
    ) -> dict[str, Any]:
        """Authorize an in-flight logical channel before the caller performs I/O."""
        channel_allowed = channel in self.allowed_channels
        if channel == "eqg->community-index":
            channel_allowed = channel_allowed and self.allow_community_publication and visibility == "public"
        if visibility == "public" and channel != "eqg->community-index":
            channel_allowed = False
        source, destination = channel.split("->", 1) if "->" in channel else (channel, "invalid")
        meter = self.channel_meters.get(channel)
        if meter is None:
            meter = ChannelMeter(
                source, destination, allowed=channel_allowed, max_bytes=self.max_event_bytes
            )
            self.channel_meters[channel] = meter
        if not meter.inspect(payload, visibility=visibility):
            self._fail(f"channel is blocked or budget exceeded: {channel}")
        return self.emit(channel, kind, payload, visibility=visibility)

    def verify_artifact(self, payload: bytes, expected_sha3_256: str) -> bool:
        actual = sha3_256(payload)
        if not secrets.compare_digest(actual, expected_sha3_256):
            self._fail("hash del artefacto no coincide")
        return True

    def meter_channel(
        self, source: str, destination: str, *, allowed: bool, max_bytes: int
    ) -> ChannelMeter:
        name = f"{source}->{destination}"
        if name in self.channel_meters:
            self._fail(f"medidor de canal duplicado: {name}")
        meter = ChannelMeter(source, destination, allowed, max_bytes)
        self.channel_meters[name] = meter
        return meter

    def snapshot(self) -> dict[str, Any]:
        return {
            "protocol": "eqg-flow-guard.v1",
            "run_id": self.run_id,
            "state": self.state,
            "sequence": self.sequence,
            "accepted_events": sum(
                1 for e in self.audit_events if e.get("event") == "protocol_event_accepted"
            ),
            "violations": sum(
                1 for e in self.audit_events if e.get("event") == "guard_violation"
            ),
            "events": list(self.audit_events),
            "channels": {
                name: {
                    "state": meter.state,
                    "attempted_bytes": meter.attempted_bytes,
                    "delivered_bytes": meter.delivered_bytes,
                    "dropped_bytes": meter.dropped_bytes,
                    "audit_events": list(meter.audit_events),
                }
                for name, meter in self.channel_meters.items()
            },
        }
