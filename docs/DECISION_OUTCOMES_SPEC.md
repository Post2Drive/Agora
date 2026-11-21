# Decision Outcomes and Review — Rung 5 Specification (Block 23)

**Status:** design specification only. This document does not implement outcome storage, change decision records, run simulations, validate prediction claims, or authorise external actions/write-back.

## 1. Purpose and boundary

Record observed follow-up evidence against one exact approved decision-record version, then allow a distinct reviewer to mark that observation reviewed or disputed. Outcomes are separate append-only evidence; they never modify the decision record, its fingerprint, its approval, or its original evidence references.

The system must preserve a strict distinction between:

- **observed outcomes:** measurements collected from a declared source and observation window, with source provenance and validation status; and
- **simulated outputs:** preferences, choices, actions, conversions, synthetic agent responses and report metrics. These remain exploratory and must never be promoted to observed sales, demand, uptake or validated prediction merely by storing them as an outcome.

This specification adds no action executor and no external write-back.

## 2. Outcome identity and append-only record

Add an append-only `decision_outcomes` table in the decision store. The logical key is:

`(decision_id, decision_version, outcome_id)`

A record is immutable after insertion. Corrections append a new `outcome_id` and reference the prior outcome using `supersedes_outcome_id`; no UPDATE/DELETE of the original observation is permitted.

Required fields:

| Field | Contract |
|---|---|
| `decision_id` | Exact existing decision identifier. |
| `decision_version` | Positive integer identifying the approved immutable decision version. |
| `outcome_id` | Opaque, unique identifier generated once for this observation. |
| `measure` | Exact measure name matching one entry in the approved decision version's `outcome_measures`; no free-form new measure. |
| `observed_value` | Typed JSON scalar (string, finite number or boolean); reject null, NaN, infinity, arrays and objects. Units/denominator are declared separately. |
| `unit` | Non-empty bounded text describing the unit or denominator (for example, `people`, `percent of eligible cohort`, or `INR`). |
| `observed_at` | RFC3339 timestamp with timezone; normalise to UTC for comparisons. |
| `measurement_window` | Explicit start/end RFC3339 timestamps, with start not after end and `observed_at` inside or at the declared end. |
| `source_ref` | Structured exact evidence reference: source-registry ID plus immutable import/snapshot ID or external evidence ID and content hash. Never accept `latest`, a mutable URL alone, or an unversioned source label. |
| `validation_status` | Explicit enum such as `unverified`, `source_verified`, `independently_checked`; never infer verification from the fact that a record exists. |
| `recorder` | Authenticated principal ID, not a caller-supplied display name. |
| `recorded_at` | Server-generated RFC3339 timestamp. |
| `notes` | Optional bounded text (maximum 500 characters). Exclude from the shared audit chain; do not use for personal/sensitive values or as a substitute for structured evidence. |
| `supersedes_outcome_id` | Optional exact prior outcome ID for an append-only correction. Must reference the same decision/version/measure and cannot create a cycle. |

The referenced decision version must exist and have status `approved`. A later decision version does not rewrite the outcome's original linkage. If the decision is superseded or its evidence is marked for review, the outcome remains immutable and is flagged for review rather than silently reattached.

## 3. Outcome lifecycle and review

Outcome status is separate from decision status:

- `recorded`: observation appended; validation status remains explicit.
- `reviewed`: an authorised reviewer has checked the source, measure, window and value.
- `disputed`: reviewer identifies a source, measurement, scope or interpretation problem.

Each review is an append-only event with outcome ID, prior state, new state, reviewer principal, timestamp, rationale code, and exact evidence reference. Free-text rationale is stored in the decision store under the normal access controls and is not copied to the shared audit chain.

Permitted transitions:

| Current state | Next state | Authority |
|---|---|---|
| `recorded` | `reviewed` | Reviewer distinct from recorder |
| `recorded` | `disputed` | Reviewer distinct from recorder |
| `disputed` | `reviewed` | Reviewer after new evidence or correction |
| `reviewed` | `disputed` | Reviewer when a later integrity/source issue is discovered |
| Any state | New corrected observation | Append a new outcome ID; never rewrite the existing row |

A disputed outcome is not deleted. A correction does not erase the earlier observation; it creates a linked successor and preserves the full history.

## 4. Permission and policy boundary

Add `decision_outcome` to the central policy operation vocabulary only as part of a separately tested implementation. The policy decision must bind:

- authenticated subject ID and trusted role/attributes;
- exact project/tenant scope and decision ID/version;
- operation (`decision_outcome`);
- source sensitivity and target sensitivity;
- declared purpose and retention where personal/sensitive data is involved.

Proposed role separation:

- `operator`: may record an outcome for an in-scope approved decision;
- `reviewer`: may review or dispute an outcome, but may not record and review their own observation;
- `approver`: no implicit outcome-recording authority merely because the actor can approve decisions.

These are proposed least-privilege rules, not a claim about the current policy matrix. The current PDP does not yet include `decision_outcome`; its operation set and role matrix must be extended and tested. A caller-supplied role is not trusted identity. Until an identity adapter exists, implementation must document the adapter boundary and must not treat arbitrary caller input as proof of role.

Fail closed on unknown roles/operations, missing scope, cross-scope access, missing sensitivity, sensitivity downgrade, missing purpose/retention where required, non-approved decision version, invalid measure, and source reference drift.

## 5. Evidence lineage and simulated/observed separation

- Each outcome must point to one exact approved decision version and an exact immutable source reference.
- A source reference must resolve to a registered evidence object with a stable identifier and content hash; the outcome must not fetch a mutable remote resource.
- Simulation run IDs may be linked as explanatory exploratory context, but a simulated action or preference cannot populate `observed_value` as an observed outcome.
- If an outcome is derived from a simulation, reject it as observed evidence regardless of whether the report contains a number or the decision is approved.
- The outcome schema must carry a provenance class such as `observed` or `exploratory_simulation`; only `observed` can enter this table, and it requires source verification metadata.
- A source change, deletion, retention/erasure event, or changed validation state creates an append-only dependency review marker. It does not rewrite the outcome.

## 6. Audit events

Emit shared audit-chain events for:

- `decision_outcome_recorded`
- `decision_outcome_reviewed`
- `decision_outcome_disputed`
- `decision_outcome_correction_appended`

Audit payloads are metadata only. Use the audit chain's allow-listed fields and put opaque decision/version/outcome/source identifiers in `resource_ids`. Do not include `observed_value`, `unit`, `notes`, raw source content, personal data, reviewer rationale or free text in the shared audit chain. The event should include an event ID, event type, actor ID, operation, allow/deny decision, policy version, safe reason code and timestamp.

The decision store and `AuditChainStore` are separate SQLite stores; an append to one is not atomic with a write to the other. The implementation must expose pending/reconciliation state and retry safely by stable event ID. It must not claim a single cross-store transaction. A future transactional outbox or a shared database boundary may be considered in a separate design.

Denied attempts must emit `decision_outcome_denied` with only allow-listed identifiers and reason code, then raise a permission error. If the denial cannot be durably audited, fail closed and surface the audit failure.

## 7. Error cases

Reject at least:

- decision does not exist, version is not approved, or version fingerprint does not match;
- measure is not an exact member of `outcome_measures`;
- missing/invalid/non-finite observed value, unit, timestamp or measurement window;
- source reference uses `latest`, is incomplete, cannot be resolved, or its content hash has changed;
- source provenance marks the evidence as simulation-only or exploratory;
- caller is outside project scope or lacks the operation permission;
- recorder attempts to review their own observation;
- correction references a different decision/version/measure or forms a cycle;
- duplicate outcome ID, attempted update/delete, or stale lifecycle transition;
- audit-chain append fails after the outcome write and reconciliation is not possible.

Diagnostics must identify the failing contract field or stable error code, not disclose raw source values.

## 8. Acceptance tests

1. Append one outcome only for an exact approved decision version.
2. Reject draft, proposed, rejected, superseded, missing and stale decision versions.
3. Accept only a measure that exactly matches the decision's `outcome_measures`.
4. Validate typed scalar values, units, RFC3339 timestamps and measurement windows.
5. Require exact source reference, source hash and observed-evidence classification.
6. Reject `latest`, changed source hashes and simulation-only evidence.
7. Enforce project scope, role/operation policy, sensitivity, purpose and retention.
8. Prove recorder cannot review/dispute their own outcome.
9. Prove reviewer can mark recorded as reviewed/disputed and append review history.
10. Prove correction appends a new outcome and preserves the prior row byte-for-byte.
11. Prove update/delete triggers reject mutation and duplicate IDs are rejected.
12. Prove audit events contain only allow-listed metadata and no values/notes/free text.
13. Prove denial is audited; audit failure is visible and recoverable without claiming cross-store atomicity.
14. Prove simulated preferences/actions cannot be accepted as observed outcomes.
15. Prove source changes/erasure create dependency review markers without rewriting outcomes.
16. Prove no path enables `VALIDATED_PREDICTION_ENABLED` or external write-back.

## 9. Scratch mutation proofs (never committed)

- Remove the approved-status check: the non-approved-decision test must fail.
- Remove the exact measure-membership check: the unknown-measure test must fail.
- Permit a simulation-only source: the simulated-versus-observed separation test must fail.
- Remove the source-hash comparison: the source-drift test must fail.
- Permit recorder self-review: the separation-of-duties test must fail.
- Remove append-only protection: the immutable-correction test must fail.
- Add `observed_value` or `notes` to the audit payload: the allow-list/redaction test must fail.
- Swallow audit-chain failure: the audit-failure/reconciliation test must fail.

## 10. Implementation and rollout gates

This is a specification for a later implementation PR. It does not authorise code changes.

1. Claude implements from this specification only after the document is merged and the owner confirms the scope.
2. Implementation is isolated to decision-outcome store/lifecycle/policy/audit modules and their focused tests; no changes to `agora/sim/**`.
3. The implementation must preserve append-only decision records and existing approval history.
4. Synthetic fixtures only; no real customer data or external systems.
5. Four CI jobs must pass on the exact final head; mutation proofs are run in a clean scratch checkout and never committed.
6. The owner explicitly says `review` before any review/merge decision.

**No implementation or write-back is authorised by this specification.**
