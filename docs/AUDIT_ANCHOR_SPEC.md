# Audit Anchor Specification

**Status:** Design specification; not implementation approval  
**Rung:** 6 — audit-chain integrity  
**Scope:** Documentation only. Synthetic/local verification first; external anchoring is a later separately approved stage.

## 1. Problem and objective

The append-only audit chain verifies links between retained events, but a valid hash chain alone cannot detect truncation of its newest tail: an attacker or faulty process could remove the last events and leave an internally valid earlier prefix.

Maintain an independently stored anchor that records the latest acknowledged chain position and head hash. Verification compares the local chain with that independently retained checkpoint and detects rollback, truncation, mismatch, or an unanchored tail.

An anchor stored beside the chain in the same writable trust boundary is useful for crash recovery and accidental-corruption detection, but it is not a strong defence against an attacker who can rewrite both. The initial local design must state this limitation plainly. A separately administered immutable/external service is a later trust-boundary improvement.

## 2. Anchor record

Each anchor record contains:

| Field | Contract |
| --- | --- |
| `sequence` | Exact sequence number of the audit-chain event being anchored; non-negative integer. |
| `head_hash` | Exact chain head hash at that sequence, using the chain's canonical encoding/hash algorithm. |
| `timestamp` | UTC RFC3339 timestamp when the anchor was committed. |
| `chain_id` | Stable identifier for the chain being anchored. |
| `format_version` | Version of the anchor record format. |

The anchor history is append-only. A new record supersedes the previous checkpoint by adding a record; it must not overwrite history silently. Validate field types, hash format, monotonic sequence, and timestamp format.

## 3. Storage boundary

### 3.1 Initial local implementation

Store anchors in a separate file or separate storage location from `data/audit_chain.sqlite3`. Do not put the only anchor copy in the same SQLite database or transaction as the chain it is intended to protect.

The local path must be explicit configuration, not an implicit current-working-directory path. Restrict filesystem permissions to the service identity, use atomic write/rename and fsync where supported, and retain a recoverable append-only history. A backup copy may improve resilience but is not an independent security anchor if it shares the same administrator and writable host.

The verifier must report the trust level of the configured anchor store. A local sidecar anchor can detect accidental truncation when the anchor survives, but cannot prove integrity against an attacker able to alter both stores.

### 3.2 Later external anchor

A future adapter may publish anchor records to an independently administered append-only or immutable service (for example, a separately controlled object-lock store or trusted timestamp/anchoring service). That adapter requires a separate threat model, authentication and key-management plan, retention policy, outage policy, and owner approval.

Do not introduce a network dependency or external write-back in the initial local implementation.

## 4. Write and update protocol

For every successfully appended audit-chain event, the preferred integrity policy is to advance the anchor synchronously before the protected operation is reported as fully successful:

1. Append the event to the audit chain using the chain's existing append/verification rules.
2. Verify the resulting chain head and obtain its exact sequence and hash.
3. Append a new anchor record to the separate anchor store.
4. Flush the anchor record durably using the platform's supported fsync/atomic-replacement guarantees.
5. Only then report the audited operation as complete.

If the chain append succeeds but the anchor write fails, surface an explicit anchor-update failure. Do not silently claim that the operation has a fully anchored audit record. Preserve the chain event and expose the mismatch for reconciliation; do not delete or rewrite the event to make the stores appear consistent.

Batch anchoring may be considered only as an explicitly weaker mode with a documented maximum unanchored-event window (RPO). It must not be the default for approval, policy-denial, or other security-sensitive events.

Bootstrap must be explicit: verify the complete existing chain, create an initial anchor for its current head, record who/what performed the bootstrap and when, and require an approved maintenance procedure. Never silently initialise an anchor from a chain that has not first passed verification.

## 5. Verification procedure

The verifier must:

1. Load and validate the anchor history and select the latest valid checkpoint for the expected `chain_id`.
2. Run the existing full audit-chain integrity verification.
3. Locate the chain event at the anchor's exact `sequence` and compare its hash to `head_hash`.
4. Compare the current chain head with the anchor sequence/hash.
5. Return a structured status and stable reason code; do not silently repair either store.

Interpret results as follows:

| Condition | Result |
| --- | --- |
| Chain ends before anchored sequence | **Truncation/rollback detected** — fail verification. |
| Hash at anchored sequence differs | **Anchor mismatch** — fail verification. |
| Chain head equals anchor sequence and hash | **Anchored and verified**. |
| Chain contains later events than the anchor | **Unanchored tail** — possible crash between chain append and anchor update; fail closed for protected operations pending reconciliation. |
| Anchor missing, malformed, wrong chain ID, or invalid history | **Anchor unavailable/invalid** — fail verification; do not auto-bootstrap. |
| Chain's own hash verification fails | **Chain integrity failure** — fail verification regardless of anchor state. |

A verifier must also detect anchor-history rollback or deletion where the configured storage provides an independent monotonic/version signal. A purely local file cannot guarantee detection if an attacker can replace both the anchor and chain with an older mutually consistent pair; document this residual risk.

## 6. Failure and recovery

- Anchor write failure: raise a dedicated error and leave the appended chain event intact.
- Anchor store unavailable or unreadable: deny protected operations that require anchored audit; do not silently skip anchoring.
- Unanchored tail: preserve all records; inspect the last valid anchor and chain events, then reconcile through an explicit recovery command or reviewed procedure.
- Chain behind anchor: treat as truncation/rollback, never advance the anchor backward automatically.
- Hash mismatch or malformed history: preserve evidence and fail verification.
- Clock skew: use UTC timestamps for audit context, but do not rely on timestamps for ordering; sequence and hash are authoritative.
- Restore from backup: restore chain and anchor history as a coordinated, verified pair, then compare against any external checkpoint if configured.
- External service outage (future): behaviour must be explicitly configured; security-sensitive operations should fail closed unless a separately approved bounded-outage policy exists.

Recovery must be auditable and must never rewrite historical chain events or silently reset the anchor.

## 7. Acceptance tests

Use synthetic audit events and temporary directories only.

1. A valid chain and matching anchor verify successfully.
2. Removing the newest chain events while retaining the newer anchor is detected as truncation.
3. Altering the event hash at the anchored sequence is detected.
4. A chain with later events than the anchor reports an unanchored tail.
5. A chain whose head exactly matches the anchor reports anchored/verified.
6. Missing, malformed, wrong-chain, or deleted anchor history fails closed.
7. A chain integrity failure is reported even if an anchor file exists.
8. Anchor sequence rollback is rejected.
9. Anchor write failure after a successful chain append raises the dedicated error and preserves the event.
10. A restart after the chain append but before anchor durability detects the unanchored tail.
11. Bootstrap refuses an invalid chain and records an explicit bootstrap event/metadata for a valid chain.
12. The verifier does not mutate, repair, truncate, or rewrite either store.
13. Local storage configuration and permission errors fail closed for protected operations.
14. Tests clearly demonstrate the local sidecar limitation: if both chain and local anchor are replaced with a mutually consistent older pair, local-only verification cannot prove the rollback.

## 8. Mutation proofs

The test suite should demonstrate that these deliberate regressions are caught:

- Skip the anchored-sequence hash comparison.
- Accept a chain shorter than the anchored sequence.
- Treat an unanchored tail as verified.
- Allow anchor sequence to move backward.
- Silently skip anchor writes after chain append.
- Swallow anchor write failures and report success.
- Automatically bootstrap a missing anchor without full chain verification.
- Rewrite or truncate chain events during recovery.
- Store the only anchor copy in the same SQLite database as the chain.
- Treat local sidecar storage as protection against an attacker who can rewrite both stores.

Each mutation must fail at least one named test. Mutation execution belongs to the implementation/verification step, not this documentation task.

## 9. Rollout gates and non-goals

1. Implement local separate-store anchoring behind explicit configuration, using synthetic fixtures and temporary paths.
2. Verify crash windows, atomicity/durability assumptions, failure propagation, and non-mutation behaviour.
3. Run the full suite and mutation proofs in a clean checkout; report exact results.
4. Keep external/network anchoring out of scope until a separate threat review and owner approval.
5. Document deployment permissions, backup/restore procedure, retention, and operator recovery steps before production use.

This document does not authorize source changes, network access, external write-back, real data, credentials, simulations, or changes to `VALIDATED_PREDICTION_ENABLED`. Any implementation must be a separate scoped task and draft PR for review.
