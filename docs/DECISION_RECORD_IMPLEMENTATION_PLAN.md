# Decision Record Implementation Plan — Rung 5

**Status:** design only. This plan breaks `docs/DECISION_RECORD_SPEC.md` into
three reviewable implementation PRs. It does not add code, external write-back,
credentials, network connectors, or real-world actions.

The current repository has validation approval and audit primitives under
`agora/validation/`, but no decision-record store or action executor. The plan
keeps those concerns separate and preserves the existing exploratory-only
boundary.

## PR 1 — Schema and immutable record versions

**Goal:** define and persist a decision record as an append-only, versioned
object with exact evidence references and a content fingerprint.

**Proposed files**

- `agora/decisions/schema.py` — typed record/envelope validation, allowed
  lifecycle states, canonical serialization, and fingerprint computation.
- `agora/decisions/store.py` — project-local append-only persistence; reject
  replacement of an existing `(decision_id, version)` and preserve prior
  versions.
- `tests/test_decision_record_schema.py` and
  `tests/test_decision_record_store.py` — schema, fingerprint, versioning, and
  evidence-link tests.

**Exit tests**

- required fields, lifecycle values, timestamps, and project scope are
  validated fail closed;
- evidence references require exact import IDs, binding fingerprints, and run
  IDs and reject `latest`;
- identical content has a stable fingerprint;
- corrections append a new version and never mutate the previous version;
- malformed or unknown fields cannot be persisted;
- simulated evidence remains labelled exploratory.

**Mutation proofs**

- remove the immutable-version conflict check: the duplicate-version test must
  fail;
- omit evidence references from the fingerprint: the changed-evidence test must
  fail.

## PR 2 — Human approval state machine

**Goal:** add explicit, permission-checked lifecycle transitions without
  implying that an approved record performs an action.

**Proposed files**

- `agora/decisions/approval.py` — transition rules for `draft → proposed →
  approved|rejected`, supersession, expiry, reviewer/approver separation, and
  append-only approval events.
- `agora/decisions/permissions.py` — project-scope and separation-of-duties
  checks, using the existing validation approval conventions where applicable.
- `tests/test_decision_approval.py` — valid/invalid transitions, expiry,
  reviewer/approver identity, supersession, and audit events.

**Exit tests**

- drafts and simulated output cannot become operational approvals implicitly;
- approval requires an authorized approver distinct from the proposer/reviewer
  where required by policy;
- stale, expired, scope-mismatched, or evidence-mismatched approvals fail
  closed;
- every transition appends an audit event with actor, method, timestamp, and
  decision fingerprint;
- approval does not call a connector or mutate an external system.

**Mutation proofs**

- remove the exact-scope/fingerprint comparison: the stale-approval test must
  fail;
- allow a proposer to approve their own record: the separation-of-duties test
  must fail.

## PR 3 — Outcome tracking and review linkage

**Goal:** record observed follow-up outcomes separately from simulated evidence
and mark dependent decisions for review when a source changes or is removed.

**Proposed files**

- `agora/decisions/outcomes.py` — append-only outcome observations with source
  registry ID, snapshot/import ID, validation status, measurement window, and
  linkage to the decision version.
- `agora/decisions/review.py` — dependency invalidation/review markers when
  source, binding, run, or approval evidence changes.
- `tests/test_decision_outcomes.py` — source lineage, simulated/observed
  separation, invalidation, and retention tests.

**Exit tests**

- observed outcomes require their own exact source and validation metadata;
- simulated preferences/actions cannot be stored as observed sales or demand;
- a changed or removed source marks dependent decision versions for review;
- outcome corrections append a new observation rather than rewriting history;
- reports can distinguish exploratory simulation evidence from observed
  follow-up evidence.

**Mutation proofs**

- remove the source-dependency invalidation: the changed-source test must fail;
- permit a simulated event as an observed outcome without a validation marker:
  the evidence-separation test must fail.

## Sequencing and gates

PR 1 must merge before PR 2; PR 2 must merge before PR 3. Each PR is docs/code
scoped to its listed files, has focused and full-suite tests, and records exact
head, CI jobs, and mutation diffs. No PR enables validated prediction or
external write-back. A separate owner-approved threat-model and pilot gate is
required before any action executor is designed.
