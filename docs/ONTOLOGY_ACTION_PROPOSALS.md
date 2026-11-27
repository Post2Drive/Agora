# Ontology action proposals (O2, first slice)

**Status:** library only (`agora/ontology/actions.py`). No CLI, web or service uses it. It proposes; it does not approve, queue, execute or write back. The O2 guardrail in [ONTOLOGY_CAPABILITY_TARGET.md](ONTOLOGY_CAPABILITY_TARGET.md) (no general action executor yet) still applies.

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

## Limits

- No signature: `proposed_by` and `policy_version` are covered by the digest but cannot be rebuilt, so recheck does not authenticate them. A valid digest is not an approval.
- **Object reads do not authenticate row content.** `get_object` accepts a source row edited in `data/tabular.sqlite3` when its identity and provenance still match (a test shows this). Recheck detects a change made *after* the proposal through the retained values digest. A change made before the proposal is not detected.
- Cited evidence is checked for existence, import status, row count and the recorded file hash. Row content is not hashed, and the evidence is not judged relevant to the reason.
- Preconditions are free text and are not evaluated. Declared `permissions` are recorded, not enforced.
- Recheck does not look for newer imports, retracted links or other later facts; it is not a staleness check against current state.
- The proposal holds parameter values in clear text. The values digests are unsalted, so low-entropy values could be guessed. Handle a proposal at its recorded classification.
- Policy decisions use the object store's existing fixed purpose and retention labels. The caller's `purpose` and `retention` apply to the source reads.
- If appending the audit event fails, no proposal is returned.

## Not yet built (next O2 slices)

Approval bound to the digest (reusing the decision approval rules, with proposer and approver separated), a signed receipt over the digest, a persisted proposal ledger with idempotency and states, precondition evaluation, and simulation-only application.
