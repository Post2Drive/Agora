# Ontology action proposals (O2, first four slices)

**Status:** library only (`agora/ontology/actions.py`, `agora/ontology/approvals.py`, `agora/ontology/outcomes.py`). No CLI, web or service uses it. It proposes, records an approval or rejection, ends an approval by withdrawal or by one admission for simulation, and records the outcome the admitter reports for that admission; it does not simulate, queue, execute or write back. The O2 guardrail in [ONTOLOGY_CAPABILITY_TARGET.md](ONTOLOGY_CAPABILITY_TARGET.md) (no general action executor yet) still applies.

## What a proposal binds

`propose_action` returns canonical JSON (`format: agora.ontology.action_proposal/v1`) and its SHA-256 digest:

- project, pack fingerprint, and the exact ActionType ID, version and fingerprint;
- the actor and target objects: exact type, version, import and record key, plus binding and schema fingerprints, source file hash, source row ID, and a digest of the property values read at proposal time;
- parameters, which must name exactly the ActionType inputs;
- at least one cited source record (import, file hash, row), without duplicates;
- the reason, the highest classification involved, and the proposer and policy version from the policy decision;
- the declared preconditions, effects and permissions, with `preconditions_evaluated: false` and `executed: false`.

There is no timestamp, so the same request by the same proposer under the same policy version gives the same digest. A later step can use that to detect a repeat; this module does not.

The digest of each successful proposal is appended to the audit chain (`ontology_action_proposed`). The proposal itself is not stored.

## Authority

- `ontology_action_propose` is a separate policy operation. Under the central roles only `operator` has it.
- The first decision names the requested pack, action, objects and cited imports, and comes before any lookup. The second is taken at the highest of the two objects' stored classification and the input properties' classification, before any source row is read.
- The proposer comes from the policy decision, never from the request. A decision without a known subject is refused.
- Reading the objects also needs the `ontology_read` and `binding` decisions the object store already requires.

## Parameters

Every declared input must be a property ID of the pack; an ActionType with any other input cannot be proposed. `integer` takes an integer within 64 bits, `boolean` a boolean, `decimal` plain decimal text (no floats or exponents), `date` `YYYY-MM-DD`, `timestamp` ISO-8601 with a zone (stored in UTC). Text is at most 4096 characters. `identifier` and `enum` must be non-empty without surrounding spaces. Nullability and allowed values are enforced. `structured_object` is not supported. Errors name the property, never the value.

Decimal text is kept as written, so `10.5` and `10.50` give different digests.

A parameter is a requested value. It is **not** compared with the actor's or target's current value.

## Rechecking

`recheck_action_proposal(store, document, expected_digest, ...)` needs read authority, not proposal authority. It refuses unless the document has the expected digest and rebuilding it from the pack and sources gives the same content. The expected digest must come from somewhere the document's holder cannot rewrite.

## Approval (O2, second slice)

`decide_action_proposal(store, document, digest, outcome, reason, ...)` lets an approver approve or reject one proposal, once.

- New policy operation `ontology_action_decide`. Under the central roles only `approver` has it; `operator`, who proposes, does not. It is decided before the audit chain is read and at the proposal's own classification.
- The chain must hold an `ontology_action_proposed` event for the digest from the identity and policy version the document names. This authenticates `proposed_by` against the anchored chain, so the digest no longer has to be retained separately.
- The deciding identity must be principal-bound and different from the proposer.
- The decision is appended as `ontology_action_approved` or `ontology_action_rejected` under the event ID `ontology-action-decision-<digest>`. The chain refuses a duplicate ID, so a digest gets one decision; a rejection cannot be followed by an approval. The chain keeps no free text, so the reason is recorded only as `reason_hash`.
- `verify_approved_action(store, document, digest, ...)` is the check to run before a later step acts. It needs read authority and re-reads the objects and sources (`recheck_action_proposal`), then requires the proposal event, exactly one decision event that is an approval, an approver who is not the proposer, and an approval that has not been withdrawn, used or expired (below). A changed pack, object or source row makes it fail, which is how a stale approval is caught.
- The decision step does not re-read the objects: the approver decides on the document they were shown, and staleness is caught at verification.

## Expiry, withdrawal and admission (O2, third slice)

- **Expiry.** An approval lasts `APPROVAL_LIFETIME_SECONDS` (24 hours) from the time the chain writer recorded the decision. `max_age_seconds` on `verify_approved_action` and `admit_approved_action` can shorten it for that call, never lengthen it. A decision without a readable time with a zone, or dated more than 30 seconds ahead of the checking clock, is refused. This also applies to approvals recorded before this change. An expired digest cannot be approved again: the same request gives the same digest, so a new approval needs a changed proposal (for example a new reason).
- **Withdrawal.** `withdraw_approval(store, document, digest, reason, ...)` needs `ontology_action_decide` and an identity other than the proposer; it need not be the original approver. It does not re-read the objects, works on an expired approval, and is permanent. It cannot undo an admission.
- **Admission.** `admit_approved_action(store, document, digest, ...)` uses a live approval once. New policy operation `ontology_action_admit`: under the central roles only `operator` has it. It is decided before anything is read. It also needs read authority, runs `verify_approved_action`, and refuses the approver's own identity (the proposer may admit). The expiry is checked again while the chain's write lock is held. A caller must not start a simulation unless it returns.
- **One ending.** Withdrawal (`ontology_action_withdrawn`) and admission (`ontology_action_admitted`) share the event ID `ontology-action-final-<digest>`, so the chain's unique event ID allows one of them, once, including when two writers race.
- If the ending is appended but its anchor cannot be written, the call raises, the approval is spent, and the anchored writer refuses further appends until reconciled.

An admission records that one simulation may start. Nothing here starts or retries one (its reported outcome can be recorded, below): a failure after admission leaves the approval spent.

## Simulation outcome (O2, fourth slice)

`record_simulation_outcome(store, document, digest, status, result_digest, ...)` records, once, how the simulation allowed by an admission ended. It runs nothing: this is the admitter's report.

- New policy operation `ontology_action_outcome`: under the central roles only `operator` has it. It is decided before the chain is read, at the proposal's own classification.
- `status` is `succeeded` or `failed`. `result_digest` is the `sha256:` digest of the caller's result or failure report. The caller keeps the content; the chain holds only the digest.
- The admission is read from the chain, not taken from the dictionary `admit_approved_action` returned. There must be a recorded proposal, one approval from someone else, and exactly one ending, which is a well-formed admission by someone other than the approver. The recording identity must be that admitter.
- The event is `ontology_action_simulation_succeeded` or `ontology_action_simulation_failed` under the event ID `ontology-action-outcome-<digest>`, so an admission has one outcome and it cannot be corrected.
- The objects and sources are not re-read, and the approval's age is not checked again. A later change or expiry therefore cannot hide an outcome.
- If the event is appended but its anchor cannot be written, the call raises and the anchored writer refuses further appends until reconciled.
- If the admitter cannot record (lost role, lost identity, crash with no report), the admission stays without an outcome. That shows only that none was recorded, not that nothing ran.

## Limits

- An outcome is not evidence that a simulation ran, that the digest belongs to a real result, or that nothing else was done with the admission.
- `recheck_action_proposal` alone does not authenticate `proposed_by` and `policy_version`; `decide_action_proposal` and `verify_approved_action` check them against the anchored chain. No signature: the chain is a local file, so someone who can rewrite it and its anchor, or run code in the service, can forge a proposal or an approval. A valid digest alone is not an approval.
- **Row checks on read are unkeyed.** Object reads recompute the stored row ID, so a source row edited under its pinned row ID is refused both before and after a proposal. Under the protected defaults these reads also require each import's [ingest record](ONTOLOGY_DATA_BINDING.md#ingest-record-in-the-audit-chain) in the anchored chain. Neither check is a signature or authenticates the snapshot against the original file; see [the snapshot content checks and their limits](ONTOLOGY_DATA_BINDING.md#snapshot-content-checks-on-read).
- Cited evidence is checked for existence, import status, row count and the recorded file hash and, under the protected defaults, each cited import's current content must have its ingest record. The proposal carries no digest of the cited row, and the evidence is not judged relevant to the reason.
- The lifetime rests on the clock of the machine that records and checks the events. There is no trusted time source.
- Objects and sources are re-read before the admission is appended, not in the same transaction, so a change in between is not detected.
- Removing a person's role does not end approvals they gave; withdraw them or let them expire.
- Preconditions are free text and are not evaluated. Declared `permissions` are recorded, not enforced.
- Recheck does not look for newer imports, retracted links or other later facts; it is not a staleness check against current state.
- The proposal holds parameter values in clear text. The values digests are unsalted, so low-entropy values could be guessed. Handle a proposal at its recorded classification.
- Policy decisions use the object store's existing fixed purpose and retention labels. The caller's `purpose` and `retention` apply to the source reads.
- If appending the audit event fails, no proposal is returned.

## Signed approval at admission

Under the protected defaults (`protection.SIGNED_APPROVAL_REQUIRED`), `admit_approved_action` also needs a `SignedApproval`: a signed statement and the `ReceiptGate` that checks it. The statement is verified with keys from the gate's newest accepted, fresh key list, and must name this gate's tenant and release, the project, the proposal digest, the proposer from the proposal and the approver the chain recorded. Those values come from the caller's own chain and store, never from the statement. A statement lasts at most five minutes, is checked again at the write, and is not single-use itself: the one-use rule still comes from the chain's final event. A statement that was supplied is checked even when the flag is off.

Limits: the proposal digest and the approver are read from the same local chain the admission writes to, so someone who can rewrite that chain can still forge both; the statement adds a second root of trust (the issuer's key), not protection against a signer whose key is stolen. No issuer service exists; tests sign with a public test key. Nothing yet requires the statement at decision time, only at admission.

## Not yet built (next O2 slices)

A stored copy of proposals with a queryable list of their states (state is only what the chain events show), precondition evaluation, approval by more than one person, a validated read of a recorded outcome, and a runner that performs the simulation itself and produces the result digest (until then an outcome is a report, and nothing enforces that only a simulation followed an admission).
