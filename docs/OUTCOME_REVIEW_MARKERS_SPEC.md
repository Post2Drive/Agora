# Outcome Dependency Review Markers Specification

**Status:** Partial implementation; the first append-only marker slice is merged in #116. This specification remains the broader target; retention/erasure triggers, automatic report/run edge registration, CLI and marker/audit reconciliation are not implemented. #102/#106 remain a separate read-only held-outcome list.
**Assessment base:** main at `30385885f16b3750a879ef7df25140fabe29c4ba` (22 November 2026)  
**Related implementation:** append-only decision outcomes/reviews (#53), read-only held-outcome listing (#102/#106), and first append-only dependency-marker slice (#116); assessment base main `30385885f16b3750a879ef7df25140fabe29c4ba`
**Related specification:** decision/audit reconciliation (#57), with read-only detector/hardening in #100/#104 and the merged missing-decision-audit repair API in #115 (not outcome/review reconciliation)

## 1. Purpose

Create durable, append-only review markers when an observed decision outcome is disputed or corrected, or when the evidence on which it depends becomes unreliable, unavailable or subject to erasure/retention action.

A marker means: **this exact object or dependent artifact must not be relied on until an authorised reviewer records a disposition.** It is a review signal, not a deletion, correction, approval, re-approval or execution command.

The marker system must preserve the original outcome and all historical decisions. It must not silently rewrite an outcome, decision, report, source record or audit event.

## 2. Current baseline and gap

Main includes the append-only outcome and review stores from PR #53, the read-only held-outcome list (#102/#106), and the first append-only dependency-marker implementation (#116). #116 adds marker, edge and event tables protected against UPDATE/DELETE; explicit-edge transitive, cycle-safe propagation; idempotent marker creation; Principal-gated edge registration and marker lifecycle; and blocking-marker lookup. Disputed, corrected and source-hash-mismatch triggers are supported. Resolution binds to a marker fingerprint, event-history head, bounded disposition and exact source evidence reference.

The implementation remains partial: retention/erasure triggers, automatic report/run edge registration, a CLI, and marker/audit reconciliation are not present. Edges are explicitly registered; absent edges produce root-level markers rather than heuristic propagation. The held-outcome CLI (#102/#106) remains separate and read-only. Decision lifecycle reconciliation (#100/#104/#119) and missing-event repair (#115) do not reconcile outcome/review or marker audit rows. Code review of #116 on main `30385885` found two lifecycle defects: `advance_marker_as()` commits its event before `_audit()`, so an audit append failure can leave a persisted `resolved(valid)` or `superseded` state that `blocking_markers()` no longer returns; and supersession checks only that a different marker exists, without binding it to the same decision/version/affected object or persisting a bounded reason. These must be fixed before operator reliance. This specification describes the broader target and must not imply that the remaining features exist.

## 3. Trigger events

Create a marker for the exact root object when one of these events occurs:

| Trigger | Required marker reason |
|---|---|
| An outcome is changed to disputed | outcome_disputed |
| A correction appends a new outcome that supersedes an earlier outcome | outcome_corrected |
| The source evidence hash no longer matches the recorded source reference | source_hash_mismatch |
| The source registry entry is revoked or the source is withdrawn | source_revoked |
| A source is erased or reaches an approved retention-expiry event | source_erased or retention_expired |
| The exact approved decision version is superseded or its linked evidence is invalidated | decision_dependency_changed |
| A previously reviewed outcome is disputed again because of later evidence | outcome_reopened |

A transition to reviewed does not automatically resolve an earlier marker. Resolution requires a separate review disposition that identifies what was checked and which dependent artifacts remain valid.

## 4. Dependency graph and propagation rules

### 4.1 Explicit edges only

Propagation follows exact, stored provenance edges, not names, fuzzy matching, timestamps or project-wide heuristics.

Supported object references may include:

- outcome: decision ID, decision version and outcome ID;
- source evidence: source-registry ID, evidence ID and content hash;
- decision: exact decision ID/version/fingerprint;
- report: exact report artifact ID/hash and the outcome/source references embedded in its provenance;
- run or scenario-input package: exact run ID, input manifest/hash and source references, but only when an explicit edge to the affected outcome/evidence exists.

A dependent report or decision is marked only if its saved provenance explicitly references the affected outcome or source evidence. Do not flag every report in a project merely because it shares a project ID. Do not infer dependencies from text, filenames or matching metric names.

### 4.2 Propagation scope

For an outcome-disputed or outcome-corrected trigger:

1. Open a marker on the exact outcome ID and decision version.
2. Traverse explicit dependency edges from that outcome.
3. Open markers for each exact dependent decision/report artifact that relied on that outcome.
4. Preserve the ordered dependency path so a reviewer can explain why each object was flagged.
5. Stop at objects with no explicit dependency edge. Do not mutate or delete them.

For source-hash mismatch, revocation, erasure or retention expiry, start from the exact source reference and traverse only objects that cite that source hash. If the source cannot be resolved unambiguously, open a root-level marker and require manual review rather than guessing.

A simulated preference, agent action, conversion or report metric is never promoted to an observed outcome by this traversal. Simulated material may be linked as exploratory context only.

## 5. Marker record

The marker is immutable. A proposed record contains:

| Field | Contract |
|---|---|
| marker_id | Opaque stable identifier. |
| trigger_event_id | Exact event that caused marker creation. |
| idempotency_key | Deterministic key derived from trigger event, trigger type and affected object reference. |
| trigger_type | One of the bounded trigger reasons in section 3. |
| root_ref | Exact root object type, ID/version and content hash where available. |
| affected_ref | Exact affected object type, ID/version and content hash where available. |
| dependency_path | Ordered list of stable object references from root to affected object. |
| reason_code | Bounded, non-free-text explanation. |
| severity | Bounded impact classification; severity never changes permissions. |
| created_at | Server-generated timezone-aware timestamp normalised to UTC. |
| provenance_version | Version of the dependency graph/lineage contract used to traverse. |
| source_evidence_ref | Exact source-registry ID, evidence ID and content hash, when applicable. |

Do not copy observed values, personal data, raw source content, free-text reviewer rationale, credentials or bearer tokens into the marker or shared audit event.

## 6. Append-only lifecycle

Store marker creation and every subsequent action as append-only events. The current marker state is derived from its event history; no UPDATE or DELETE is permitted.

Proposed states:

- open — marker created; affected object must be treated as under review.
- acknowledged — an authorised owner/reviewer has accepted responsibility for triage.
- under_review — evidence and dependency path are being checked.
- resolved — a reviewer has recorded a bounded disposition and evidence reference.
- superseded — a newer marker or corrected dependency record replaces the current review scope; the earlier marker remains visible.

Permitted transitions:

| Current state | Next state | Required evidence |
|---|---|---|
| open | acknowledged | Reviewer identity and acknowledgement event |
| acknowledged | under_review | Reviewer identity and review-start event |
| under_review | resolved | Disposition code, exact evidence reference and reviewer sign-off |
| open or acknowledged | superseded | Exact replacement marker ID for the same decision ID/version and affected type/ref, plus a bounded persisted reason code |
| resolved | open | Not allowed by rewriting history; create a new marker for a new trigger |

A resolution must state whether the affected object is still valid, needs reissue, remains blocked, or is superseded. “Reviewed” is not equivalent to “valid.” A corrected outcome is a new outcome record; it does not erase or mutate the disputed outcome.

## 7. Reviewer actions and downstream handling

An authorised reviewer should:

1. Verify the root trigger against the exact source hash, outcome ID, decision version and event history.
2. Inspect the recorded dependency path and confirm each edge against immutable provenance.
3. Decide whether the outcome is valid, disputed, corrected, withdrawn or unresolvable.
4. For each affected report, decide whether it must be labelled stale, reissued or retained with a visible limitation.
5. For each affected decision, decide whether the decision needs a new version or a separate review. Never rewrite an approved version or silently change its evidence.
6. Record the disposition, evidence reference and reason code as a new marker event.
7. Leave unresolved or ambiguous dependencies open and block reliance on them.

Opening a marker must not automatically approve a replacement decision, publish a report, run a simulation, execute an action, erase source data or write to an external system. Any such action requires its own authority and approval.

## 8. Permission and separation of duties

- The actor who recorded an outcome cannot review or resolve a marker for that same outcome.
- A reviewer must hold a trusted reviewer permission for the exact tenant/project scope.
- A person who proposed or approved the linked decision must not gain marker-resolution authority merely from that role.
- Marker resolution must bind to the exact marker fingerprint, affected object reference and current event-history head.
- Missing, expired, untrusted or out-of-scope principal denies.
- #111 restricts role-string PDP/permission imports to the internal allowlist and makes the legacy role-string approval authorizer private; #113 requires `BoundPolicy` for protected shared policy enforcement. This closes the M1 synthetic Principal-bound policy gate, but `SyntheticFixtureAdapter` remains synthetic-only; no OIDC or production identity provider is claimed. Caller-supplied role strings are not trusted authority.

## 9. Audit and reconciliation

Emit allow-listed audit events for marker creation, acknowledgement, review start, resolution and supersession. Include only event ID/type, actor subject ID, operation, exact opaque resource IDs, marker ID, trigger/reason code, policy version and timestamp.

Never include observed_value, unit, notes, raw source content, personal data, credentials or free-text rationale in the shared audit chain.

Marker storage and the audit chain may be separate SQLite stores. Do not claim a cross-store atomic transaction. Required invariant: if marker persistence succeeds but its audit append fails, or vice versa, the durable state must remain visibly pending and blocking until reconciliation proves both sides; use a stable idempotency key so retry cannot create duplicate markers. **Current #116 gap:** `advance_marker_as()` commits the lifecycle event before calling `_audit()`. If the audit append fails, a `resolved` marker with disposition `valid` or a `superseded` marker remains persisted, while `blocking_markers()` excludes those states. Change to audit-before-commit or a durable pending/outbox state that remains blocking; never clear a hold on an unaudited transition. **Current supersession gap:** the replacement is only checked for existence/different ID. Require matching `decision_id`, `decision_version`, `affected_type` and `affected_ref`, plus a bounded reason persisted in the event.

The reconciliation specification and #100/#104/#119 detector scope themselves to decision lifecycle/approval audit gaps; #115 repairs only missing decision lifecycle events through an API. #102/#106 list held outcome/review states from the decision store but do not reconcile those rows against the audit chain. Marker/outcome reconciliation requires an explicit extension or separate approved design. No marker queue, worker or automatic repair is claimed here.

## 10. Retention and erasure

A source erasure or retention-expiry event creates a marker for affected dependencies before any downstream object is represented as valid. Preserve only the opaque identifiers and hashes that are necessary and lawful for review. If the identifier itself must be erased, the implementation must follow the approved retention/erasure policy and record only a permitted tombstone/reference.

A marker is not a reason to retain raw personal data indefinitely. Backup expiry, access controls and the retention/erasure design in docs/RETENTION_ERASURE_DESIGN.md continue to apply.

## 11. Acceptance tests

1. A disputed outcome creates one marker for the exact outcome ID and decision version.
2. A correction creates a new marker linked to the superseded outcome; neither outcome row is modified.
3. A source hash mismatch opens markers only for objects that reference that exact hash.
4. Source revocation, erasure and retention expiry produce bounded reason codes and exact dependency references.
5. Explicit dependency traversal flags every known dependent report/decision and no unrelated object.
6. Missing or ambiguous dependency edges do not trigger heuristic propagation; they produce a root-level open marker.
7. Duplicate delivery of the same trigger is idempotent.
8. Marker event history is append-only; UPDATE/DELETE attempts fail.
9. A reviewer cannot resolve a marker for an outcome they recorded.
10. Missing, expired, untrusted and cross-scope principals are denied.
11. Resolution requires an exact evidence reference and marker fingerprint.
12. A reviewed outcome does not automatically resolve a disputed marker.
13. Marker creation never changes decision status, outcome value, report bytes or source data.
14. Audit events contain only allow-listed metadata and never include values or free text.
15. Marker/audit partial failure is visible and cannot be silently treated as complete.
16. Retention/erasure removes or tombstones only what the approved policy permits.
17. No simulated preference/action can become an observed outcome through marker propagation.
18. No marker action enables VALIDATED_PREDICTION_ENABLED or external write-back.
19. If the anchored audit append fails during acknowledge, resolve-valid or supersede, the prior blocking state remains effective and no unaudited non-blocking state is persisted.
20. Supersession rejects replacement markers for another decision/version/affected object and requires a bounded persisted reason code.

## 12. Scratch mutation proofs (never committed)

- Remove exact outcome/source matching; the unrelated-object exclusion test must fail.
- Remove dependency-path validation; the missing-edge test must fail.
- Remove idempotency enforcement; duplicate trigger delivery must create a detectable duplicate and fail the test.
- Permit marker UPDATE/DELETE; the append-only test must fail.
- Permit the recorder to resolve their own outcome marker; the separation-of-duties test must fail.
- Treat reviewed as automatic resolution; the unresolved-dispute test must fail.
- Add observed values or rationale text to audit payloads; the allow-list/redaction test must fail.
- Swallow marker/audit partial failure; the reconciliation-state test must fail.
- Commit `resolved(valid)` or `superseded` before the required audit append; the audit-failure test must fail.
- Remove same-decision/version/affected-object validation or omit the bounded supersession reason; the scope/reason test must fail.

## 13. Implementation and rollout gates

The first implementation slice is merged in #116 and was included in Claude's explicit M1 confirmation. Before operator reliance, fix the two merged-code review findings above. Remaining specification work requires a separately owner-approved M2 task: retention/erasure triggers, automatic report/run edge registration, CLI, marker/audit reconciliation and operator evidence. Use synthetic fixtures and temporary local stores only; no network access or external services.

No simulation, calibration, backtest, forecast, study mutation, real data, credentials, network connector, external write-back or change to agora/sim/** is authorised by this document. Keep VALIDATED_PREDICTION_ENABLED=False.
