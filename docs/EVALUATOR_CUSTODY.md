# Evaluator Custody and Label-Release Procedure

**Status:** Draft governance procedure for owner review. This document defines the independent review boundary; it does not authorize a flag change, new dataset, additional run, label release before output freeze, or alteration of the frozen protocol or manifest.

## 1. Roles and separation

- **Project owner:** controls approvals and the release of sealed labels.
- **Claude:** run operator and data custodian. Claude executes the authorized stages, maintains the sealed-label boundary, creates the raw-output inventory and freeze attestation, and is the sole recorder of official validation results in the canonical project log.
- **ChatGPT:** independent reviewer for non-sensitive generated prediction outputs and checksum metadata when explicitly requested. May inspect state/year/cutoff-level prediction records and logs in PR #213 for integrity review; those artifacts contain no personal data or row-level outcome labels. Do not access raw source CSVs, private operational data or held-out outcome labels. Any label-based metric recalculation remains with a separately named owner-designated evaluator in the controlled environment. ChatGPT does not run Agora, tune mappings, alter outputs or access labels.

The evaluator must not participate in calibration or run execution in a way that could expose held-out labels or influence the preregistered configuration.

## 2. Frozen governing artifacts

The current frozen package is:

- **Protocol v0.2 commit:** `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`.
- **v0.2 run-spec SHA-256:** `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`.
- **Unchanged v0.1 protocol commit:** `6d06088cf7954bd41f003544f5ec61675389bcc1`; protocol file SHA-256 `b776948e14d6dc5c72262b3572365ebc0288fd632bc0bb13743d96fe7d8fea66`.
- **15-row dataset manifest:** finalized separately by PR #203 (exact head `3f85a1419921a142b3050d7094757bc32e19adba`, merge commit `3872f2401a8c6c6de097ad82a701414e8b1a26c9`); SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`, current/v0.2-freeze Git blob `ba684b0a1884f11e6331bcf5130b092c71c1303b`. The v0.1 protocol-file freeze commit `6d06088cf7954bd41f003544f5ec61675389bcc1` predates this status-column-only manifest finalization; the manifest is a separately identified frozen artifact included in v0.2 freeze commit `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`.
- **Package scope:** Package E only for the current evaluable benchmark; Package A is predeclared NOT EVALUABLE; Package R/M5 is dropped.
- **Prediction flag:** `VALIDATED_PREDICTION_ENABLED=False`.

The v0.2 additions are limited to the owner-pre-approved mappings, run command and backend. The splits, metrics, baselines, data and manifest remain unchanged. No document in this procedure amends the frozen protocol or manifest.

## 3. What ChatGPT receives

Before any held-out label release, the evaluator handoff is limited to:

1. The exact frozen protocol and run-spec version/commit/hash.
2. The exact 15-row dataset manifest and its SHA-256.
3. A non-sensitive inventory/checksum manifest for the authorized Package E outputs. Raw prediction/output files remain in owner-controlled custody and are not transferred to ChatGPT under the current no-real-data boundary.
4. A complete output inventory listing each relative path, byte count and SHA-256, plus the SHA-256 of the inventory itself. ChatGPT may independently verify the non-sensitive generated output bytes when explicitly requested; raw source CSVs and held-out labels remain in owner/custodian control.
5. Non-sensitive provenance needed to identify the run: run/configuration identifiers, stage identifiers, backend type, seed, exact code/protocol commits, timestamps and completion/failure status. Do not transfer raw source rows, held-out outcome labels, credentials or personal data to ChatGPT; the non-sensitive generated prediction records in PR #213 may be reviewed for byte integrity as requested.

The handoff is file-based and read-only. It does not include a live workspace, credentials, source-data workspace, execution environment, repository write access, or unrelated project files. ChatGPT must not infer missing fields. If an output cannot be interpreted from the frozen artifacts, the affected stage/configuration is reported NOT EVALUABLE.

PR #213 artifact status (24 November 2026): PR #213 merged into main at 5ec1bdd62d562cb8ef2ef58d54b61d717232e4ec from exact head 699ab1739aad4a654ae98e339de23e8b8321d6b7; exact-head CI 45312734872 passed 4/4. The merge adds nine output/log artifacts, SHA256SUMS and a results note under docs/validation_results/package_e. ChatGPT inspected only the SHA256SUMS text and compared the test_outputs.json and validation_outputs.json digest strings with the two Notion-recorded hashes; this is a metadata string comparison, not byte-level verification. ChatGPT did not fetch or hash raw output files, byte counts, prediction rows or labels. The package has no per-file byte counts, no separately hashed inventory, no complete run-configuration/provenance bundle, and no record of the failed first calibration attempt's exit status/partial-output disposition. The results note states no outcome labels were copied; ChatGPT did not inspect the JSON outputs to verify that statement. No owner-designated byte-verifier attestation or label-release handoff is recorded.

## 4. Output freeze and label boundary

Claude's 24 Nov 00:15/00:20 IST entries report the frozen v0.2 Package E sequence completed. The aggregate results note reports a 2012 MAE tie with worse RMSE and a 2016 held-out loss to the published-average and persistence baselines. ChatGPT did not inspect prediction rows, raw output bytes, byte counts or labels and did not independently recalculate any metric. The 2016 output digest string in SHA256SUMS matches the pre-label seal recorded in Notion; the 2012 validation digest string also matches the Notion-recorded value. These string comparisons do not verify the bytes.

The required order is:

1. Complete only the authorized Package E stages under the frozen v0.2 configuration. Do not add seeds, elections, packages, transformations or retries outside the frozen specification.
2. Collect **all** raw output files and run provenance. Do not filter, edit, regenerate, rename to conceal, or selectively omit an unfavorable output.
3. Compute SHA-256 and byte count for every raw output file. Create a complete relative-path inventory and hash the inventory itself.
4. At output freeze, record the exact protocol commit, run/code commit, input manifest hash, every output path/byte count/hash, output-inventory hash, timestamp and stage completion/failure state, plus an explicit statement that 2016 labels have not yet been opened. If a later authorized test-evaluate opens them, append a subsequent entry with the seal, command, code commit, label-bundle inventory/path/bytes/hash, release timestamp and result; do not rewrite the pre-release attestation.
5. A separately named owner-designated verifier checks the PR #213 output files against SHA256SUMS and the logged stage hashes inside the controlled environment. ChatGPT checks only non-sensitive checksum strings and provenance identifiers; it does not receive output bytes, source CSVs or outcome labels.
6. Claude's 24 Nov 00:20 IST entry reports that its authorized test-evaluate opened the 2016 labels after the sealed output hash matched. ChatGPT has not received or accessed those labels. Any later label-based evaluation must be performed by a separately named owner-approved evaluator inside the controlled data environment; no label bundle is transferred to ChatGPT under the current boundary.
7. Only after the independent output-integrity check and a separately authorized label release may the owner-designated evaluator compare frozen outputs with held-out labels under the frozen metrics. Claude alone records the official validation result. ChatGPT remains a documentation/metadata reviewer.

**Merged seal-order fix and test follow-up:** PR #211 merged at `2730903234196e9b38914ccb0fcab2de4e6c16ca` from exact head `1d90528de82d2a08f24ad38cf6c7c5c7bdd15eb0`; exact-head CI `45229437458` passed 4/4. PR #214 merged at current main `b111a4f918710f41650c659c40cad593419b02af` from exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5`; exact-head CI `45313425335` passed 4/4. Static main review confirms `test-evaluate` checks the output seal before MEDSL verification/loading. Review finding: the missing-seal test asserts `load_outcomes` is not called but does not instrument `h.sha256_file` for the MEDSL path; the positive asserts one load and result creation but not explicit output-read-before-MEDSL-hash order. Recommend those assertions as future hardening; this is not evidence the completed test-evaluate was unsealed. ChatGPT did not run code or tests.

## 5. Independent hash verification and mismatch procedure

The owner-designated byte verifier checks every raw output's exact relative path, byte count and SHA-256 against the logged inventory, including the inventory file's own SHA-256. ChatGPT checks only the non-sensitive inventory text and protocol/manifest identifiers; it does not fetch or hash raw output bytes.

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

Claude's 24 Nov 00:15/00:20 IST entries report Package E complete under frozen v0.2. The aggregate results note reports calibration k=0.24, a 2012 MAE tie with worse RMSE, and a 2016 held-out loss to the published-average and persistence baselines. The 2016 and 2012 output digest strings in SHA256SUMS match the two hashes recorded in Notion; ChatGPT compared the strings only and did not fetch/hash raw output bytes, byte counts or prediction rows. The package lacks a complete per-file byte-counted inventory, separately hashed inventory, full run configuration/provenance and the first calibration failure's exit/partial-output disposition. A separately named owner-designated verifier must complete byte/inventory review in the controlled environment. No label bundle was transferred to ChatGPT.

The owner's conditional run approval was “Go, once v0.2 is frozen”; Claude reports the single Package E run completed under frozen v0.2. The first calibration process reportedly exited silently and was restarted from the same frozen commit; its exit status, logs and partial-output disposition remain undocumented. No additional package, seed, configuration or rerun is authorized. ChatGPT completed the requested non-sensitive output-integrity review from PR #213 without accessing labels or raw source CSVs. A separate label-bundle handoff is needed only for any future independent metric recalculation. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.
