# Audit Anchor Wiring Plan

**Status:** Stage A/D writer plumbing (#71), lifecycle/outcome append wiring (#74/#75), protected Principal-bound policy (#113), role-string importer allowlist/private approval authorizer (#111), missing-decision-event repair API (#115), first append-only outcome dependency-marker slice (#116), read-only audit timeline/verify (#107), sidecar-verified reconciliation (#119/#122), local backup/verify/restore CLI (#120) and backup hardening (#127) are merged. #122 closes the primary marker audit-order/supersession and reconcile verify/classify race findings; a marker-store commit failure after successful audit append can still leave an orphan audit event. Reconcile's lock helper may create a `.lock` metadata file and its concurrency test uses a fixed sleep. #127 hardens backup/restore but project/backup/target root symlink rejection and a shared source-pair snapshot lock/head check remain follow-ups. #125's checked-in fixture/start component is merged; independent manifest pinning, fixture symlink/version checks and clean-install proof remain open. #130 is an open run-record loader/workdir PR, not mainline evidence. This is a wiring plan, not deployment or rehearsal approval.
**Assessment base:** `main` at `e64df1e5b8060d1684ed71ddee1412a5c664b566` (22 November 2026).
**Specification:** `docs/AUDIT_ANCHOR_SPEC.md`, merged PR #52  
**Implementation evidence:** PR #63 (local-sidecar primitive), #71 (writer factory and policy/data-boundary wiring), #74 (lifecycle/outcome append wiring) and #75 (structural `AuditAppender` protocol). Exact-head Actions runs #71 (`44926109220`), #74 (`44928837108`) and #75 (`44929428177`) passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.

## 1. Purpose and non-claims

Wire the local anchored audit writer into every existing shared audit append boundary without changing the audit event allow-list, weakening fail-closed policy behaviour, or pretending that separate SQLite/file writes are one transaction.

The local sidecar anchor is a crash/accidental-truncation control, not an independently administered security anchor. PR #63 reports `trust_level: local_sidecar` and explicitly demonstrates that replacing both the chain and anchor with a mutually consistent older pair is not detected. Do not call this external anchoring, production-grade tamper resistance, or protection against an administrator who can rewrite both stores.

This plan does not implement the wiring, authorise deployment, add network access, or authorise any simulation or external write-back.

## 2. Verified current mainline inventory

The following inventory was checked against main at `e64df1e5b8060d1684ed71ddee1412a5c664b566`, after #127's backup hardening merge. Claude's exact 09:05 IST log entry confirms M1. The owner approved local synthetic M2. #123/#125 provide only a partial run record; #130 is open and unmerged; no M2 completion or rehearsal is claimed.

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

The shared `_audit()` helper calls `audit.append(event)` after the decision transition has been stored. If the append fails, it raises `ApprovalTransitionError`; it does not roll back the already committed decision transition. PR #75 introduces the structural `AuditAppender` protocol, so `AnchoredAuditChain` satisfies the declared writer contract. The Python parameter remains optional, but #109 adds an entry guard to `propose()`, `reject()`, `expire()` and `supersede()`: when production-default `ANCHOR_REQUIRED=True`, `require_anchored(audit)` runs before `_current()` and before any decision-store mutation, so `None` and plain writers are refused. `approve_as()` already has the corresponding guard; legacy `approve()` remains disabled except through the test-only `LEGACY_APPROVE_ENABLED` flag. The separate decision/audit stores remain non-atomic: if the audit append fails after the decision transition is stored, the transition remains committed and must not be described as fully audited.

### 2.3 Decision outcomes and reviews

`agora/decisions/outcomes.py` has private `_record_outcome()` / `_review_outcome()` helpers with optional audit. PR #92 removes the public role-string names; public callers use `record_outcome_as()` / `review_outcome_as()` and the Principal wrappers default to `require_anchored=True`.

The outcome or review row is committed to the decision store before the shared audit append. If the append fails, `OutcomeError` is raised while the outcome/review row remains stored. If `audit=None`, the shared audit append is skipped. This is another non-atomic boundary; do not report the operation as fully audited after an anchor failure. PR #75 changes the type contract to `AuditAppender`; it does not make the writer mandatory.

### 2.4 Policy-denial audit and data-boundary callers

`agora/policy_enforcement.py::enforce_policy()` has no caller-controlled `require_policy` override. #99 requires an anchored writer for protected denials. #113 adds `PRINCIPAL_BOUND_REQUIRED=True` and accepts `BoundPolicy` from `principal_policy()` while rejecting raw callables; each call re-evaluates the bound Principal. #113 completes the protected Principal-bound callback gate; `BoundPolicy` rechecks the Principal at each invocation. Identity remains synthetic-only. Preserve fail-closed denial behaviour and policy-before-source-read ordering.

The shared `enforce_policy()` boundary is called by:

- `agora/tabular.py::ingest_csv()` for `import`
- `agora/ontology/binding.py::materialize_instances()` for `binding`
- `agora/scenario_inputs.py::build_scenario_input()` for `simulation_input`

These callers invoke policy enforcement before reading source bytes or opening the snapshot database. Preserve that ordering. The policy-denial path is the only production-code constructor of `AuditChainStore` found by repository code search; decision and outcome APIs receive their audit object from their caller.

In production, `POLICY_REQUIRED=True`, so `policy=None` is denied; the no-op branch is reachable only when the test-only protection flag is relaxed. Do not allow a protected operation to become authorised because `policy=None` was passed.

### 2.5 Outcome-marker lifecycle audit boundary

PR #116 adds append-only marker/edge/event storage. PR #122 now appends the audit event before committing the marker transition, so an audit append failure rolls the marker change back; supersession must match decision ID/version and affected type/ref and persist a bounded reason. Residual cross-store gap: if the audit append succeeds but the later marker-store commit fails, the audit event remains without the marker transition. Add a commit-failure test and a durable pending/outbox or reconciliation contract before claiming cross-store consistency.


### 2.6 Backup/restore anchor-consistency boundary (#120/#127)

PR #120 adds local synthetic `agora backup`, `agora backup verify` and `agora restore`; #127 adds the run-record synthetic gate, symlink/unsafe-path refusal, manifest schema validation, copied chain/anchor re-verification and post-copy restore hashing. #127 exact-head Actions run `44994798420` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. The merged code still lacks an explicit `lstat` rejection for project/backup/restore-target root symlinks before marker/manifest reads or destination writes, and it does not hold one shared anchor lock across source verification and the audit DB/anchor pair snapshot.

Post-merge review found the following follow-ups: project/backup/restore-target root symlinks are not explicitly rejected before reads/writes; backup does not hold the same `AnchorStore.lock()` across source verification and audit DB/anchor pair snapshot or prove the same sequence/head; recursive source enumeration rejects in-tree symlinks but the run-record `data_class=synthetic` gate is not a separately pinned fixture allowlist; and malformed root path handling needs stable refusal tests. #127 adds manifest schema validation and post-copy restored-file hashes. Add deterministic root-symlink, source-pair concurrency/head-equality, allowlist and post-copy mutation tests before operator reliance.

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
- Enforce the anchored-writer requirement at each protected lifecycle entry point before state reads or writes. #109 adds this guard to `propose()`, `reject()`, `expire()` and `supersede()`; retain tests for missing/plain writers and no state change. Tests may inject a fake appender only to prove bounded failure paths.
- Preserve the current failure semantics: the decision transition may already be committed when chain/anchor append fails. Surface that partial state explicitly; do not attempt to roll back or rewrite the decision record.
- Do not claim that the decision store and audit chain are one transaction. PR #100 adds a read-only decision lifecycle/approval detector; #104 validates immutable source transition metadata, expected audit operation and exact resource IDs, and closes connections on partial open. #119 verifies the sidecar before classification; #122 holds the same anchor lock across verification and classification. The lock helper opens its sidecar with `a+b`, so a missing lock file may be created during reconciliation; the #122 concurrency test uses a fixed sleep rather than a deterministic handshake. Marker audit-before-commit prevents a failed audit append from clearing a hold, but a marker DB commit failure after successful audit append still needs reconciliation semantics.

**Acceptance:** every protected lifecycle transition produces an anchored event; missing writer is denied in protected mode; anchor failure raises and identifies the committed transition/event for reconciliation; proposer/reviewer/approver separation and exact-version checks remain unchanged.

### Stage C — outcome recording and review

Pass the same anchored writer through `record_outcome_as()` and `review_outcome_as()`; do not expose the private role-string helpers as public routes.

- Keep the observed-only provenance, approved decision-version, exact source hash, measure allow-list, append-only correction and reviewer-separation checks unchanged.
- Preserve the current order: the outcome/review row is committed before the shared audit append. If anchoring fails, return a typed partial-failure signal; the row remains stored and must not be described as fully audited.
- Keep observed values, units, notes and reviewer rationale out of audit events.
- Do not imply that decision/audit reconciliation #100 covers outcome rows; its detector scope is decision lifecycle/approval events only. #102/#106 list held outcome/review states read-only, with #106 failing closed on connection-open errors; they do not create dependency markers or reconcile outcome rows against the audit chain.

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

- **PR #63/#71/#74/#75/#88/#89/#94/#96/#97/#99/#100/#102/#104/#106:** local-sidecar primitive, writer factory, policy/data-boundary wiring, lifecycle/outcome append boundaries, structural `AuditAppender`, guided pilot, default-on defaults, CLI import isolation, public opt-out removal, test-only legacy approval, anchored policy-denial enforcement, read-only reconciliation detector plus #104 source-integrity/connection hardening, and read-only held-outcome list are merged. Neither #100/#104 nor #102 adds anchor validation, queue/repair, or outcome/audit reconciliation.
- **Storage-spec follow-up:** confirm explicit permissions, atomicity/durability and cross-process serialization against #52 before treating the local implementation as complete.
- **Reconciliation:** #100/#104 implement a read-only detector for decision lifecycle/approval transitions. It verifies the hash chain and classifies matched/missing/conflict/source-invalid/orphan cases; #104 adds immutable source metadata checks, exact audit operation/resource-ID checks and partial-open connection cleanup. No anchor check, queue, repair or outcome/review coverage exists. #102's held-outcome list is separate.
- **Principal migration:** #96 removes public `require_anchored=False` kwargs, #97 removes the legacy approval env switch, and #99 closes direct policy-helper bypasses. Role-string PDP/permission compatibility APIs remain; the synthetic fixture adapter is not production authentication.
- **Owner gate:** green CI is not review or merge approval. No PR is marked ready, requested for review, approved or merged by this document.

## 9. Safety boundaries

- No changes to `agora/sim/**`; scenario-input-to-engine wiring remains separately blocked pending Claude's written approval and separate owner approval.
- No simulations, calibration, backtests, forecasts, study mutations or changes to existing study folders.
- No NCC Park Square or E0_C0_D0 changes.
- No real data, personal/customer records, credentials, drivers, network connectors or external write-back.
- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- This plan is not permission to begin implementation; each code slice requires its own scoped approval and draft PR.

## 10. Current mainline status after PR #125, #124, #123 and #122

**Stage A — writer factory/lifecycle: IMPLEMENTED.** `open_anchored_audit(chain_path, anchor_path, chain_id)` uses explicit paths and chain ID, does not bootstrap, rejects same-file and unclean chain/anchor pairs, returns an anchored writer and closes the underlying chain. Missing/invalid anchor state fails closed.

**Stage D — policy-denial and data-boundary threading: DIRECT HELPER HARDENING IMPLEMENTED.** #96 removes `require_policy` kwargs from `ingest_csv()`, `materialize_instances()` and `build_scenario_input()`. #97 removes the unanchored fallback when `audit=None`; #99 removes the direct policy override and validates supplied writers with `require_anchored()`. Keep the early-denial tests and anchored-writer requirement.

**Stage B — decision lifecycle: PROTECTED ENTRY-POINT GUARDS IMPLEMENTED.** #96 removes the `require_anchored` kwarg from `approve_as()`. #97 removes the `AGORA_TEST_ONLY_LEGACY_APPROVE` env switch; legacy `approve()` is disabled by default and enabled only by the test-only `LEGACY_APPROVE_ENABLED` module flag. #109 adds `require_anchored(audit)` at the start of `propose()`, `reject()`, `expire()` and `supersede()` when `ANCHOR_REQUIRED=True`, before decision state can be read or mutated. Their signatures still annotate audit as optional, but `None` and plain writers fail closed on the protected path.

**Stage C — outcome recording/review: PUBLIC PRINCIPAL ROUTES ONLY.** #92 removes public role-string `record_outcome()` / `review_outcome()` exports; #96 removes public `require_anchored` opt-out kwargs from `record_outcome_as()` / `review_outcome_as()`. Private helpers and audit-optional internals remain implementation details, not public governed routes.

**Guided pilot integration (#88/#125): IMPLEMENTED AS A LOCAL SYNTHETIC COMMAND.** `agora pilot --workdir <new-empty-directory>` remains the legacy M1 path; #125 adds `agora pilot list` and `agora pilot start --fixture <id> --workdir <dir>` using the checked-in synthetic fixture. Per-file hashes are checked before stores open, but the manifest digest is not independently pinned, fixture directory/manifest/payload paths can follow symlinks, empty fixture versions are accepted, and clean-checkout installation is unproven. #130 proposes a non-empty-workdir guard and strict run-record loader but remains open, not main.

**Exact-head CI evidence:** #74 run `44928837108`, #75 `44929428177`, #79 `44931670540`, #80 `44934473818`, #82 `44937162200`, #84 `44939812441`, #88 `44945307064`, #89 `44948055801`, #92 `44950576945`, #94 `44955653075`, #96 `44956724553`, #97 `44958568446`, #99 `44960946006`, #100 `44963254416`, #102 `44965953082`, #104 `44968039923`, #106 `44970435296`, #107 `44972864246`, #109 `44975437439`, #122 `44989188092`, #123 `44990673166`, #124 `44991628960` and #125 `44993280261` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.

**Read-only audit CLI (#107): IMPLEMENTED.** `agora audit timeline --decisions <db> --audit <db> --decision-id <id>` verifies the hash chain before listing one decision's stored transitions and related audit events. `agora audit verify --audit <db> --anchor <file> --chain-id <id>` compares the chain with the local anchor and prints a plain-language verdict plus the `local_sidecar` trust limitation. Timeline does not compare the anchor itself; run verify separately. Both commands are read-only and do not repair stores.

**Remaining acceptance gates:** close the marker/audit cross-store commit-failure case with durable pending/outbox or reconciliation semantics; finish #125 fixture manifest pinning, symlink/version/workdir validation and clean-install proof; complete the run-record provenance envelope, strict schema/hash validation and failure-atomic publication (the #130 loader/workdir PR is still open and does not complete the spec); add root-symlink and source-pair lock/head-equality tests for #127 backup/restore; then make the operator runbook executable by tests and record the separately approved synthetic rehearsal. Unanchored-tail recovery remains blocked.
## 11. Permanent safety boundaries

- No changes to `agora/sim/**`; scenario-input-to-engine wiring remains separately blocked pending Claude's written approval and separate owner approval.
- No simulations, calibration, backtests, forecasts, study mutations or changes to existing study folders.
- No real data, credentials, network connectors or external write-back.
- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Green CI is not review or merge approval; this document does not authorise deployment or rehearsal.
