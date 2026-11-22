# M2 Plain-Language Audit and Anchor Verification — Planning Specification

**Status:** Planning only; no new command or operator rehearsal is implemented here.
**Current merged components:** `agora audit timeline` and `agora audit verify` (#107); read-only decision detector plus sidecar-anchor check `agora reconcile` (#100/#104/#119); API-only missing-event repair (#115); and shared anchor locking across reconcile verification/classification (#122).
**Current limitation:** #115's missing-decision-event repair is merged as a Python API only; it is not a CLI and does not cover outcome/review rows.

## 1. Operator-facing outcome

An operator should be able to answer, without interpreting hashes:
- Is the audit chain internally valid?
- Does the configured local sidecar anchor match the chain?
- What is the last verified sequence?
- Is reconciliation intact, missing an event, conflicting, source-invalid or blocked?
- Is a repair permitted, refused or unavailable?

Every output must distinguish a clean chain from a clean chain-plus-anchor pair. Never describe `local_sidecar` as independent or external anchoring.

## 2. Existing commands (read-only)

```bash
agora audit timeline --decisions <db> --audit <db> --decision-id <id>
agora audit verify --audit <db> --anchor <file> --chain-id <id>
agora reconcile --decisions <db> --audit <db> --anchor <file> --chain-id <id>
agora outcomes held --decisions <db>
```

Timeline checks the hash chain and lists one decision's transitions/events; run verify separately to compare the local sidecar. Reconcile (#100/#104/#119) verifies the sidecar anchor read-only and classifies only when `anchored_verified`; its CLI requires `--anchor` and `--chain-id`. Held-outcome listing remains separate. #115's repair API appends only missing decision lifecycle events under approver, clean-anchor and exact-head checks; it does not reconcile outcome audit rows.

## 3. Proposed plain-language summary

A future operator summary should present:
- **Chain:** valid / invalid / unreadable.
- **Anchor:** matches / mismatch / missing / malformed / wrong chain ID / not checked.
- **Last verified point:** sequence and shortened opaque hash only.
- **Reconciliation:** intact / gaps found / blocked, with stable reason codes.
- **Next safe action:** inspect, stop writes, preserve stores, or seek authorised review.

Do not expose event payloads, personal values, free-text notes, secrets or credentials.

## 4. Repair boundary

#115 is merged as `agora.reconcile_repair.apply_repairs(decisions_db, audit, *, principal, project_id, expected_audit_head)`. It requires an approver Principal, anchored writer, clean anchor and exact audit head; it repairs missing decision audit events only. It has no CLI. Conflicts, invalid sources, orphan events, broken chains and unanchored tails block. Outcome/review reconciliation is separate.

Review note: #122 closes the original verify/classify TOCTOU by holding the same `AnchorStore.lock()` across both phases. The lock helper opens the sidecar with `a+b`, so a missing `.lock` file may be created during an otherwise read-only reconcile call; clarify whether that metadata side effect is permitted or preserve strict no-filesystem-write semantics. The concurrency test uses a fixed `time.sleep(0.5)` rather than a deterministic handshake proving the writer reached the lock attempt; strengthen the test so removing the lock reliably fails.

## 5. Acceptance evidence

- CLI integration tests assert human-readable summaries for each stable status.
- Golden output tests ensure no sensitive payloads are printed.
- Subprocess tests exercise commands from the runbook.
- Tampered, truncated, missing-anchor and wrong-chain fixtures fail closed.
- Operator wording clearly explains the `local_sidecar` trust limitation and coordinated-rollback blind spot.

## 6. Non-goals

No automatic bootstrap, silent repair, chain reset, rollback, external anchoring, network access, real data or write-back.
