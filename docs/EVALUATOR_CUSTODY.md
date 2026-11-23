# Evaluator Custody and Label-Release Procedure

**Status:** Draft governance procedure for owner review. It does not authorize a dataset import, simulation, validation run, prediction-flag change, or release of test labels.

## 1. Roles and separation

- **Project owner:** controls approvals, access to sealed labels, and the decision to proceed.
- **Claude:** technical/data-custody operator. Claude verifies run inputs and outputs, maintains the sealed-label boundary, and is the sole recorder of official validation results in the canonical project record.
- **ChatGPT:** independent evaluator operating as a separate process. ChatGPT evaluates only the frozen artifacts explicitly handed over under this procedure. It does not run AGORA, alter inputs, tune configurations, or access the sealed labels before output freeze.

The evaluator must not participate in model/backend selection, calibration, tuning, or run execution in a way that exposes held-out labels or changes the preregistered configuration.

## 2. What the evaluator receives before label release

The evaluator handoff is limited to these artifacts:

1. The exact frozen validation protocol version and its commit/hash.
2. The exact dataset manifest and its SHA-256.
3. The raw AGORA output files for the completed, authorized run, accompanied by a per-file inventory containing relative path, byte count, and SHA-256.
4. The minimum provenance needed to interpret those outputs, included in or attached to the frozen output package: run/configuration identifiers, scenario identifiers, backend/model identifier and pinned version, seed, temperature/cache settings, command/version information, and completion or failure status.

No live workspace, repository write access, execution environment, source dataset workspace, database credentials, or general project filesystem is part of the evaluator handoff. If an output cannot be interpreted from the frozen artifacts, the evaluator must mark the affected package/configuration not evaluable rather than infer missing information.

## 3. What remains sealed

ChatGPT must not receive, inspect, infer from, or be shown the held-out test labels before the output freeze has been completed and attested.

The sealed label material includes:

- **Elections:** the 2016 held-out election outcomes/labels.
- **Ember:** the 2024–2025 held-out monthly EV-registration labels. Package A is predeclared NOT EVALUABLE in the current v0.2 specification; these labels remain sealed and are not used for an AGORA claim.

Calibration and validation-period information may be used only to the extent explicitly allowed by the frozen protocol. Held-out labels must not be used to choose mappings, scale constants, backends, seeds, thresholds, stopping rules, or output transformations.

## 4. Output freeze and label-release sequence

The following sequence is mandatory and ordered:

1. Claude completes the authorized run under the then-current frozen protocol. Any stop rule, missing target, invalid configuration, or failed integrity check stops the affected package/configuration; it is marked not evaluable and is not silently repaired or rerun.
2. Claude collects every raw output file and the associated run provenance. No post-run edits, filtering, replacement, or selective omission are permitted after freeze.
3. Claude computes SHA-256 for every output file and records its relative path and byte count. A package-level output manifest is created and itself hashed.
4. Claude verifies the output inventory is complete, records the exact protocol and input-manifest hashes, and posts a timestamped freeze attestation to the project log. The attestation identifies the output-manifest hash and confirms that the held-out labels have not been disclosed to ChatGPT.
5. Only after that attestation may the owner/Claude release the sealed 2016 and Ember 2024–2025 labels to the evaluator, as a separate, clearly identified label bundle. The label bundle must have its own file inventory and SHA-256 values. Its release time must be later than the output-freeze attestation.
6. ChatGPT evaluates the frozen outputs against the released labels and the frozen protocol. It must not modify the frozen outputs or protocol. Any mismatch, missing output, hash failure, or ambiguity is reported; the affected result is not evaluable unless the frozen protocol already defines a deterministic resolution.

If outputs are not frozen and hashed, labels remain sealed. A run completing is not itself an output freeze.

## 5. Evaluation and official recording

- ChatGPT returns an independent evaluation report identifying the exact protocol, input-manifest, output-manifest, and label-bundle hashes used.
- The report must follow the frozen metrics and mappings. It must include every baseline comparison and every loss to baseline; no result may be omitted because it is unfavorable.
- Results must distinguish calibration, validation, and held-out test periods. No tuning or scale adjustment may use held-out labels.
- ChatGPT may flag arithmetic, mapping, provenance, or integrity issues, but it must not revise the protocol or rerun a configuration.
- **Claude alone records the official validation result** in the canonical AGORA project log/results record, including the evaluator report reference and all relevant hashes. The owner independently reviews the result.
- Any disagreement or suspected leakage is recorded as an unresolved validity issue. It is not resolved by silently changing the data, protocol, or result.

## 6. Stop conditions

Mark the affected package/configuration **NOT EVALUABLE** and stop if any of the following occurs:

- A required target output is absent or cannot be mapped under the frozen protocol.
- An input, output, or label hash/byte count does not match its declared inventory.
- The backend, model version, seed, temperature, cache, command, or scenario differs from the frozen specification.
- A required output is missing, truncated, modified after freeze, or cannot be tied to the run provenance.
- Held-out labels were exposed before the output-freeze attestation.
- A metric, baseline, mapping, or transformation would need to be invented or changed after seeing held-out results.

No rerun, replacement dataset, alternate baseline, flag change, or protocol amendment is implied by a not-evaluable result. Each requires the approvals and versioning rules already in force.

## 7. Current authorization boundary

Protocol v0.1 is frozen at commit `6d06088cf7954bd41f003544f5ec61675389bcc1`, with Agora's 15-row hash-only dataset register SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. The v0.1 freeze explicitly authorizes no run, no dataset import into AGORA, and no flag change.

The additive `docs/VALIDATION_RUN_SPEC.md` v0.2 is now merged on main via #205 (exact head `9d5c466ec886b27e7c83c5c13695810cb44ed08d`, exact-head CI run `45222866705` passed 4/4), but it remains DRAFT. The owner's conditional v0.2 freeze pre-approval is limited to five named additions: published-average-to-AGORA input mapping, AGORA vote-share-to-state-margin mapping, counted-action-to-EV mapping, run command, and backend. Splits, metrics, baselines, data and manifest must remain unchanged; verify that boundary before invoking the pre-approval. Package A is explicitly NOT EVALUABLE; Package R/M5 is dropped.

**Blocking label-custody defect found by static connector review:** `agora/validation/run_election_validation.py` currently calls `_verify(manifest, a.medsl, ...)` and `h.load_outcomes(a.medsl, ...)` before checking `--sealed-sha` in the `test-evaluate` stage. Both operations read the MEDSL label file. This contradicts the run-spec claim that the seal is checked before labels are opened. Do not run `test-evaluate`, hand over labels, or release the 2016 bundle until the driver first verifies the frozen output file and its SHA-256 against `--sealed-sha`, then and only then hashes and loads MEDSL. A regression test must prove missing/wrong seals cause zero label-file reads; a mutation that moves label verification/loading before the seal check must make that test fail. ChatGPT did not execute code or tests.

The separate owner-controlled private repository still lacks the MEDSL and Ember raw-file handoff; P2D PR #5 contains only the 12 FiveThirtyEight CSVs. The production CLI remains default-deny. `VALIDATED_PREDICTION_ENABLED=False` remains in force. No run or data import is authorized by this procedure; M3 remains unreached. This document does not change the frozen protocol or manifest.