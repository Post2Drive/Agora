# Ontology action proposals (O2, first slice)

**Status:** library only (`agora/ontology/actions.py`, `agora/ontology/approvals.py`). No CLI, web or service uses it. It proposes and records an approval or rejection; it does not queue, execute or write back. The O2 guardrail in [ONTOLOGY_CAPABILITY_TARGET.md](ONTOLOGY_CAPABILITY_TARGET.md) (no general action executor yet) still applies.

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
- `verify_approved_action(store, document, digest, ...)` is the check to run before a later step acts. It needs read authority and re-reads the objects and sources (`recheck_action_proposal`), then requires the proposal event, exactly one decision event that is an approval, and an approver who is not the proposer. A changed pack, object or source row makes it fail, which is how a stale approval is caught.
- The decision step does not re-read the objects: the approver decides on the document they were shown, and staleness is caught at verification.

## Limits

- `recheck_action_proposal` alone does not authenticate `proposed_by` and `policy_version`; `decide_action_proposal` and `verify_approved_action` check them against the anchored chain. No signature: the chain is a local file, so someone who can rewrite it and its anchor, or run code in the service, can forge a proposal or an approval. A valid digest alone is not an approval.
- **Object reads do not authenticate row content.** `get_object` accepts a source row edited in `data/tabular.sqlite3` when its identity and provenance still match (a test shows this). Recheck detects a change made *after* the proposal through the retained values digest. A change made before the proposal is not detected.
- Cited evidence is checked for existence, import status, row count and the recorded file hash. Row content is not hashed, and the evidence is not judged relevant to the reason.
- Preconditions are free text and are not evaluated. Declared `permissions` are recorded, not enforced.
- Recheck does not look for newer imports, retracted links or other later facts; it is not a staleness check against current state.
- The proposal holds parameter values in clear text. The values digests are unsalted, so low-entropy values could be guessed. Handle a proposal at its recorded classification.
- Policy decisions use the object store's existing fixed purpose and retention labels. The caller's `purpose` and `retention` apply to the source reads.
- If appending the audit event fails, no proposal is returned.

## Not yet built (next O2 slices)

A signed receipt over the digest, a persisted proposal ledger with states and expiry (an approval does not expire and is not a lease), precondition evaluation, approval by more than one person, and simulation-only application.
