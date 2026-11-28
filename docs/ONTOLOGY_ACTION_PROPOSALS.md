# Ontology action proposals (O2, first four slices)

**Status:** library only (`agora/ontology/actions.py`, `agora/ontology/approvals.py`, `agora/ontology/outcomes.py`). No CLI, web or service uses it. It proposes, records an approval or rejection, ends an approval by withdrawal or by one admission for simulation, and records the outcome the admitter reports for that admission; it does not simulate, queue, execute or write back. The O2 guardrail in [ONTOLOGY_CAPABILITY_TARGET.md](ONTOLOGY_CAPABILITY_TARGET.md) (no general action executor yet) still applies.

## What a proposal binds

`propose_action` returns canonical JSON (`format: agora.ontology.action_proposal/v1`) and its SHA-256 digest:

- project, pack fingerprint, and the exact ActionType ID, version and fingerprint;
- the actor and target objects: exact type, version, import and record key, plus binding and schema fingerprints, source file hash, source row ID, and a digest of the property values read at proposal time;
- parameters, which must name exactly the ActionType inputs;
- at least one cited source record (import, file hash, row), without duplicates;
- the reason, the highest classification involved, and the proposer and policy version from the policy decision;
- the declared preconditions, effects and permissions, with `executed: false` and `preconditions_evaluated` true only when every declared precondition is an evaluated `expr:` (see below).

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

### Reading an outcome

`read_simulation_outcome(store, document, digest, ...)` returns the recorded status, result digest, recording identity and time, the proposer, the approver and, where there is one, the second approver.

- It needs `ontology_read` at the proposal's own classification and a principal-bound identity. Under the central roles `operator`, `reviewer` and `reader` have it; `approver` does not. The decision is made, and appended to the chain like other read decisions, before any proposal event is looked up.
- The chain must hold the proposal from the person the document names, one approval from someone else, one well-formed admission by someone who gave neither approval, and one well-formed outcome from that admitter. A sensitive proposal also needs one well-formed second approval while `protection.TWO_PERSON_SENSITIVE` is set, so an outcome admitted without one is refused then. A second approval that is recorded is checked whatever the flag says. Positions in the chain must be: proposal, approval, second approval (where present), admission, outcome. Recording does not compare positions, so an outcome appended ahead of its admission by someone who can write to the chain is refused here.
- The same history must also pass the checks behind `action_proposal_state`: every recorded proposal of this digest agrees on who proposed it, the policy version and the resources, and the decision, second approval, ending and outcome name the same pack, action and version. So this read does not return an outcome for a history the state view reports as `inconsistent`. The reverse does not hold: the read is stricter, for example about a required second approval.
- With no outcome it raises "no outcome has been recorded". That does not show that nothing ran. A malformed or second outcome raises a different error; so does an unrelated event under the outcome's event ID.
- It does not re-read the objects, check the approval's age or a signed statement, or receive or check the result content. The caller compares the content it holds with `result_digest`, so it is still a report in the chain, not proof that an effect happened.
- `verify_simulation_result` takes only the result document. It checks the history behind the outcome with the same `action_proposal_state` rules, but it has no proposal document, so it does not tie the proposer to a document or know whether a second approval was required. A caller who holds the proposal calls both and compares the two `result_digest` values.

## Limits

- An outcome is not evidence that a simulation ran, that the digest belongs to a real result, or that nothing else was done with the admission.
- `recheck_action_proposal` alone does not authenticate `proposed_by` and `policy_version`; `decide_action_proposal` and `verify_approved_action` check them against the anchored chain. No signature: the chain is a local file, so someone who can rewrite it and its anchor, or run code in the service, can forge a proposal or an approval. A valid digest alone is not an approval.
- **Row checks on read are unkeyed.** Object reads recompute the stored row ID, so a source row edited under its pinned row ID is refused both before and after a proposal. Under the protected defaults these reads also require each import's [ingest record](ONTOLOGY_DATA_BINDING.md#ingest-record-in-the-audit-chain) in the anchored chain. Neither check is a signature or authenticates the snapshot against the original file; see [the snapshot content checks and their limits](ONTOLOGY_DATA_BINDING.md#snapshot-content-checks-on-read).
- Cited evidence is checked for existence, import status, row count and the recorded file hash and, under the protected defaults, each cited import's current content must have its ingest record. The proposal carries no digest of the cited row, and the evidence is not judged relevant to the reason.
- The lifetime rests on the clock of the machine that records and checks the events. There is no trusted time source.
- Objects and sources are re-read before the admission is appended, not in the same transaction, so a change in between is not detected.
- Removing a person's role does not end approvals they gave; withdraw them or let them expire.
- Only preconditions written as `expr:` are evaluated; any other precondition is free text and is not. Declared `permissions` are recorded, not enforced.
- Recheck does not look for newer imports, retracted links or other later facts; it is not a staleness check against current state.
- The proposal holds parameter values in clear text. The values digests are unsalted, so low-entropy values could be guessed. Handle a proposal at its recorded classification.
- When a proposal is classified `personal` or `sensitive`, every policy check this lifecycle makes at that classification carries the caller's `purpose` and `retention`, and nothing is filled in if they are absent: building and rechecking, deciding, the second approval, withdrawing, admitting, recording and reading an outcome, and reading one proposal's state. `list_action_proposals` checks at `sensitive`, so it needs them too. The first check in building a proposal runs before any object is looked up and keeps the fixed catalog labels, as do pack checks. `verify_simulation_result` receives no proposal document, checks at `internal` and takes neither value, so it is not covered. The values apply to the source reads as before. The policy receives them; this library does not judge whether a stated purpose is permitted, and the authorization audit event does not record them. Each step states its own values: nothing ties an approver's purpose to the proposer's. Building and rechecking compute the classification from the stored objects and declared inputs. The other steps take it from the proposal document before the chain is read; their later chain checks do not accept a document the chain did not record.
- If appending the audit event fails, no proposal is returned.

## Signed approval at admission

Under the protected defaults (`protection.SIGNED_APPROVAL_REQUIRED`), `admit_approved_action` also needs a `SignedApproval`: a signed statement and the `ReceiptGate` that checks it. The statement is verified with keys from the gate's newest accepted, fresh key list, and must name this gate's tenant and release, the project, the proposal digest, the proposer from the proposal and the approver the chain recorded. Those values come from the caller's own chain and store, never from the statement. A statement lasts at most five minutes, must not expire after the approval (at the lifetime asked for in this call), and is not single-use itself: the one-use rule still comes from the chain's final event. Inside the admission's append transaction, the key list used for the check must still be the newest in the store being written and fresh, the statement unexpired, and the gate's clock not behind its first reading; so a revocation accepted after the signature check stops the admission. The admission event records `approval_statement_hash`; the statement itself is not stored, and reading the event later does not verify the signature again. The gate must be a `ReceiptGate`, but the library cannot tell that it was opened from the worker's own configuration. The key list does not say what a key is for, so any accepted online key, including one used for run receipts, can sign a statement. A statement that was supplied is checked even when the flag is off.

Limits: the proposal digest and the approver are read from the same local chain the admission writes to, so someone who can rewrite that chain can still forge both; the statement adds a second root of trust (the issuer's key), not protection against a signer whose key is stolen. No issuer service exists; tests sign with a public test key. Nothing yet requires the statement at decision time, only at admission.

## Reading where a proposal stands

`action_proposal_state` (one proposal) and `list_action_proposals` (every proposal in the chain, optionally one state) read the anchored chain once and report: `proposed`, `rejected`, `approved`, `awaiting_second_approval`, `expired`, `withdrawn`, `admitted`, `simulation_succeeded`, `simulation_failed`, or `inconsistent` with a reason (for example two decisions, a self-decision, an outcome without an admission, events out of chain order, a decision, second approval, admission or outcome whose resources differ from the proposal's, a decision, second approval, admission or outcome with the wrong ID, or an outcome with the wrong operation or no valid result digest). Proposing the same content again is allowed and does not change the state; repeated records must agree on proposer, policy version and resources. One inconsistent digest does not hide the others. Reading changes nothing. One proposal is read at its own classification and must name the proposer the chain recorded; the list needs read authority at the highest classification.

Limits: the state comes from the chain only, so `approved` does not mean the proposal would still pass `verify_approved_action` (objects and sources are not re-read, and a signed statement is not checked). The list covers the whole chain, not one project. Expiry uses the process clock and the default 24 hours unless a shorter `max_age_seconds` is passed, so a caller using a shorter limit at admission must pass the same limit here. This is a view over the chain, not a separate stored ledger.

## Preconditions (`expr:`)

A precondition string that starts with `expr:` is machine-checked; others stay free text. The grammar is closed: one to eight clauses joined by ` and `, each `operand OP operand` with `OP` one of `==`, `!=`, `<`, `<=`, `>`, `>=`. An operand is `actor.<property>`, `target.<property>`, `param.<property>` (an input of the action) or a literal (`"text"`, a number, `true`, `false`, `null`). No `or`, arithmetic, functions or other lookups. Example: `expr: target.crm:Customer.status == "open" and param.crm:Request.count >= 1`.

- A pack with an `expr:` that is outside the grammar, names a property the object type or action does not have, mixes kinds (number, text, date, boolean), orders text or booleans, uses a property of another data type, or compares a date with an impossible date literal is refused when it is parsed. So is a precondition that only looks like an expression (a leading space, `Expr:`, `expr :`), which would otherwise be unenforced free text.
- When a proposal is built, every `expr:` is evaluated against the actor and target values read from their source rows and the parameter values. A false clause refuses the proposal and records nothing; the message names the precondition text, never a value. A property that was never read (for example one the source binding does not map) or a malformed value makes a clause false, whatever the operator. A stored null is unknown: only `== null`, written with the literal `null`, is true for it. Every other comparison with it is false, including `!=`, and two nulls are not equal to each other. So `target.status != "frozen"` does not pass when the status is unknown.
- The document lists the evaluated texts in `preconditions_met`, and `preconditions_evaluated` is true only when every declared precondition was an `expr:`. A pack with no `expr:` produces the same document as before.
- Admission rebuilds the proposal from the current objects, so the same expressions are evaluated again and a changed source row is refused there. The rebuild and the audit append are not one transaction, as above.

Limits: evaluation shows only that the stored values satisfied the expression when it was read. It does not look at anything outside the two objects and the parameters, such as other records, time or links. Dates compare as dates, timestamps cannot be used. The expression language was chosen to be small enough to read in full; it is not extended without a review of its grammar.

## Dry-run simulation and its recorded result

`run_admitted_simulation` is called by the identity that admitted the action. It rebuilds the proposal from the objects and sources as they are now (so `expr:` preconditions are evaluated again), builds a result document, and records the document's digest as the outcome through `record_simulation_outcome`. The caller keeps the document; `verify_simulation_result` later shows that a document is exactly the one recorded.

- The result lists digests of the actor and target values and of the parameters, the `expr:` preconditions that held, and the action's declared effects marked `simulated`, with `state_changed: false`. There are no timestamps, so rebuilding it from the same proposal gives the same digest.
- A failure report is recorded as a failed outcome only for a positive finding: an `expr:` precondition is false; a pinned source row is missing from a readable committed import, no longer matches its row ID or object identity, or no longer matches the stored object reference's provenance; or the rebuilt proposal differs from the admitted one.
- Every other error is raised and records nothing, so the admission keeps its one outcome and the run can be tried again. This includes a refusal by policy, a missing or locked snapshot database, and an ingest record, import, manifest or cited evidence that cannot be read or verified. Some of these may be lasting damage (for example an altered manifest or changed cited evidence); they leave the admission without an outcome, which shows only that none was recorded.
- An admission still has one outcome. A second run is refused after the rebuild.
- `verify_simulation_result` needs read authority. It requires exactly one outcome event for the proposal, under the fixed event ID, from an allowed `ontology_action_outcome` by a named identity, whose result hash equals the digest of the document, and whose success or failure kind matches the document's format. The chain must also show what led to it, by the same rules as `action_proposal_state` (one shared check): the proposal (repeated records must agree on proposer, policy version and resources), one approval by someone other than the proposer, at most one second approval by a third person, one admission by someone who approved neither, and then the outcome from that admitter, in chain order, with the same pack, action and version throughout. The `unknown` placeholder, written when no identity was established, never counts as an identity at any step. It reads the chain only: it does not re-read objects or sources, check the approval's age or a signed statement, or know whether the proposal's classification required a second approval. Someone who can write the whole sequence into the chain can still forge it.

Limits: effects are names, not programs, so nothing is applied to any data and the result shows only that the rebuild passed at the time of the run, not what an effect would have done. The run is not tied to the admission beyond the same identity and the chain's one-outcome rule, and `record_simulation_outcome` with a caller-supplied digest is refused under the protected defaults (`protection.RUNNER_ONLY_OUTCOMES`), which stops accidental use, not code in the same process that calls the private recorder. Verification shows the document matches what the chain recorded; the chain is a local file with the limits above.

## Second approver for sensitive proposals

Under the protected defaults (`protection.TWO_PERSON_SENSITIVE`), a proposal classified `sensitive` needs two approvers who are three different people with the proposer. After the first approval, `co_approve_action_proposal` records the second as `ontology_action_co_approved` under the fixed event ID `ontology-action-coapproval-<digest>`, with the same decision operation and a reason hash. It needs a live first approval (not withdrawn, used, expired or a rejection), is once per proposal, and does not extend the first approval's lifetime. A withdrawal, admission or expiry is checked again while the chain's write lock is held, so a second approval cannot be recorded after one of them.

- `verify_approved_action` and so `admit_approved_action` refuse a sensitive proposal without exactly one well-formed second approval from someone other than the proposer and the first approver, and name `co_approved_by` in their result.
- Neither approver can admit. This also holds when the second approval was recorded but not required (a proposal that is not sensitive, or the flag off), and it is checked again under the chain's write lock. The state view reports an admission under either approver as `inconsistent`, and no outcome can be recorded for it. With signed statements required, admission takes one statement per approver in order (first, second); each is checked against the approver this chain recorded. The admission event's `approval_statement_hash` is the statement's hash for one approver, or the hash of both statement hashes joined by a newline for two.
- A rejection by the first decider still ends the proposal; there is no second rejection. Either approver (or any other decider) can withdraw.
- `action_proposal_state` shows `co_approved_by`, and reports a second approval that is malformed, duplicated or has no approval as `inconsistent`.

Limits: the requirement is set by the proposal's classification and a protection flag, not by the action type, and it is two people, not a configurable quorum. The state views report a live first approval that still needs the second as `awaiting_second_approval`, using the same rule as `verify_approved_action`, so `list_action_proposals(state="approved")` leaves it out. `approved` there still does not mean admissible. `action_proposal_state` takes the classification from the proposal document, which the digest covers; the list takes it from the `proposal_sensitivity` field of the proposal record. Records written before that field existed give the list no classification: such an entry stays `approved` and carries `second_approval_requirement: "unknown"`. Records that carry different or unknown classifications, or one that differs from the document, are `inconsistent`. The views apply the current protection flag, not the one in force when the approval was recorded. Two identities are only as distinct as the policy that issues them.

## Not yet built (next O2 slices)

A stored copy of proposals (states are now readable from the chain, but the proposal documents themselves are not kept), a configurable approver quorum, effects that are more than names (a real simulation).
