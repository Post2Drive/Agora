# G4 — Validation approval lifecycle and report enforcement

## Purpose and safety boundary

G4 connects a validation-evidence record to an append-only review lifecycle and a fail-closed report preflight. A `passed` review is scoped, claim-limited and time-limited. It is not a general endorsement of a model or of other use cases.

`validated_prediction` output remains disabled in this release. The report writer verifies the complete approval gate and then refuses to emit validated output until the project owner separately authorises enabling the feature flag in `agora/report/writer.py`. Exploratory reports remain the default.

## Project-specific scope binding

Validated report preflight requires an owner-authored `validation/scope.json`. This file is intentionally not inferred from scenario free text: geography, target and population boundaries require explicit owner decisions.

Required JSON fields:

- `scenario_name`: exact scenario name.
- `scenario_sha256`: SHA-256 of the exact `scenario.yaml` bytes.
- `domain`, `use_case`, `target`, `population`, `geography`, `horizon`: explicit scope strings.

The preflight derives `model_version` from the active backend/model and computes `config_hash` from the scenario SHA-256 plus the non-secret model configuration (backend, model, endpoint, timeout, parallelism, context and model-policy/cache flags). A changed scenario or model configuration invalidates the registry match. API keys are never included in the hash payload or written to registry records. On Windows, obtain the exact scenario digest with `Get-FileHash .\scenario.yaml -Algorithm SHA256`; place that digest in `scenario_sha256` in `validation/scope.json`.

## Registry evidence

Create a JSON object with the fields in `agora.validation.registry.REQUIRED`. `data_provenance`, `holdout_design`, `baselines`, `metrics`, `thresholds`, `results` and `uncertainty` must be non-empty objects. `results.threshold_assessment.overall` must be `pass` before a review can move to `passed`. `holdout_design.protocol_fingerprint` and `data_provenance.source_hashes` are required for a pass. The entry is immutable after registration and begins at `not_assessed`; `approved_claims` is assigned only by the final passed review.

Example lifecycle:

```powershell
agora validation add <PROJECT> evidence.json
agora validation review <PROJECT> <REGISTRY_ID> --to-status protocol_drafted --reviewer "Reviewer Name" --rationale "Protocol reviewed" --evidence-ref "docs/protocol.pdf"
agora validation review <PROJECT> <REGISTRY_ID> --to-status data_reviewed --reviewer "Reviewer Name" --rationale "Data provenance reviewed" --evidence-ref "validation/data-review.md"
agora validation review <PROJECT> <REGISTRY_ID> --to-status evaluation_pending --reviewer "Reviewer Name" --rationale "Evaluation evidence complete" --evidence-ref "validation/evaluation.json"
agora validation review <PROJECT> <REGISTRY_ID> --to-status passed --reviewer "Approver Name" --rationale "Scope-specific approval" --evidence-ref "validation/approval.md" --approved-claim "Exact approved claim" --expires-at "2027-01-01T00:00:00+00:00"
agora validation list <PROJECT>
```

The allowed transitions are strictly forward:

`not_assessed -> protocol_drafted -> data_reviewed -> evaluation_pending -> passed | failed | inconclusive`.

Failed and inconclusive records are terminal; create a new registry entry for a materially revised evaluation. Expiry is computed from the passed review's timestamp and is not an editable status transition. Every review requires reviewer identity, rationale and one or more evidence references. Review events are appended to `validation/reviews.jsonl` through the G2 hash-chained audit logger; previous events are not overwritten.

## Report preflight

A validated report request must provide `--registry-id` and one or more exact `--claim` values. The report writer verifies:

1. The scope file exists, parses, and is bound to the exact scenario name and SHA-256.
2. The active model version and computed config hash match the registry entry.
3. The latest hash-chain review state is `passed` and not expired.
4. Domain, use case, target, population, geography, horizon, model and config all match exactly.
5. Every requested claim is included in the passed review's `approved_claims` list.
6. The registered evidence is complete and the evaluation threshold assessment passed.

Any missing, malformed, expired or mismatched condition raises `PermissionError` before report analysis or file output. A rejected validated request does not silently generate a validated report. The owner can explicitly request `--mode exploratory` instead.

## Limitations

- The scope file is an explicit owner assertion bound to the scenario bytes; it does not independently prove the truth of domain/geography/population claims.
- Reviewer identity and evidence references are recorded as supplied strings; G4 does not authenticate an identity provider or verify external evidence documents.
- Hash-chained review history is tamper-evident, not immutable against an actor who can rewrite the entire file and recompute the chain. Preserve and independently anchor backups.
- The report generator currently creates simulation-oriented narrative. Therefore validated output remains disabled even when a registry approval passes. A separate owner decision and a claim-aware report-content implementation are required before enabling it.
- G5 prediction/outcome monitoring is not part of G4.
