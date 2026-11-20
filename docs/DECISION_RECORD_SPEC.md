# Decision Record Specification — Rung 5 Design

**Status:** design only. Agora has no external write-back capability through this specification.

## Purpose

A decision record captures a human-reviewed choice and the evidence used to make it. It is immutable by version: corrections append a new version and preserve the prior record.

## Required record

Each record contains:

- `decision_id`, `version`, project scope, and lifecycle status (`draft`, `proposed`, `approved`, `rejected`, `superseded`);
- decision statement and alternatives considered;
- links to exact source snapshot/import IDs, ontology binding IDs/fingerprints, and simulation run IDs;
- evidence references, rationale, assumptions, uncertainty, and outcome measures;
- proposer, reviewer, approver, timestamps, and approval method;
- expiry/review date, supersession link, and immutable content fingerprint.

Approval is explicit and human controlled. A draft or simulation output never becomes an approved operational action implicitly. Approval transitions are append-only audit events and require the approver's permission for the project scope.

## Evidence and outcomes

Evidence links name exact immutable snapshots, bindings, and runs; they never use `latest`. Simulated results remain exploratory and are labelled as simulated. Outcome tracking records observed follow-up evidence separately, including its source and validation status. A changed or removed source marks dependent records for review.

## Actions and auditability

Decision records may describe a proposed action, but this repository has no write-back implementation. Any future action must have an idempotency key, explicit approval state, actor, target, parameters, timestamp, result, retry history, and audit event. Partial failure must be visible and recoverable; replay must be rejected or proven idempotent.

## Threat model for future write-back

| Threat | Required control | Proof before enablement |
|---|---|---|
| Confused deputy | Separate caller, approver, and target permissions; enforce at the service boundary | Cross-tenant and cross-role denial tests |
| Replay | One-time approval nonce and durable idempotency key | Replayed request produces no second side effect |
| Over-broad credentials | Least-privilege, scoped credentials held outside records | Scope audit and denied out-of-scope call |
| Stale approval | Bind approval to exact decision, snapshot, binding, run, and parameter fingerprint | Changed evidence or parameters invalidate approval |
| Partial failure | Transactional outbox/reconciliation and explicit pending state | Crash injection leaves auditable recovery state |
| Data poisoning | Provenance, validation, quarantine, and human review | Malformed/untrusted evidence cannot reach an approved action |
| Insider misuse | Separation of duties, audit integrity, and revocation | Unauthorized actor and tampered-log tests |

Rungs 2–4 remain simulation-only. Any real write-back requires a separate owner-approved design, threat model, consent/privacy review, implementation rung, and rollback plan.
