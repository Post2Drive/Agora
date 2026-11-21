# Decision/Audit Reconciliation — Manual Triage and Recovery Procedure

**Status:** Proposed operator procedure; requires owner approval and a synthetic rehearsal before it can count as a milestone recovery path  
**Assessment base:** `main` at `90789ccfd866c038ce67753645b5e258134b9af3`  
**Specification:** `docs/RECONCILIATION_SPEC.md` (#57)  
**Scope:** Decision lifecycle and approval events only; local stores; synthetic rehearsal evidence only

## 1. Purpose and current implementation boundary

Use this procedure when a decision transition is committed to the decision store but its corresponding audit-chain event may be missing, conflicting or unverifiable.

The decision store and audit chain are separate SQLite stores and do not share a transaction. A committed transition is not fully audited merely because the decision-store write succeeded. Preserve the transition and its evidence; never rewrite history to make the stores appear consistent.

**This is not an implemented Agora reconciliation feature.** Main contains no reconciliation queue, detector, worker or repair command. #57 is a design specification. This document defines a controlled manual triage and hold process; it does not supply a supported repair writer or authorise direct store edits. Until the owner approves and rehearses the procedure and a safe append-only repair path is available, a missing event remains blocked for escalation.

The initial #57 scope is decision lifecycle/approval events. It does not reconcile outcome rows or outcome dependency markers.

## 2. Trigger and immediate containment

Start a case when any of the following occurs:

- a decision transition reports that its audit append failed;
- a transition exists in the decision store but no exact corresponding audit event can be found;
- an audit append or anchor verification returns an error;
- duplicate, mismatched or orphan audit events are reported;
- an operator cannot establish whether a committed transition is fully audited.

Immediately:

1. Stop further protected decision transitions and approvals for the affected local store/scope. Do not continue on the assumption that the audit problem is temporary.
2. Keep the committed decision transition intact. Do not roll it back, delete it, overwrite it or repeat the business operation.
3. Preserve the decision database, audit database, anchor sidecar (if configured), lock sidecar and relevant application logs.
4. Notify the system owner and assign separate decision-owner, independent-reviewer and operator roles. The original actor must not review or approve their own repair.
5. Do not use this procedure on real/personal/customer data under this documentation task. Any such use needs separate explicit owner authorisation and the applicable data-handling controls.

## 3. Preserve a read-only evidence set

Create a case record in the owner-approved restricted incident register. The register is an operator record, not an Agora queue or feature.

Record only opaque identifiers and integrity metadata:

- case ID and detection time (timezone-aware);
- repository/application version and local store identifiers;
- exact decision ID and version, if known;
- source and audit file identities/paths in the restricted case record;
- cryptographic hashes of preserved copies;
- audit-chain head sequence/hash and anchor sequence/hash, if readable;
- stable error codes and operator identities;
- the current hold status.

Preserve consistent read-only copies of the decision store, audit store and anchor files before any further investigation. Keep originals unchanged. Restrict access to the minimum authorised operators. Do not copy raw decision content, personal values, secrets, tokens or unrestricted free text into shared logs or the audit chain.

If a safe read-only copy cannot be obtained, record `blocked` and escalate; do not attempt a repair against a moving store.

## 4. Verify store integrity before comparing records

1. Verify the complete audit hash chain using the repository's supported read-only verification path.
2. If a local anchor is configured, verify it with `verify_anchored()` against the same chain. The merged #63 implementation reports `trust_level: local_sidecar`; it is not an external checkpoint and cannot detect an attacker who rewrites both local stores.
3. Verify the decision version history using the supported read-only inspection path.
4. Record the exact result and head fingerprints in the case register.

**Stop without repair** for any invalid chain, truncation, anchor mismatch, invalid/missing anchor after prior use, unanchored tail, broken decision-version history, unreadable store or uncertain store identity. Preserve evidence read-only and escalate as an integrity incident. Never bootstrap an anchor to make an existing incident appear clean, move an anchor backward, restore only one half of a store pair, or repair an invalid chain.

## 5. Build a read-only transition inventory

For each committed decision transition, identify the exact immutable source version and collect, where present:

- decision ID and exact version;
- transition type (proposed, approved, rejected, expired or superseded);
- actor/subject ID, transition timestamp and method;
- decision fingerprint;
- policy decision metadata for approval/denial;
- expected audit event type and allow-listed payload;
- source-store identity and stable correlation identifier.

Compare it with the audit chain using the exact decision ID, version, transition type, fingerprint and stable correlation ID. Inspect orphan audit events as well as missing events. Do not match on decision ID alone, current mutable state, names, timestamps or approximate payload similarity.

If the stored transition does not contain enough immutable information to reproduce the original safe event exactly, classify it as `unreconstructable` / `needs_review`; do not infer a role, reason, policy result or event payload.

## 6. Classify the case

Use one of these bounded classifications in the case register:

| Classification | Meaning | Required handling |
|---|---|---|
| `matched` | Exactly one valid event matches the exact committed transition | Record evidence; close only after independent verification |
| `missing` | No matching event; immutable source data is sufficient to reconstruct the exact allow-listed event | Hold; proceed to the repair-approval gate only |
| `conflict` | Multiple events, mismatched payload/hash, duplicate correlation ID or contradictory transition | Human investigation; no automatic or manual append |
| `unreconstructable` | Required immutable source fields/correlation data are absent | Keep blocked; do not reconstruct from mutable state |
| `chain_invalid` | Full audit-chain verification fails | Stop all repairs; preserve both stores read-only |
| `source_invalid` | Decision version history is broken or inconsistent | Stop; preserve evidence and escalate |
| `orphan_event` | Audit event has no corresponding committed source transition | Preserve and investigate; never delete it |

Repeated inventory must use the same case/gap fingerprint for the same source transition. Do not create duplicate case entries merely because the scan is repeated.

## 7. Independent review and repair gate

A repair may be considered only when all of the following are true:

- classification is exactly `missing`;
- the immutable source version contains every field needed to reproduce one canonical allow-listed event;
- a stable deterministic correlation/idempotency key can be established from immutable evidence;
- the audit chain and configured anchor verify cleanly;
- the source version and audit head have not changed since the evidence was reviewed;
- the decision owner confirms the transition;
- an independent reviewer, different from the original actor and the repair operator, approves the exact case/gap fingerprint, source version, expected event hash and current audit-head hash;
- the system owner explicitly authorises the repair path.

**Current-main limitation:** #57 specifies this gate but main does not provide a reconciliation queue, deterministic gap detector or repair command. Do not issue SQL updates, insert rows directly, edit JSONL by hand, bypass the anchor wrapper, or invent a one-off command. If no separately reviewed and owner-approved append-only repair path is available, leave the case `blocked` and escalate for implementation. This document alone does not authorise a repair.

If a supported repair path is later implemented and separately approved, its operator must:

1. acquire the per-store reconciliation lock or compare-and-swap guard;
2. re-verify the exact source version and audit head after approval;
3. recompute the deterministic key and canonical event from immutable source data;
4. check for an existing event: identical means idempotent completion without another append; different content means `conflict` and stop;
5. append exactly one repair-marked audit event through the approved append-only path;
6. preserve the original transition timestamp as an event attribute while recording the actual append timestamp;
7. verify the full chain and configured anchor, then capture the exact event ID, sequence and head hash;
8. append a completion record to the restricted case register with reviewer, operator, approval reference and result.

If the audit append succeeds but completion recording fails, the next pass must find the same deterministic event and complete idempotently; it must not append a duplicate. If the audit append or case-register write fails, preserve the partial state and keep the case open.

## 8. Close-out and escalation

Close a case only when the independent reviewer and system owner can verify:

- the exact source transition and classification;
- the audit chain and configured anchor are valid;
- either the exact event was already present or an approved append-only repair was verified;
- no historical decision or audit event was modified or deleted;
- the case register contains the evidence hashes, event ID/sequence/head hash, reviewer/operator separation and final disposition.

If any point is uncertain, leave the case `needs_review` or `blocked`. A successful decision-store commit is not proof of successful audit. Do not resume protected operations until the system owner confirms the audit path is healthy.

## 9. Manual case-register fields

The restricted register should contain one append-only case history with:

| Field | Purpose |
|---|---|
| case_id / gap_fingerprint | Stable opaque case identity |
| source_store_id / decision_id / decision_version | Exact source transition |
| transition_type / correlation_id | Expected event identity |
| expected_event_hash / audit_head_hash | Evidence bound to review |
| classification / status | Bounded triage state |
| detected_at / reviewed_at / closed_at | Time-ordered case history |
| reviewer / operator / decision_owner | Separation-of-duties evidence |
| approval_reference | Owner approval bound to exact case fingerprint |
| repair_event_id / sequence / resulting_head_hash | Verified repair evidence, if a supported repair occurred |
| last_error_code | Stable non-sensitive failure category |

Keep raw values, decision rationale, personal information, credentials and unrestricted free text out of this register and the shared audit chain.

## 10. Synthetic rehearsal and acceptance checklist

Before this procedure is treated as an approved manual recovery path, the owner must authorise a separate rehearsal using temporary SQLite stores and invented synthetic decision records only. Do not use existing studies, NCC Park Square, E0_C0_D0 or real data.

The rehearsal must demonstrate:

- a matching pair is classified `matched`;
- a missing event is detected without changing either source store;
- repeated scans preserve one stable gap fingerprint;
- conflicting/duplicate events are held for human investigation;
- absent immutable correlation/source data is `unreconstructable`;
- invalid chain, invalid anchor and invalid decision history block all repair;
- independent reviewer separation and exact audit-head binding are enforced;
- a separately approved supported repair path appends at most one event and verifies the chain/anchor;
- a crash after append but before case completion is handled idempotently;
- no historical record/event is rewritten or deleted and no raw values/secrets enter logs.

This checklist is a proposed rehearsal plan, not evidence that a rehearsal or repair test has been run. Record the owner decision and rehearsal evidence before changing the milestone gate.

## 11. Non-goals and permanent safety boundaries

- This procedure does not reconcile decision outcomes or implement #60 dependency review markers; those require a separate procedure/design.
- No simulated preference, agent action, conversion or report becomes an observed decision outcome through reconciliation.
- No simulation, calibration, backtest, forecast, study mutation, real data, credentials, drivers, network connector or external write-back is authorised.
- Do not edit `agora/sim/**`; do not alter NCC Park Square or E0_C0_D0.
- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- This procedure does not authorise production use, automatic repair or any external action.
