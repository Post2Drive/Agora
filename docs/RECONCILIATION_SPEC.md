# Decision Store and Audit-Chain Reconciliation Specification

**Status:** Partial implementation. #100/#104 provide the read-only decision lifecycle detector; #119 adds read-only sidecar-anchor verification before classification and requires `--anchor` / `--chain-id`; #115 adds API-only, approver-authorised, idempotent repair for missing decision audit events. Repair has no CLI, does not cover outcome/review rows, and cannot recover an unanchored tail. Review found a possible TOCTOU window between #119's verification connection and the subsequent classification connection under concurrent writes.

## 1. Problem and objective

Decision lifecycle and approval operations write the immutable decision record/version to one SQLite store and then append a corresponding event to the separate audit-chain SQLite store. These writes do not share a transaction. If the decision-store commit succeeds and the audit append fails, the decision transition remains stored while its audit event is absent.

Reconciliation must detect and resolve this cross-store gap without rewriting decision history, fabricating audit evidence, weakening hash-chain verification, or silently treating an unaudited transition as fully audited.

The same pattern may later apply to decision outcomes and reviews. The outcome store (#53) is merged and writes its own audit events, but its reconciliation contract is not specified here; this specification's initial scope is decision lifecycle/approval events only.

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

## 5. Gap detection — read-only chain-and-anchor detector on main (#100/#104/#119)

PR #100 adds `agora reconcile`; #119 changes the command contract to `agora reconcile --decisions <db> --audit <db> --anchor <file> --chain-id <id>` and `reconcile(decisions_db, audit_db, *, anchor_path, chain_id)`. It verifies the chain against the local sidecar using a read-only SQLite connection before opening the decision and audit stores for classification. No bootstrap, write or repair occurs during detection.

The merged detector now:

1. Calls `verify_anchored_readonly()` and proceeds only when status is `anchored_verified`. Missing/malformed/wrong-chain anchors, chain-integrity failures, truncation, mismatch, unanchored tail and unreadable stores fail closed with stable blocked codes; CLI exits 2 and emits no classifications.
2. Reopens the stores read-only for source/audit classification. Review finding: because the anchor-check connection is closed before the classification connection is opened, a concurrent writer could append between those steps. Until a shared anchor lock or consistent read snapshot covers both phases, do not claim atomicity against concurrent writers.
3. Verifies the complete audit hash chain with `verify_rows()` before classifying. An invalid chain raises `CHAIN_INVALID`; the CLI exits 2 and emits no classifications.
2. Checks decision-record version continuity and compares each transition row's `decision_fingerprint` with the fingerprint stored for the same decision/version.
3. Matches lifecycle audit events by decision ID and exact `version-N` in `resource_ids`, expected `decision_<transition>` event type, fingerprint and actor/subject ID.
4. Classifies source transitions as `matched`, `missing`, `conflict` or `source_invalid`; lists orphan lifecycle audit events separately.
5. Emits deterministic JSON findings followed by a summary. Exit codes are 0 for no detected gaps, 1 for listed gaps, and 2 when blocked by a missing/unreadable store or invalid chain.

**Hardening now present in main (#104):** source transition/status/actor/method/timestamp are cross-checked against immutable `decision_records.payload_json`; audit operation and exact two-element `resource_ids` are validated; partial-open connections are closed safely. The detector does not itself verify the sidecar anchor. Merged #115 adds `agora.reconcile_repair.apply_repairs()` as a separate API requiring an approver Principal, anchored writer, clean anchor and exact audit head reviewed by the caller. It repairs only `missing` findings; conflicts, invalid sources, orphans and other non-repairable findings block the whole operation. It adds no CLI, outcome/review reconciliation or recovery from an unanchored tail.

PR #100 exact-head Actions run `44963254416` and PR #104 exact-head Actions run `44968039923` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. #104 adds tests for transition/status, actor, method and timestamp mismatches against the immutable payload, wrong audit operation, extra resource IDs and partial-open connection cleanup. PR #102 separately adds the read-only held-outcome list; #106 makes connection-open failures return `STORE_UNREADABLE` / exit 2. Neither is reconciliation of outcome rows against the audit chain.

## 6. Idempotent repair protocol

Automatic repair is permitted only for a `missing` event with an exact, reproducible, allow-listed payload and explicit authorisation. Merged #115 implements `apply_repairs()` as an API-only operation. It requires an approver Principal and anchored writer, verifies a clean anchor and exact audit-head match, and blocks the entire operation if any finding is not `missing`. It does not provide an operator CLI or a durable review queue.

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

### 6.1 Merged repair boundary — PR #115

`agora.reconcile_repair.apply_repairs()` repairs only source-valid decision transitions whose audit event is missing. It requires an anchored writer, approver Principal, clean anchor and exact current audit head. It refuses stale plans, conflicts, invalid source records, orphans and broken chains without writing. Deterministic event IDs make replay idempotent. It never edits/deletes historical decision or audit records. No CLI is included; operator-facing invocation belongs to M2. An unanchored tail still blocks repair by design. Exact-head Actions run `44980052093` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.

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
2. Implemented minimally by #100 and hardened by #104: the read-only `agora reconcile` detector verifies the hash chain and classifies decision lifecycle/approval transitions. Immutable source metadata, audit operation/resource IDs and partial-open connection cleanup are now checked. Stable correlation, anchor verification, outcome/review coverage and queue/repair remain separate gaps. #102/#106 provide a separate read-only held-outcome list with fail-closed connection-open handling, not cross-store reconciliation.
3. Implement the append-only queue and independent review workflow.
4. Add idempotent repair behind explicit configuration and approval.
5. Prove crash/retry/concurrency behaviour and run mutation tests in a clean checkout.
6. Integrate trusted principals and independent audit anchoring before any production use.
7. Reconcile historical gaps only through an owner-approved, evidence-preserving migration plan.

This document specifies the future queue/repair workflow beyond the minimal read-only detector in #100, hardened by #104. The current command does not alter either store, run repairs, enable network access or external write-back, use real data or credentials, run simulations, or change `VALIDATED_PREDICTION_ENABLED` (which remains `False`).
