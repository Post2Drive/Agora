# Audit Anchor Wiring Plan

**Status:** Stage A and D writer plumbing implemented by #71; Stage B/C append wiring and opt-in protected gates implemented by #74; #80 makes `approve_as()` principal-native. Universal protected mode remains incomplete because policy/anchor requirements are still optional and legacy paths remain. This document is a wiring plan, not deployment or rehearsal approval.  
**Assessment base:** `main` at `25231d68b6f9d5684b76b6204265cd225cc29449` (21 November 2026).  
**Specification:** `docs/AUDIT_ANCHOR_SPEC.md`, merged PR #52  
**Implementation evidence:** PR #63 (local-sidecar primitive), #71 (writer factory and policy/data-boundary wiring), #74 (lifecycle/outcome append wiring) and #75 (structural `AuditAppender` protocol). Exact-head Actions runs #71 (`44926109220`), #74 (`44928837108`) and #75 (`44929428177`) passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.

## 1. Purpose and non-claims

Wire the local anchored audit writer into every existing shared audit append boundary without changing the audit event allow-list, weakening fail-closed policy behaviour, or pretending that separate SQLite/file writes are one transaction.

The local sidecar anchor is a crash/accidental-truncation control, not an independently administered security anchor. PR #63 reports `trust_level: local_sidecar` and explicitly demonstrates that replacing both the chain and anchor with a mutually consistent older pair is not detected. Do not call this external anchoring, production-grade tamper resistance, or protection against an administrator who can rewrite both stores.

This plan does not implement the wiring, authorise deployment, add network access, or authorise any simulation or external write-back.

## 2. Verified current mainline inventory

The following inventory was checked against current main at `25231d68b6f9d5684b76b6204265cd225cc29449`, after PRs #78, #79 and #80 merged.

### 2.1 Audit primitives

- `agora/audit_chain.py` defines `AuditChainStore(path)`, `append(event)`, `verify()` and `close()`. The store redacts to an allow-list, uses an append-only SQLite table, verifies the full hash chain and rejects replayed event IDs.
- Merged PR #63 provides `AnchorStore`, `AnchoredAuditChain`, `bootstrap_anchor()` and `verify_anchored()`; the writer exposes `append()`, `verify()` and `close()`. Merged PR #71 adds `open_anchored_audit(chain_path, anchor_path, chain_id)`, which uses explicit paths, does not bootstrap, rejects same-file/unclean pairs and closes the chain on exit.
- `AnchorStore` appends JSONL records, flushes and calls `os.fsync`; the implementation uses owner-only creation permissions. Compare the exact implementation against every #52 storage-hardening requirement before deployment; passing CI does not prove all operational permission, atomicity, backup or restore requirements.
- The wrapper checks the existing anchor before appending, appends to the chain, reads/verifies the resulting head, then advances the anchor. If the anchor write fails, it raises `AnchorWriteError` and leaves the chain event in place. The next protected append sees an unanchored tail and is refused.
- `AnchoredAuditChain` serializes verify → chain append → anchor advance with a cross-process sidecar lock. The known Linux lock-removal mutation gap remains; the earlier mutation proof did not detect removal of the lock.

### 2.2 Decision lifecycle

`agora/decisions/approval.py` accepts an optional `audit: AuditAppender | None` in:

- `propose()`
- `approve()`
- `approve_as()`
- `reject()`
- `expire()`
- `supersede()`

The shared `_audit()` helper calls `audit.append(event)` after the decision transition has been stored. If the append fails, it raises `ApprovalTransitionError`; it does not roll back the already committed decision transition. If `audit=None`, the shared audit append is skipped. PR #75 introduces the structural `AuditAppender` protocol, so `AnchoredAuditChain` satisfies the declared writer contract. The parameter remains optional; this is not a protected-mode requirement.

### 2.3 Decision outcomes and reviews

`agora/decisions/outcomes.py` accepts an optional `audit: AuditAppender | None` in:

- `record_outcome()`
- `review_outcome()`

The outcome or review row is committed to the decision store before the shared audit append. If the append fails, `OutcomeError` is raised while the outcome/review row remains stored. If `audit=None`, the shared audit append is skipped. This is another non-atomic boundary; do not report the operation as fully audited after an anchor failure. PR #75 changes the type contract to `AuditAppender`; it does not make the writer mandatory.

### 2.4 Policy-denial audit and data-boundary callers

`agora/policy_enforcement.py::enforce_policy()` now accepts optional `audit=`. When a writer is supplied, denial events are appended through that writer and there is no unanchored fallback for that call. `open_anchored_audit()` supplies the configured writer. The data-boundary callers `ingest_csv()`, `materialize_instances()` and `build_scenario_input()` now accept/thread `audit=`. #78 adds `principal_policy()` and a missing-policy denial when `require_policy=True`; #79 threads the flag through the three data-boundary APIs. However, `require_policy=False` remains the default, the callback is still `(operation, resource)`, `audit=None` falls back to an unanchored project-local chain, and no protected path requires the anchored writer by default.

The shared `enforce_policy()` boundary is called by:

- `agora/tabular.py::ingest_csv()` for `import`
- `agora/ontology/binding.py::materialize_instances()` for `binding`
- `agora/scenario_inputs.py::build_scenario_input()` for `simulation_input`

These callers invoke policy enforcement before reading source bytes or opening the snapshot database. Preserve that ordering. The policy-denial path is the only production-code constructor of `AuditChainStore` found by repository code search; decision and outcome APIs receive their audit object from their caller.

`policy=None` is currently a no-op in `enforce_policy()`. That is a separate authorization-contract issue covered by the principal-migration work; anchor wiring must not imply that an optional policy hook is safe for a protected operation.

## 3. Target integration contract

1. **One explicit writer per project/security boundary.** Construct the chain and anchor from explicit configuration: chain database path, separate anchor file/location, and stable `chain_id`. Do not infer the anchor path from the current working directory or silently create a new anchor during ordinary application startup.
2. **Structural interface.** Introduce a narrow audit-appender protocol (at minimum `append(event)`) so decision/outcome code can accept `AnchoredAuditChain` without lying about its type. Keep ownership of the underlying `AuditChainStore` in a factory/context manager that closes it reliably.
3. **Separate storage.** The anchor must not be the chain database or a table in it. Restrict both paths to the service identity. If both files remain on the same host/admin trust boundary, continue to report `local_sidecar`.
4. **Required writer on protected paths.** Production-capable decision, outcome and policy-denial paths must receive the configured anchored writer. Keep `None` only for explicitly ungoverned/test contexts; do not silently fall back from anchored to unanchored writes.
5. **Synchronous append semantics.** An operation is not reported as fully audited until both the chain event and its anchor checkpoint are durable. Preserve the event if anchoring fails; surface a typed error and an actionable pending/reconciliation state. Include safe event ID/sequence metadata so the persisted event can be located without logging values or free text.
6. **Serialise the pair.** Protect chain-append plus anchor-advance as one writer critical section across threads/processes. A SQLite lock alone does not serialize the separate JSONL append. Define lock acquisition, timeout, crash recovery and lock cleanup.
7. **No weakening of redaction.** Continue using `AuditChainStore.append()` and its allow-list. Never copy outcome values, units, notes, source contents, credentials, principal claims or reviewer rationale into the shared chain.

## 4. Wiring sequence by call site

### Stage A — writer factory and lifecycle

- Add an explicit factory/configuration boundary that opens `AuditChainStore`, constructs `AnchorStore` from the configured anchor path and stable chain ID, and returns the anchored writer.
- Add reliable close/context-manager behaviour for the wrapper or factory. Do not leak SQLite handles when policy-denial writers are opened repeatedly.
- Add read-only startup/health verification. A missing anchor after initial provisioning is an error, not permission to auto-bootstrap.
- Define one serialized append path for all writers that target the same chain/anchor pair.
- Keep the local trust label explicit in health/readiness output.

**Exit evidence:** factory configuration is explicit; wrong/same-file paths, missing anchor, invalid chain ID, invalid history and lock failures fail closed; no implicit bootstrap occurs.

### Stage B — decision lifecycle

Pass the anchored writer through the existing `audit` parameter for `propose`, `approve`, `approve_as`, `reject`, `expire` and `supersede`.

- Replace the concrete `AuditChainStore | None` annotation with the structural appender type.
- Preserve each existing event type, event ID, resource IDs, reason code and policy version.
- Make the production service/harness require an anchored writer for protected lifecycle transitions; tests may inject a fake appender to prove failure paths.
- Preserve the current failure semantics: the decision transition may already be committed when chain/anchor append fails. Surface that partial state explicitly; do not attempt to roll back or rewrite the decision record.
- Do not claim that the decision store and audit chain are one transaction. The decision/audit reconciliation design in merged PR #57 is still specification only; its detector/queue/repair implementation is separate work.

**Acceptance:** every protected lifecycle transition produces an anchored event; missing writer is denied in protected mode; anchor failure raises and identifies the committed transition/event for reconciliation; proposer/reviewer/approver separation and exact-version checks remain unchanged.

### Stage C — outcome recording and review

Pass the same anchored writer through `record_outcome()` and `review_outcome()`.

- Keep the observed-only provenance, approved decision-version, exact source hash, measure allow-list, append-only correction and reviewer-separation checks unchanged.
- Preserve the current order: the outcome/review row is committed before the shared audit append. If anchoring fails, return a typed partial-failure signal; the row remains stored and must not be described as fully audited.
- Keep observed values, units, notes and reviewer rationale out of audit events.
- Do not imply that decision/audit reconciliation #57 already covers outcome rows; its initial scope is decision lifecycle/approval events. Outcome dependency review markers are a separate design/implementation gate.

**Acceptance:** recorded/reviewed/disputed/correction events are anchored; audit/anchor failure is visible; the stored row remains immutable; no simulated value is promoted to observed evidence.

### Stage D — policy-denial path and data boundaries

Change `enforce_policy()` to receive an explicit anchored audit appender or a configured writer factory rather than constructing an unanchored `AuditChainStore` internally.

- Preserve the existing project-local chain path unless the owner-approved deployment configuration specifies another explicit path.
- Supply the anchor path and stable chain ID from explicit project/service configuration; do not derive a silent default from the process working directory.
- Ensure the denial writer is closed by its owner/factory after the append attempt.
- Keep the `policy_denied` event redacted and allow-listed.
- Preserve the pre-read order in `ingest_csv()`, `materialize_instances()` and `build_scenario_input()`: policy evaluation and denial auditing must finish before source bytes or snapshot databases are read.
- If the denial event cannot be anchored, raise `PolicyEnforcementError`; do not continue the protected read or downgrade to a plain chain append.
- Keep the separate principal-migration requirement visible: a protected operation must not become authorised merely because `policy=None` was passed.

**Acceptance:** a denied import, binding or scenario-input request creates a verified anchored denial event; an anchor failure leaves the protected source unread and is surfaced; no call site can silently create a new unanchored writer.

### Stage E — operational runbook and controlled rehearsal

- Update the pilot runbook only after the implementation and its operator interface are merged.
- Document explicit configuration, service-account file permissions, bootstrap, startup verification, backup/restore, outage/lock behaviour and recovery.
- Demonstrate the local-sidecar limitation in the operator-facing output.
- Do not run a rehearsal or simulation as part of this documentation plan. A synthetic rehearsal requires its own explicit owner approval and must use temporary local stores only.

## 5. Bootstrap procedure

Bootstrap is a one-time, explicit maintenance operation for a newly provisioned chain/anchor pair, not an application-startup convenience.

1. Confirm the configured chain path, separate anchor path, stable chain ID, service identity and filesystem permissions.
2. Stop writers to that chain. Open the existing chain read-only for inspection or under a maintenance lock.
3. Run the full `AuditChainStore.verify()`. If invalid, stop; do not create an anchor for a broken chain.
4. Confirm this is the initial provisioning event and that no prior anchor history is expected. If an anchor previously existed and is now missing/invalid, treat that as an incident, not first-time bootstrap.
5. With an authorised maintenance operator identity, call the explicit `bootstrap_anchor(..., performed_by=...)` operation. The implementation must refuse to overwrite an existing history.
6. Run `verify_anchored()` and require `anchored_verified` at the exact current sequence/head.
7. Record the chain ID, paths, bootstrap operator, UTC time, sequence, head hash, trust level and verification result in the protected operational record. Do not include secrets or event payloads.
8. Resume writers only after the verification result is clean.

Never bootstrap automatically on missing/corrupt anchor history. Never reset an existing anchor to the current chain head to make a mismatch disappear.

## 6. Runtime failure and recovery matrix

| Signal | What is already persisted | Required response |
|---|---|---|
| `AnchorRequiredError` / pre-append status is not clean | No new event from this attempted append; prior chain/anchor state is suspect or incomplete | Stop protected writes. Preserve both stores. Verify and investigate; do not append around the problem. |
| `AnchorWriteError` / `unanchored_tail` | The new event is in the chain; its new anchor checkpoint is not durable | Stop subsequent protected writes. Preserve the event and both stores. Locate the exact event ID/sequence, inspect the full chain and prior anchor, and use only a separately approved recovery procedure. Do not delete the event or retry the business operation blindly. |
| `truncation_detected` | Chain ends before the latest retained anchor checkpoint | Treat as rollback/truncation. Preserve evidence; restore a verified chain+anchor pair or investigate against an independent checkpoint. Never move the anchor backward. |
| `anchor_mismatch` | Chain hash at the anchored sequence differs from the checkpoint | Stop protected writes and preserve both files. Treat as integrity incident; no automatic repair. |
| `anchor_invalid` | Anchor missing, malformed, wrong-chain or broken history | If this is not confirmed first-time provisioning, treat as an incident. Do not auto-bootstrap or overwrite. |
| `chain_integrity_failure` | The audit chain itself fails verification | Stop all protected writes. Preserve evidence and use a reviewed restore/investigation procedure. Never anchor the broken head. |
| `ApprovalTransitionError` after audit failure | Decision transition is already committed; shared event may or may not have reached the chain | Report the exact decision/version as stored but not fully audited; retain the safe event correlation and reconcile under the separate approved procedure. |
| `OutcomeError` after audit failure | Outcome/review row is already committed; shared event may or may not have reached the chain | Report the exact outcome/review as stored but not fully audited; do not rewrite it. Reconcile under a separately approved procedure. |
| `PolicyEnforcementError` while auditing a denial | Policy denied; denial event could not be confirmed anchored | Keep the protected read/action denied. Preserve the chain state and error evidence; never continue because audit failed. |

### Recovery rules

- An unanchored tail may result from a crash after chain append and before anchor durability. It is not permission to repeat the original operation or to delete the event.
- A future recovery command must be explicit, append-only, idempotent and bound to the exact prior anchor, current chain head, event IDs and independent operator approval. The merged #63/#71 implementation does not provide that recovery command.
- If chain and anchor must be restored from backup, restore them as a coordinated pair and verify the pair before resuming. A local pair alone cannot prove that both were not rolled back together.
- If the anchor is missing after prior use, do not call bootstrap as a repair. Escalate for evidence-preserving investigation.
- Keep external anchoring out of scope until a separate threat review, authentication/key-management plan, outage policy and owner approval exist.

## 7. Implementation acceptance and mutation evidence

Use synthetic events and temporary directories only.

1. Every protected approval/lifecycle and outcome/review append uses the anchored writer.
2. Every policy-denial append uses the same explicit anchored writer configuration.
3. No production-capable call site silently falls back to `AuditChainStore` alone or `audit=None`.
4. The wrapper/factory closes the underlying SQLite connection on success and every failure path.
5. Multiple concurrent writers cannot produce a missing, duplicate or backward anchor sequence.
6. Crash between chain append and anchor durability yields `unanchored_tail` and blocks subsequent protected appends.
7. Anchor write failure preserves the chain event and returns safe event correlation metadata.
8. Missing/invalid anchor never triggers automatic bootstrap.
9. Truncation, mismatch and chain-integrity failure remain distinct fail-closed statuses.
10. Denial auditing completes before any source bytes or snapshot database are read.
11. Decision/outcome state remains append-only when the separate audit append fails; the partial state is reported accurately.
12. File permissions, atomicity/durability, backup/restore and the local-sidecar trust limitation match the #52 specification.
13. No audit event contains observed values, notes, source content, credentials or unrestricted free text.
14. No network, external write-back, real data or credentials are used.

Mutation proofs must fail if the implementation skips pre-append verification, allows an unanchored tail, advances the anchor backward, swallows an anchor write failure, auto-bootstraps a missing anchor, races concurrent writers, closes the store incorrectly, audits after a protected source read, or bypasses the anchored writer on any protected call site.

## 8. Current blockers and ownership

- **PR #63/#71/#74:** the local-sidecar primitive, writer factory, policy/data-boundary threading and lifecycle/outcome append boundaries are merged. Exact-head CI runs 201, 211 and 221 passed all four matrix jobs. `require_anchored=True` remains opt-in on the three Principal wrappers.
- **Storage-spec follow-up:** confirm explicit permissions, atomicity/durability and cross-process serialization against #52 before treating the local implementation as complete.
- **Reconciliation:** merged PR #57 is a specification only. No detector, queue, worker or repair command is implemented.
- **Principal migration:** #80 makes `approve_as()` principal-native; public role-string `approve()` remains callable and outcome wrappers still delegate to legacy role-string APIs. #79's `require_policy` is opt-in/default-false; no policy or anchor gate is enabled by default everywhere.
- **Owner gate:** green CI is not review or merge approval. No PR is marked ready, requested for review, approved or merged by this document.

## 9. Safety boundaries

- No changes to `agora/sim/**`; scenario-input-to-engine wiring remains separately blocked pending Claude's written approval and separate owner approval.
- No simulations, calibration, backtests, forecasts, study mutations or changes to existing study folders.
- No NCC Park Square or E0_C0_D0 changes.
- No real data, personal/customer records, credentials, drivers, network connectors or external write-back.
- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- This plan is not permission to begin implementation; each code slice requires its own scoped approval and draft PR.


## 10. Current mainline status after PR #80

**Stage A — writer factory/lifecycle: IMPLEMENTED.** `open_anchored_audit(chain_path, anchor_path, chain_id)` uses explicit paths and chain ID, does not bootstrap, rejects same-file and unclean chain/anchor pairs, returns an anchored writer and closes the underlying chain. Missing/invalid anchor state fails closed.

**Stage D — policy-denial and data-boundary threading: IMPLEMENTED, BUT OPTIONAL.** `enforce_policy(..., audit=)` accepts an injected writer. When supplied, denial events use it; when `audit=None`, the implementation creates a legacy unanchored project-local `AuditChainStore`. #78 adds a principal-bound `principal_policy()` and `require_policy=True` missing-policy denial; #79 threads `require_policy` through `ingest_csv()`, `materialize_instances()` and `build_scenario_input()`. All data-boundary defaults remain `False`, and the callback still receives only `(operation, resource)`. Policy and anchor are not default-on.

**Stage B — decision lifecycle: PARTIALLY IMPLEMENTED (#74/#80).** Lifecycle methods accept optional audit appenders and the anchor gate remains opt-in. #80 makes `approve_as()` principal-native through `authorize_decision_approval_principal()`, but the public role-string `approve()` remains callable. `approve_as(..., require_anchored=True)` fails closed before state mutation without an `AnchoredAuditChain`; its default remains `False`.

**Stage C — outcome recording/review: PARTIALLY IMPLEMENTED (#70/#74).** `record_outcome_as()` and `review_outcome_as()` derive roles from Principal but still delegate to legacy role-string functions. Their `require_anchored=True` gates are opt-in; the underlying outcome APIs still accept optional audit appenders. No default protected outcome path is established.

**Exact-head CI evidence:** #74 run 221 (`44928837108`) and #75 run 224 (`44929428177`) passed all four matrix jobs; #79 run 236 (`44931670540`) and #80 run 239 (`44934473818`) also passed all four jobs. #79 had one initial Windows 3.11 SQLite lock failure; a rerun passed. These CI results do not establish operational backup/restore or close the known Linux lock-removal mutation gap.

**Remaining acceptance gates:** require the same configured anchored writer on every protected path by default; remove/gate legacy optional-audit paths; migrate outcome writes to Principal at the actual store boundary; keep denial before protected source reads; add precise typed-error assertions, cross-process lock mutation/concurrency proofs and backup/restore/tamper drills. Preserve the committed-but-unanchored partial-failure state and the explicit `local_sidecar` trust limitation. Reconciliation (#57) remains a specification only.

## 11. Permanent safety boundaries

- No changes to `agora/sim/**`; scenario-input-to-engine wiring remains separately blocked pending Claude's written approval and separate owner approval.
- No simulations, calibration, backtests, forecasts, study mutations or changes to existing study folders.
- No real data, credentials, network connectors or external write-back.
- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Green CI is not review or merge approval; this document does not authorise deployment or rehearsal.
