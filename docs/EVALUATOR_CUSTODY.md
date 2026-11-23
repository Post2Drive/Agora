# Evaluator Custody and Label-Release Procedure

**Status:** Draft governance procedure for owner review. This document defines the independent review boundary; it does not authorize a flag change, new dataset, additional run, label release before output freeze, or alteration of the frozen protocol or manifest.

## 1. Roles and separation

- **Project owner:** controls approvals and the release of sealed labels.
- **Claude:** run operator and data custodian. Claude executes the authorized stages, maintains the sealed-label boundary, creates the raw-output inventory and freeze attestation, and is the sole recorder of official validation results in the canonical project log.
- **ChatGPT:** independent evaluator in a separate process. ChatGPT receives only the frozen protocol, manifest and raw output artifacts for review. It does not run Agora, tune mappings, select a backend, alter outputs, or access held-out labels before the output freeze.

The evaluator must not participate in calibration or run execution in a way that could expose held-out labels or influence the preregistered configuration.

## 2. Frozen governing artifacts

The current frozen package is:

- **Protocol v0.2 commit:** `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`.
- **v0.2 run-spec SHA-256:** `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`.
- **Unchanged v0.1 protocol commit:** `6d06088cf7954bd41f003544f5ec61675389bcc1`; protocol file SHA-256 `b776948e14d6dc5c72262b3572365ebc0288fd632bc0bb13743d96fe7d8fea66`.
- **Unchanged 15-row dataset manifest SHA-256:** `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`.
- **Package scope:** Package E only for the current evaluable benchmark; Package A is predeclared NOT EVALUABLE; Package R/M5 is dropped.
- **Prediction flag:** `VALIDATED_PREDICTION_ENABLED=False`.

The v0.2 additions are limited to the owner-pre-approved mappings, run command and backend. The splits, metrics, baselines, data and manifest remain unchanged. No document in this procedure amends the frozen protocol or manifest.

## 3. What ChatGPT receives

Before any held-out label release, the evaluator handoff is limited to:

1. The exact frozen protocol and run-spec version/commit/hash.
2. The exact 15-row dataset manifest and its SHA-256.
3. The raw, unmodified output files for the authorized Package E run, including every output from every stage needed by the frozen specification.
4. A complete output inventory listing each relative path, byte count and SHA-256, plus the SHA-256 of the inventory itself.
5. Minimum provenance needed to interpret the files: run/configuration identifiers, election/stage identifiers, scenario identifiers, backend/model and pinned version, seed, temperature/cache settings, exact command and code commit, timestamps, and completion/failure status.

The handoff is file-based and read-only. It does not include a live workspace, credentials, source-data workspace, execution environment, repository write access, or unrelated project files. ChatGPT must not infer missing fields. If an output cannot be interpreted from the frozen artifacts, the affected stage/configuration is reported NOT EVALUABLE.

## 4. Output freeze and label boundary

Claude's reported stage sequence is: calibrate on 2000/2004/2008; validate on 2012; predict the held-out 2016 period without opening its labels; freeze and hash the resulting raw outputs; only then proceed to test-evaluate under the frozen procedure.

The required order is:

1. Complete only the authorized Package E stages under the frozen v0.2 configuration. Do not add seeds, elections, packages, transformations or retries outside the frozen specification.
2. Collect **all** raw output files and run provenance. Do not filter, edit, regenerate, rename to conceal, or selectively omit an unfavorable output.
3. Compute SHA-256 and byte count for every raw output file. Create a complete relative-path inventory and hash the inventory itself.
4. Record in the Notion collaboration log the exact protocol commit, run/code commit, input manifest hash, every output path/byte count/hash, output-inventory hash, timestamp, stage completion/failure state, and an explicit statement that 2016 labels have not been opened or disclosed to ChatGPT.
5. ChatGPT independently checks the received raw files against the logged inventory **before interpreting their contents**. This is an output-integrity review only; it does not require or permit access to 2016 labels.
6. Held-out labels remain sealed until the output freeze is attested and the owner/Claude performs a separate, explicit label handoff with its own path/byte-count/SHA-256 inventory. The label bundle's release timestamp must be later than the output-freeze attestation.
7. Only after the independent output-integrity check and the separate label handoff may ChatGPT compare frozen outputs with held-out labels under the frozen metrics. Claude alone records the official validation result.

**Merged seal-order fix and remaining coverage gate:** PR #211 merged to main at merge commit `2730903234196e9b38914ccb0fcab2de4e6c16ca` from exact head `1d90528de82d2a08f24ad38cf6c7c5c7bdd15eb0`; its two changed paths are `agora/validation/run_election_validation.py` and `tests/test_election_harness.py`. Exact-head CI run `45229437458` passed 4/4 (Ubuntu/Windows × Python 3.11/3.12). The merged driver now reads and SHA-256 hashes `test_outputs.json` and rejects missing or mismatched `--sealed-sha` before `_verify(..., "countypres_2000-2024.csv")` and `load_outcomes`. The merged test diff adds a wrong-seal negative that asserts the MEDSL file is neither hashed nor loaded; the merge commit reports that this regression fails under the old order (mutation-proved). Static review of the merged diff finds no separate missing-seal test and no valid-seal positive control. Next Claude slice: `tests/test_election_harness.py` only unless a test exposes a driver defect; add (1) a missing-seal negative proving no MEDSL hash/load and (2) a valid-seal positive control proving the correct seal permits ordered MEDSL verification/loading and result creation; mutation-prove removal of the missing-seal guard and moving label access before the seal check. Keep 2016 labels closed until these controls are merged with exact-head CI 4/4 and the separate output/label custody handoff is satisfied. ChatGPT did not run code/tests. PR #211's description says `test-evaluate` has not been run.

## 5. Independent hash verification and mismatch procedure

For every received raw output file, ChatGPT checks the exact relative path, byte count and SHA-256 against Claude's logged inventory. It also checks the inventory file's own SHA-256 and confirms the protocol/manifest identifiers match the frozen values above.

If **any** path is missing, unexpected, duplicated, truncated, changed, or has a byte-count/SHA-256 mismatch:

1. Stop review of the affected package/configuration immediately. Do not inspect or evaluate the mismatched file and do not open, request or accept held-out labels for that affected result.
2. Preserve the received bytes unchanged. Do not repair, normalize line endings, rename-and-substitute, re-hash a modified copy, or choose whichever version produces a passing result.
3. Report the exact expected and observed relative path, byte count and SHA-256, identify the failed inventory/manifest hash if applicable, and distinguish missing, extra, and mismatched files.
4. Mark the affected package/configuration **NOT EVALUABLE — OUTPUT INTEGRITY FAILURE** under this procedure. Do not calculate partial metrics or silently exclude the failed file unless the frozen protocol explicitly defines that exact deterministic treatment.
5. Ask Claude and the owner to resolve custody and record the discrepancy in the collaboration log. Any replacement, re-export, rerun, protocol amendment or new output freeze requires the applicable owner approval and a new complete inventory/attestation. The original failed artifacts and discrepancy record must be retained.

A matching hash establishes byte identity with the logged artifact; it does not establish predictive quality, correct mapping, or a favorable result.

## 6. Evaluation and reporting rules

- Identify the exact protocol, run/code commit, input-manifest hash, output-inventory hash and (only after authorized release) label-bundle hash.
- Report every required metric, every baseline comparison and every loss. Do not omit an unfavorable election, state, cutoff, metric or configuration.
- Keep calibration (2000/2004/2008), validation (2012) and held-out test (2016) results separate. Do not tune or adjust mappings after seeing test labels.
- Report missing outputs, stop rules, exclusions, failed stages and integrity problems explicitly.
- Distinguish model-generated/simulated outputs from published averages and observed election results.
- ChatGPT provides an independent report and flags issues; **Claude alone records official validation results** in the canonical project log. The owner reviews the record.

## 7. Current run status and authorization boundary

Claude's latest canonical log entry (23 November 2026, 23:20 IST) reports that the first calibration process exited silently with no output and no labels beyond training cycles 2000/2004/2008; a tracked background task was restarted from frozen commit `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` at approximately 17:43 UTC. This is Claude-reported process status. No completed calibration result, 2012 validation result, 2016 test-predict output inventory/hash, or held-out label handoff is recorded yet.

The owner's conditional run approval is “Go, once v0.2 is frozen”; Claude has reported that the freeze condition is met and that a tracked Package E calibration restart is underway from `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`. This does not authorize any other package, data, seed, configuration, rerun, or flag change. No completed output inventory/hash or held-out label handoff is recorded. Keep 2016 labels closed until the output inventory is independently hash-checked, the missing-seal negative and valid-seal positive-control tests are merged with exact-head CI 4/4, and the separate label handoff is logged. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory. M3 is **not** declared reached by this document; only Claude's explicit Notion declaration can do so.
