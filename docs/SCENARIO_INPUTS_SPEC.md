# Simulation Scenario Inputs — Rung 4 Bridge

**Status:** design only. This contract does not edit `agora/sim/**`, run simulations, calibrate models, or enable validated predictions.

## 1. Purpose and boundary

Scenario inputs are built from explicitly named, read-only binding-materialized snapshots. A caller supplies an `import_id`, or a binding plus `import_id`; the adapter never resolves `latest`. Inputs retain the snapshot, schema, binding, and source provenance needed to reproduce a run.

Personal and sensitive values do not enter prompts, agent memory, or scenario text by default. A separate policy decision must explicitly authorize a permitted transformation, with purpose, retention, sensitivity, reviewer, and audit reference. Without that decision, the adapter rejects the input.

## 2. Scenario-input manifest

Every generated input carries an immutable manifest:

- explicit `import_id`, dataset/schema IDs and versions;
- snapshot manifest hash and file SHA-256;
- binding ID/version/fingerprint and ontology pack/version fingerprint;
- source registry IDs and data role;
- selected columns/property IDs and type/sensitivity decisions;
- transformation policy ID, if any, with reviewer and timestamp;
- engine/application version and creation timestamp;
- `scenario_hash` and the run-provenance reference.

The manifest is canonical JSON and is stored with the scenario input. A caller cannot replace its hash fields after construction.

## 3. Reproducibility and identity

`scenario_hash` is a domain-separated SHA-256 over the canonical input payload plus the snapshot manifest hash, schema fingerprint, binding fingerprint, ontology fingerprint, transformation-policy fingerprint, and declared scenario parameters. The same explicit snapshot and policy produce the same hash. A different snapshot manifest, schema, binding, policy, or parameter produces a different hash.

The adapter rejects `latest`, an omitted import ID, an ambiguous selector, a missing manifest hash, and a mismatch between stored snapshot metadata and the supplied binding. Each run records the exact scenario hash and import ID; reports never imply that an input was current merely because it was most recent.

## 4. Governance and source roles

`sealed_holdout` snapshots cannot feed scenario inputs. Calibration and validation roles are checked by the existing source registry and holdout rules; the adapter does not infer or upgrade roles. A role mismatch fails closed before values are read.

The adapter is read-only. It must not update snapshot tables, source registry records, graph storage, credentials, external systems, or simulation state. `VALIDATED_PREDICTION_ENABLED` remains `False`; outputs are exploratory and must carry the input manifest and scenario hash.

## 5. Acceptance tests and mutation proofs

The implementation must show:

1. an explicit import ID is required and `latest` is rejected;
2. the same snapshot and binding produce the same scenario hash;
3. a different snapshot manifest changes the scenario hash;
4. a binding or schema fingerprint change changes the hash;
5. sealed-holdout input is rejected;
6. role and policy mismatches fail closed;
7. personal/sensitive values are rejected from prompts and agent memory without an explicit policy decision;
8. provenance fields and exact import ID are present in every run record;
9. snapshot tables remain unchanged after input construction;
10. no code path calls `agora/sim/**` or enables validated prediction.

Required scratch mutations, never committed:

- remove the sealed-holdout check; the holdout test must fail;
- omit the snapshot manifest hash from the hash input; the different-snapshot/hash test must fail.

## 6. Non-goals

This specification does not define model prompts, agent-memory formats, calibration, backtests, forecasts, real personal data, network access, credentials, external drivers, write-back, or any simulation execution. Those require separate implementation and owner approval.
