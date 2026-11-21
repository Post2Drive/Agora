# Decision Store and Audit-Chain Reconciliation Specification

**Status:** Design specification only; no queue, worker, repair command or automatic reconciliation is implemented by this document.

## 1. Problem and objective

Decision lifecycle and approval operations write the immutable decision record/version to one SQLite store and then append a corresponding event to the separate audit-chain SQLite store. These writes do not share a transaction. If the decision-store commit succeeds and the audit append fails, the decision transition remains stored while its audit event is absent.

Reconciliation must detect and resolve this cross-store gap without rewriting decision history, fabricating audit evidence, weakening hash-chain verification, or silently treating an unaudited transition as fully audited.

The same general pattern may later apply to decision outcomes and reviews if/when those records are implemented and their audit contract is confirmed. This specification's initial scope is decision lifecycle/approval events only.

## 2. Invariants

1. Decision records and lifecycle versions are append-only. Reconciliation never updates or deletes a historical decision version/event.
2. Audit-chain events are append-only. Reconciliation never edits, deletes, reorders or truncates chain entries.
3. A decision transition is not considered fully audited merely because its decision-store transaction committed.
4. An audit append is idempotent by a deterministic reconciliation key, not by reusing an arbitrary event ID.
5. A missing audit event is not proof that the transition did not happen; the decision store remains authoritative for the committed transition.
6. A conflicting event, invalid chain, duplicate key with different content, or ambiguous mapping requires human review and must not be auto-repaired.
7. Reconciliation records and repair attempts are themselves auditable, but the reconciler must not recursively hide its own audit failure.
8. No simulated preference, agent action or report statement can be converted into an observed decision outcome by reconciliation.

## 3. Source evidence and correlation contract

For each committed decision transition, the source evidence should include:

- decision ID and exact version;
- transition type (proposed, approved, rejected, expired, superseded);
- actor/subject ID;
- transition timestamp and method;
- decision fingerprint;
- policy decision metadata for approval/denial where present;
- expected audit event type and allow-listed payload;
- source decision-store path/identity and a stable store identifier.

The existing lifecycle audit event includes an event ID generated at append time, event type, subject ID, operation, decision, resource IDs and decision fingerprint, with optional reason/policy version. A future reconciliation contract should add a stable correlation identifier to the decision-store transition record itself so the expected event can be reconstructed deterministically.

Do not reconstruct event payloads from mutable current state alone. Use the exact immutable decision version and its stored transition event. If the current schema lacks enough immutable data to reproduce the original safe event exactly, classify the row as `needs_review` rather than guessing.

## 4. Queue model

Proposed append-only reconciliation queue fields:

| Field | Meaning |
| --- | --- |
| `reconciliation_id` | Opaque unique ID for one identified gap. |
| `source_store_id` | Stable identifier for the decision store. |
| `decision_id` / `decision_version` | Exact committed transition reference. |
| `transition_type` | Expected lifecycle event type. |
| `correlation_id` | Deterministic identifier linking source transition and audit event. |
| `expected_event_hash` | Hash of canonical allow-listed event payload, when deterministically available. |
| `status` | `detected`, `ready_for_review`, `approved_for_repair`, `repaired`, `needs_review`, `rejected`, `blocked`. |
| `detected_at` | UTC RFC3339 detection timestamp. |
| `attempt_count` | Number of repair attempts; monotonic. |
| `last_error_code` | Stable non-sensitive failure category. |
| `reviewer` / `reviewed_at` | Independent human review evidence. |
| `repair_event_id` | Exact audit event ID after successful repair. |

Queue transitions are append-only status events; never overwrite the detection record. Free-text notes must be bounded, access-controlled and excluded from the audit chain. Secrets and personal values are prohibited.

## 5. Gap detection

A read-only detector should:

1. Verify the complete audit chain before attempting reconciliation.
2. Enumerate committed decision transition events from the decision store in deterministic order.
3. Match each source transition to an audit-chain event using the stable correlation ID and exact decision ID/version/type/fingerprint.
4. Classify each source transition:
   - `matched`: exactly one matching valid audit event;
   - `missing`: no matching event and the source contains enough immutable data to reconstruct it;
   - `conflict`: multiple events, mismatched payload/hash, duplicate correlation ID or contradictory transition;
   - `unreconstructable`: missing immutable source fields;
   - `chain_invalid`: audit-chain verification fails;
   - `source_invalid`: decision version history is broken or inconsistent.
5. Detect orphan audit events that reference no committed source transition.
6. Emit a deterministic gap fingerprint so repeated scans identify the same gap rather than creating duplicate queue items.

The detector must not append to either store or modify the queue while performing the initial inventory. A separate queue writer may append detection records after the read-only scan completes.

## 6. Idempotent repair protocol

Automatic repair is permitted only for a `missing` event with an exact, reproducible, allow-listed payload and explicit independent approval.

1. Acquire a per-store reconciliation lock or equivalent compare-and-swap guard.
2. Re-verify the decision transition and audit-chain head; abort if either changed since review.
3. Recompute the deterministic correlation ID and canonical event payload from immutable source data.
4. Check whether the correlation ID already exists:
   - if an identical event exists, mark the queue item `repaired/already_present` without appending a duplicate;
   - if the event differs, mark `conflict` and stop;
   - if absent, proceed only with approval.
5. Require a reviewer distinct from the original actor and the repair operator. Approval must bind to the exact reconciliation fingerprint, source version, expected event hash and current audit head hash.
6. Append one audit event with a deterministic idempotency key and a distinct repair marker. The original transition timestamp remains an event attribute; the audit store's recorded timestamp reflects actual append time.
7. Verify the audit chain and locate the exact newly appended event.
8. Append a reconciliation completion record with event ID, sequence, head hash, reviewer, operator, approval reference and result.
9. If the append succeeds but completion recording fails, the next pass must discover the identical event and complete idempotently without adding another event.

Do not backdate the chain's recorded timestamp, overwrite the original audit event, or pretend the repaired event was appended at the original transition time.

## 7. Cases that must never auto-repair

Require human investigation for:

- invalid audit-chain hash/link verification;
- suspected tail truncation or anchor mismatch;
- decision-store version-chain inconsistency;
- missing or mutable source transition details;
- duplicate or conflicting audit events;
- policy decision payload mismatch;
- unknown event schema/version;
- changed audit head since approval;
- actor identity or scope ambiguity;
- any case requiring a guessed reason, role, policy result or event payload.

A future independent audit anchor must be verified before repair where configured. Reconciliation cannot use a local sidecar anchor as proof against an attacker who can rewrite both local stores.

## 8. Operational roles and separation

- **Detector:** read-only inventory; cannot repair.
- **Decision owner/data steward:** confirms source transition and business context.
- **Independent reviewer:** reviews the exact gap fingerprint and proposed event; must differ from original actor and repair operator.
- **Repair operator:** executes the approved append-only repair; cannot approve their own repair.
- **System owner:** authorises exceptional recovery and signs the final reconciliation report.

The current caller-supplied role interface is not a trusted identity system. Production use requires the separately specified trusted-principal adapter to be implemented and reviewed first.

## 9. Failure behaviour

- Store unavailable: report `blocked`; no repair.
- Audit chain invalid: halt all repairs; preserve both stores read-only.
- Concurrent head change: abort and require a fresh scan/review.
- Duplicate correlation key with identical payload: idempotent success without another append.
- Duplicate key with different payload: `conflict`; manual investigation.
- Audit append failure: preserve the source transition and queue item; retry only after verifying current chain and idempotency key.
- Queue write failure: do not report repair complete; the audit event remains discoverable by correlation ID.
- Partial recovery: report `needs_review`; never silently clear the gap.

All diagnostics must use stable error codes and opaque IDs, not raw decision content, personal values, secrets or unrestricted free text.

## 10. Acceptance tests

Use temporary SQLite stores and synthetic decision records only.

1. A matching transition/event pair is classified `matched`.
2. A committed transition with no audit event is detected as `missing`.
3. Repeated scans produce one stable gap fingerprint and no duplicate queue entries.
4. An identical existing event is recognised idempotently without a second append.
5. Same correlation ID with different payload is classified `conflict`.
6. Missing immutable source details are classified `unreconstructable`.
7. Invalid audit chain blocks all repairs.
8. Invalid decision version history blocks repair.
9. A repair requires independent approval bound to exact source and audit-head fingerprints.
10. A concurrent audit append between approval and repair aborts the repair.
11. A successful repair appends exactly one event and verifies the chain.
12. A crash after audit append but before queue completion is recovered idempotently.
13. A failed audit append leaves the original decision transition unchanged and retryable.
14. Orphan audit events are surfaced and never deleted.
15. Repair never changes a decision record, historical transition, or existing audit event.
16. Logs and audit events contain no secret, raw personal value or decision free text.

## 11. Mutation proofs

The implementation test suite must show named tests fail if a mutation:

- skips full audit-chain verification before scanning;
- matches only on decision ID and ignores version/type/fingerprint;
- creates a new queue row on every scan;
- appends a duplicate event after a crash/retry;
- accepts a conflicting event payload;
- reconstructs an event from mutable current state;
- permits the original actor to approve their own repair;
- omits the audit-head compare-and-swap check;
- swallows an audit append failure;
- marks a gap repaired before verifying the appended event;
- rewrites or deletes historical decision/audit records;
- auto-repairs an invalid chain or anchor mismatch.

## 12. Rollout gates and non-goals

1. Add immutable correlation metadata to new decision transition records; define how legacy transitions are classified when correlation data is absent.
2. Implement a read-only detector and deterministic gap report.
3. Implement the append-only queue and independent review workflow.
4. Add idempotent repair behind explicit configuration and approval.
5. Prove crash/retry/concurrency behaviour and run mutation tests in a clean checkout.
6. Integrate trusted principals and independent audit anchoring before any production use.
7. Reconcile historical gaps only through an owner-approved, evidence-preserving migration plan.

This document does not implement reconciliation, alter current stores, run repairs, enable network access or external write-back, use real data or credentials, run simulations, or change `VALIDATED_PREDICTION_ENABLED` (which remains `False`).
