# Operator Pilot Run-Record Field Map

**Status:** Documentation specification only; no implementation or durable operator run record is created here. PR #88 returns an in-memory `PilotResult` and does not persist this envelope.  
**Assessment base:** `87c7cc95b3e7c231f52dca4924d6fc433c698462` (22 November 2026)  
**Parent contract:** `docs/RUN_PROVENANCE_SPEC.md`  
**Execution boundary:** No simulation-engine call, no `agora/sim/**` changes, no real data, credentials, connectors or write-back.

## 1. Purpose

Map the existing immutable scenario-input provenance envelope into the operator pilot's own guided workflow record. This is an orchestration record, not a simulation run. The pilot must stop at the governed decision/outcome/reporting boundary and must not invoke the simulation engine.

The `input_provenance` object below must conform to `docs/RUN_PROVENANCE_SPEC.md`; this document adds operator-stage and audit evidence around it without weakening that contract.

## 2. Record envelope

A completed, denied or failed operator attempt has one immutable run ID and a versioned record with these fields:

| Field | Required content | Rule |
|---|---|---|
| `record_version` | Integer schema version, initially `1` | Reject unknown versions; never silently upgrade old records. |
| `run_id` | Unique immutable operator-attempt ID | Never reuse or overwrite an earlier attempt. |
| `run_kind` | `operator_synthetic_pilot` | Distinguishes this guided workflow from an engine/simulation run. |
| `repository_sha` | Exact Git commit SHA used for the attempt | Required; do not use a branch name as provenance. |
| `mode` / `data_class` | `exploratory` / `synthetic` | Never label as validated prediction, demand or observed sales. |
| `engine_invoked` | Boolean, always `false` | Any true value violates this pilot contract. |
| `validated_prediction_enabled` | Boolean, always `false` | Must agree with `VALIDATED_PREDICTION_ENABLED=False`. |
| `started_at`, `completed_at` | RFC3339 UTC timestamps | Completion may be absent while the attempt is in progress; timestamps are metadata only. |
| `status` | `running`, `completed`, `denied` or `failed` | A gate denial is a terminal `denied` result, not a retry that skips the gate. |
| `fixture_set_id` and `fixture_hashes` | Exact checked-in fixture ID plus SHA-256 for each fixture/schema/binding artefact | No `latest` alias; compute from exact bytes at runtime. |
| `input_provenance` | Version-1 envelope from `RUN_PROVENANCE_SPEC.md` | Exact `import_id`, manifest, scenario hash, manifest hash, binding/ontology/policy fingerprints and data role. Omit fields that do not exist after an early denial; never fabricate IDs or hashes. |
| `stage_results` | Ordered append-only stage events | Each event records stage name, result (`completed` / `denied` / `failed`), safe reason code, stable input/output references and timestamp. No raw rows or sensitive values. |
| `decision_ref` | Exact decision ID, version and fingerprint, when created | No mutable “current decision” lookup in place of the exact version. |
| `approval_ref` | Exact approved decision version, policy version and a non-sensitive actor reference | Actor authority is from Principal; do not persist credentials or raw identity tokens. |
| `audit_ref` | Chain ID, sequence, head hash, anchor verification status and trust level | Protected stages require the configured anchored writer; report `local_sidecar` trust honestly. |
| `outcome_refs` | Exact observed outcome IDs and review event references, when present | Simulated output is never an observed outcome. |
| `report_ref` | Report ID and explicit exploratory/simulated label, when present | No report may imply validated prediction or real-world effect. |

## 3. Canonical provenance mapping

Copy the exact version-1 fields from `docs/RUN_PROVENANCE_SPEC.md` into `input_provenance`:

- `provenance_version`
- `scenario_hash`
- `import_id` (exact immutable ID, never `latest`)
- `input_manifest` and canonical `manifest_hash`
- `binding_fingerprint`
- `ontology_pack_fingerprint`
- `transformation_policy_fingerprint` (or null only where the contract permits)
- `data_role`
- `created_at`

The manifest must retain the exact dataset/schema/source-registry/binding/ontology/policy and file-hash fields defined by the parent spec. Do not copy raw personal or sensitive values into this record.

## 4. Persistence and stop semantics

1. Allocate the immutable `run_id` and append a `running` envelope before the first workflow stage.
2. Append each stage result in order. A denied gate appends a safe denial code and terminates the attempt before the next protected read or write.
3. Once created, `input_provenance` is append-once. Corrections or reruns create a new run ID or explicit superseding record; never rewrite history.
4. If a business-store append succeeds but the anchored audit append fails, preserve the documented partial-failure state and surface a typed failure. Do not retry the business operation or silently report success.
5. On completion, append the final status and exact audit head/anchor verification result. A missing or invalid anchor is a denial, not an automatic bootstrap or repair.
6. If denied before import, record only the stages and identifiers actually known; do not invent an `import_id`, manifest or hash.

## 5. Required tests and mutation proofs

Tests must prove: exact field mapping to the parent provenance spec; repository/fixture/schema/binding hashes are exact; append-once immutability; new run IDs for retries/supersession; ordered stage events; a denial prevents all later protected reads/writes; engine invocation is always false; exploratory/synthetic labels are mandatory; no raw row/value/credential is persisted; anchor absence/mismatch fails closed; and partial audit failure is surfaced without rewriting the business record.

Mutation proofs must fail if code: substitutes `latest` for `import_id`; omits or changes a manifest hash; overwrites an existing envelope; continues after denial; invokes the simulation engine; changes `engine_invoked` or `validated_prediction_enabled`; accepts an unanchored writer on a protected stage; swallows anchor failure; or persists raw payloads.

## 6. Explicit exclusions

This specification does not authorise simulation wiring, any simulation run, calibration, backtest, forecast, real data, personal/customer data, credentials, identity/network connectors, external drivers, write-back, study mutation, or changes to `agora/sim/**`. Keep `VALIDATED_PREDICTION_ENABLED=False`. The operator pilot is synthetic governance evidence only.
