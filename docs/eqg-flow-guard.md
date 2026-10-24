# EQG Flow Guard and Per-Run Private Artifacts

## Scope

The guard adapts the egress-duplication detector (EgressLink) to an EQG protocol of events and channels. The execution path uses `send()` as a logical gate before simulator/backend calls and before writing private artifacts. It monitors state transitions, owner and run identifiers, monotonic sequence numbers, anti-replay nonces, authorized channels, size limits, and artifact hashes. Logs do not store payloads or keys.

States: `INIT → PRECHECK → AUTHORIZED → RUNNING → VERIFYING → PACKAGED`. Anomalies lead to `QUARANTINED`, while operational errors may lead to `REJECTED`. No silent recovery transition is allowed from terminal states.

## Per-run privacy

- Each run creates a unique random AES-256-GCM key and stores it in a separate file with owner-only permissions (0600 on POSIX systems).
- `report.json` and `ablation.png` are encrypted as `report.eqg.enc` and `ablation.eqg.enc`. Plaintext artifacts are not retained in the output directory.
- `run_manifest.json` contains only the version, a random run identifier, and ciphertext/envelope hashes. It excludes the provider, backend, results, cost, owner, and raw data.
- The key is bound to the `run_id`, local owner, and key identifier. It cannot decrypt another run that uses a different key.
- Do not publish the key, commit it to the repository, or store it beside ciphertexts in a shared environment. Delivering the key file to the user is a separate handoff step.
- To decrypt: `python -m ddqpu.privacy decrypt --input report.eqg.enc --key-file PATH/run.key --output /private/path/report.json`.

Local decryption is authorized by possession of the unique key for that run; therefore, the key file is a secret and must not be shared. The `owner_id` field is an audit label, not user authentication. The `decrypt_artifact` API accepts `requester_id` so an application can compare it with an authenticated identity. In a real multi-user service, authentication, key delivery, and revocation must be integrated with an identity provider/KMS. Anyone who steals a run key can decrypt that run.

## Community index and freshness

Publication is disabled by default. The guard rejects public events unless a policy explicitly enables them; private results are not automatically turned into community records. This version does not implement a global results history. Each fresh comparison requires new runs on the selected platforms; the local manifest does not provide access to other runs.

## Cryptographic limitations

AES-GCM protects artifacts at rest and detects ciphertext tampering. The guard's SHA3-256 hash detects byte discrepancies within the process. This is not equivalent to a notarial CSG seal: CSG integration, key trust, and rollback protection remain separate controls. The guard also cannot establish the physical truth of data reported by a QPU or detect a passive mirror outside the channels it controls.

## Verification

Run `pytest -q tests/test_flow_guard.py`. The suite checks state transitions, replay, reordering, incorrect owners, unauthorized public channels, egress budgets, artifact modification, per-run encryption/decryption, incorrect keys, and ciphertext tampering.


## Boundary for the MORPH MVP runner

The new MORPH CPU runner does not call FlowGuard during workload execution. FlowGuard remains part of the historical A/C/D/E pipeline. A future selectable preflight may use it as a security-control test and block startup on a detected anomaly; that result must be scoped to instrumented logical channels and must not be presented as universal eavesdropper detection. The current CPU runner's CSG preflight is separate: it verifies that the CSG signing/verification integration functions locally.
