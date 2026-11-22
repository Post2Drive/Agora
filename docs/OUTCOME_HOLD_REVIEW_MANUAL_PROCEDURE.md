# Outcome Dependency — Manual Hold and Review Procedure

**Status:** Proposed manual hold/review procedure; requires owner approval and a synthetic rehearsal before it can count as a milestone control  
**Assessment base:** `main` at `90789ccfd866c038ce67753645b5e258134b9af3`  
**Specification:** `docs/OUTCOME_REVIEW_MARKERS_SPEC.md` (#60)  
**Related implementation:** observed outcome recording/review API (#53)  
**Scope:** Exact observed-outcome/source dependencies and local manual controls; no automated marker propagation

## 1. Purpose and current implementation boundary

Use this procedure when an observed outcome is disputed or corrected, or when its source evidence or linked decision version becomes unreliable, unavailable, withdrawn, erased or subject to retention expiry.

A hold means: **the exact affected object and any proven dependent artifact must not be relied on until an authorised reviewer records a disposition.** A hold is not a deletion, correction, approval, re-approval or execution command. Preserve original outcomes, decisions, reports and source history.

**This is not an implemented Agora marker system.** Main contains the #53 append-only outcome and review APIs, but no dependency-marker store, propagation worker or automatic downstream flagging. #60 is a specification. This document describes a proposed manual register and operator hold process; it does not create marker rows in Agora or imply automated propagation. Owner approval and a synthetic rehearsal are required before it can satisfy a milestone gate.

The procedure is for observed outcome evidence only. Simulated preferences, agent actions, conversions and reports are not observed outcomes and must never be promoted through this process.

## 2. Trigger events

Open a manual hold case for the exact root object when any of these triggers is confirmed:

| Trigger | Bounded reason code |
|---|---|
| An outcome review changes an outcome to disputed | `outcome_disputed` |
| A correction appends a new outcome that supersedes an earlier one | `outcome_corrected` |
| The source content hash no longer matches the recorded source reference | `source_hash_mismatch` |
| A source registry entry is revoked or withdrawn | `source_revoked` |
| A source is erased or reaches an approved retention-expiry event | `source_erased` / `retention_expired` |
| The exact approved decision version is superseded or linked evidence is invalidated | `decision_dependency_changed` |
| A previously reviewed outcome is disputed again due to later evidence | `outcome_reopened` |

A transition to reviewed does not automatically resolve an earlier hold. Resolution requires a separate disposition that identifies what was checked and which dependent artifacts remain valid.

## 3. Immediate hold and evidence preservation

1. Open a case in the owner-approved restricted manual hold register. The register is an operator record, not an Agora marker store.
2. Place a visible hold on the exact root outcome/source/decision reference in the controlled operator workflow. Until a supported application marker exists, do not describe this as an automatic system block; operators must prevent reliance manually.
3. Stop downstream use of the affected outcome and any dependent report/decision that is later proven to reference it. Do not publish, export, approve or base a new decision on held evidence.
4. Preserve immutable outcome ID, decision ID/version, source-registry ID, evidence ID, exact content hash and trigger event ID where available.
5. Preserve only the metadata and hashes permitted by the approved retention/erasure policy. Do not copy observed values, units, raw source content, personal data, credentials or free-text reviewer rationale into shared logs or audit events.
6. Do not edit or delete the original outcome, review, decision, report or source record to clear the hold. A correction is a new append-only outcome record.

If the trigger or root reference cannot be identified unambiguously, open a root-level `needs_review` case and do not infer affected objects.

## 4. Establish the exact root and dependency edges

For each case, record the exact root object and inspect only saved provenance references.

Supported exact references may include:

- outcome: decision ID, decision version and outcome ID;
- source evidence: source-registry ID, evidence ID and content hash;
- decision: exact decision ID/version/fingerprint;
- report: exact report artifact ID/hash and the outcome/source references embedded in its provenance;
- run or scenario-input package: exact run ID, input manifest/hash and source references, but only where an explicit edge to the affected outcome/evidence is stored.

Do not infer dependencies from project IDs, names, filenames, matching metric labels, timestamps, text search or other heuristics. Shared project membership is not a dependency edge.

If a source cannot be resolved to one exact immutable reference, open a root-level hold and require manual review. Do not propagate broadly based on guesswork.

## 5. Manual dependency traversal and hold scope

Use the trigger-specific procedure below and record the ordered dependency path for every affected object.

### 5.1 Outcome disputed or corrected

1. Open a hold on the exact outcome ID and decision version.
2. Traverse explicit stored dependency edges from that outcome.
3. Open a hold for each exact dependent decision/report artifact whose saved provenance references that outcome.
4. Record the path from the root outcome to each affected artifact.
5. Stop at objects with no explicit dependency edge; do not flag unrelated objects.

For a correction, the new outcome is a separate append-only record. Keep the superseded outcome and its history visible and held until reviewed. Do not rewrite the old value or silently transfer its status to the new outcome.

### 5.2 Source hash mismatch, revocation, erasure or retention expiry

1. Open a hold on the exact source-registry/evidence/hash reference.
2. Traverse only objects whose saved provenance cites that exact source hash.
3. Open holds for the exact affected outcomes, decisions, reports and run/input artifacts with explicit edges.
4. If the source reference is ambiguous, keep only the root-level hold and require review rather than guessing.
5. Apply the approved retention/erasure policy. Do not retain raw personal data indefinitely for the sake of a hold record; preserve only permitted opaque IDs, hashes or tombstone references.

### 5.3 Decision version superseded or evidence invalidated

1. Open a hold on the exact decision ID/version/fingerprint.
2. Identify only outcomes/reports that explicitly cite that version or its evidence.
3. Record the dependency path and hold those exact artifacts.
4. Do not rewrite an approved decision version. A new decision version or separate review requires its own authority.

A simulated preference, agent action, conversion or report metric may be linked as exploratory context only. It must never be treated as observed evidence.

## 6. Independent review and disposition

An authorised reviewer should:

1. Verify the root trigger against the exact source hash, outcome ID, decision version and event history.
2. Inspect each recorded dependency edge and confirm it against immutable provenance.
3. Determine whether the outcome is valid, disputed, corrected, withdrawn or unresolvable.
4. For each affected report, decide whether it is stale, must be reissued, or may be retained with a visible limitation.
5. For each affected decision, decide whether a new version or separate review is required. Never rewrite an approved version or silently change its evidence.
6. Record a bounded disposition, exact evidence reference and reviewer sign-off as a new append-only case-register event.
7. Leave unresolved or ambiguous dependencies open and continue the hold.

**Separation of duties:** the actor who recorded an outcome cannot review or resolve a hold for that outcome. A proposer/approver of a linked decision does not gain marker-resolution authority merely from that role. The reviewer must be independently authorised for the exact scope.

**Current identity limitation:** #92 retires the public role-string outcome record/review exports; public writes use `record_outcome_as()` / `review_outcome_as()` with Principal-derived actor identity, and #109 guards decision lifecycle transitions with a required anchored writer when `ANCHOR_REQUIRED=True`. The PDP and permission compatibility surface remains partly role-string based and the trusted-principal adapter remains synthetic-only. Do not treat a caller-supplied role string as trusted reviewer identity or use this manual procedure for production decisions. The owner must separately establish the authorised reviewer and approve the scope.

“Reviewed” is not equivalent to “valid.” The #53 outcome review state and this manual dependency hold are separate controls. A reviewed outcome does not automatically resolve an earlier hold.

## 7. Manual hold-register lifecycle

Maintain an append-only case history with bounded states:

- `open` — trigger recorded; exact root is under hold.
- `acknowledged` — authorised owner/reviewer accepts triage responsibility.
- `under_review` — exact source and dependency paths are being checked.
- `resolved` — reviewer records a disposition and evidence reference for the exact affected object.
- `superseded` — a new case/trigger replaces the current review scope; the earlier history remains visible.

Permitted manual transitions:

| Current state | Next state | Required evidence |
|---|---|---|
| open | acknowledged | Reviewer identity and acknowledgement |
| acknowledged | under_review | Reviewer identity and review-start record |
| under_review | resolved | Disposition code, exact evidence reference and reviewer sign-off |
| open or acknowledged | superseded | Exact replacement case ID and reason |
| resolved | open | Do not rewrite history; create a new case for a new trigger |

For every resolved object, state whether it remains valid, needs reissue, remains blocked or is superseded. Keep each dependent artifact's disposition separate; resolving the root does not automatically validate every dependent object.

## 8. Audit, partial failure and retention

The #60 specification requires allow-listed audit events for marker creation, acknowledgement, review start, resolution and supersession. Shared audit metadata must be limited to opaque IDs, event/operation type, actor subject ID, marker/case ID, bounded trigger/reason code, policy version and timestamp.

Never place observed values, units, notes, raw source content, personal data, credentials or free-text rationale in the shared audit chain.

Marker storage and audit storage may be separate stores; do not claim cross-store atomicity. If a future marker write or audit append partially succeeds, record a pending/blocked case and prevent reliance until the state is reconciled. The current mainline does not implement marker storage or its reconciliation. Do not write directly to SQLite or hand-edit audit JSONL.

A source erasure or retention-expiry trigger must follow the approved retention/erasure policy. Keep only opaque identifiers and hashes that are necessary and lawful; if an identifier itself must be erased, use only a permitted tombstone/reference.

## 9. Manual register fields

The restricted append-only register should record:

| Field | Purpose |
|---|---|
| case_id / trigger_event_id | Stable case and exact trigger |
| trigger_type / reason_code | Bounded trigger classification |
| root_ref | Exact root object type, ID/version and content hash |
| affected_ref | Exact affected object type, ID/version and content hash |
| dependency_path | Ordered explicit references from root to affected object |
| idempotency_key | Deterministic key for duplicate-trigger detection |
| severity / status | Bounded impact and lifecycle state; severity never changes permission |
| created_at / reviewed_at / resolved_at | Time-ordered history |
| source_evidence_ref | Exact source-registry ID, evidence ID and content hash |
| reviewer / disposition / evidence_ref | Independent review and exact basis for resolution |
| provenance_version | Version of the dependency/lineage contract used |

Do not include observed values, personal data, raw source content, secrets, credentials or unrestricted free text.

## 10. Synthetic rehearsal and acceptance checklist

Before this procedure is treated as an approved manual hold/review control, the owner must authorise a separate rehearsal using invented synthetic outcome/source references and temporary local stores only. Do not use existing studies, NCC Park Square, E0_C0_D0 or real data.

The rehearsal must demonstrate:

- a disputed outcome opens a hold for the exact outcome and decision version;
- a correction creates a separate case/reference and does not rewrite either outcome;
- a source hash mismatch flags only objects citing that exact hash;
- source revocation/erasure/retention expiry uses bounded reason codes and approved tombstone handling;
- explicit dependency traversal flags every known dependent object and no unrelated object;
- missing/ambiguous edges create only a root-level hold;
- duplicate trigger delivery is idempotent;
- the manual register is append-only;
- the outcome recorder cannot review their own outcome;
- a reviewed outcome does not automatically resolve a dependency hold;
- marker/audit partial failure remains visible and blocks reliance;
- no observed values or free-text rationale enter shared audit metadata;
- no simulated preference/action becomes an observed outcome.

This is a proposed rehearsal checklist, not evidence that tests or a rehearsal have been run. Record the owner decision and rehearsal evidence before changing the milestone gate.

## 11. Non-goals and permanent safety boundaries

- This procedure does not implement an outcome-marker store, propagation worker, automatic downstream flagging or reconciliation queue.
- #57's reconciliation specification covers decision lifecycle/approval audit gaps; it does not implement outcome-marker reconciliation.
- Opening or resolving a hold does not approve a replacement decision, publish a report, run a simulation, execute an action, erase source data or write to an external system.
- No simulation, calibration, backtest, forecast, study mutation, real data, credentials, drivers, network connector or external write-back is authorised.
- Do not edit `agora/sim/**`; do not alter NCC Park Square or E0_C0_D0.
- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- This procedure does not authorise production use or any external action.
