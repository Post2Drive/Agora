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
3. The non-sensitive generated Package E prediction/output artifacts and checksum manifest published in PR #213. ChatGPT may retrieve and verify only those generated outputs/logs when explicitly requested; raw source CSVs, private operational data and held-out outcome labels remain outside ChatGPT's access.
4. A complete output inventory listing each relative path, byte count and SHA-256, plus the SHA-256 of the inventory itself. ChatGPT may independently verify the non-sensitive generated output bytes when explicitly requested; raw source CSVs and held-out labels remain in owner/custodian control.
5. Non-sensitive provenance needed to identify the run: run/configuration identifiers, stage identifiers, backend type, seed, exact code/protocol commits, timestamps and completion/failure status. Do not transfer raw source rows, held-out outcome labels, credentials or personal data to ChatGPT; the non-sensitive generated prediction records in PR #213 may be reviewed for byte integrity as requested.

The handoff is file-based and read-only. It does not include a live workspace, credentials, source-data workspace, execution environment, repository write access, or unrelated project files. ChatGPT must not infer missing fields. If an output cannot be interpreted from the frozen artifacts, the affected stage/configuration is reported NOT EVALUABLE.

PR #213 artifact integrity review (24 November 2026): PR #213 merged into main at `5ec1bdd62d562cb8ef2ef58d54b61d717232e4ec` from exact head `699ab1739aad4a654ae98e339de23e8b8321d6b7`; exact-head CI `45312734872` passed 4/4. ChatGPT independently recomputed SHA-256 and byte counts for all nine UTF-8 repository artifacts against `SHA256SUMS`; all nine match. The `SHA256SUMS` file is 755 bytes and has SHA-256 `7ac2ffece93b4c923e26d35f8b59fc24c38373d8ad515b7f7d8165ca1c9a8c7d` (recorded separately because it does not self-list).

| File | Bytes | SHA-256 |
|---|---:|---|
| `calibrate.log` | 316 | `67208e573d499fdbec65fa368eb7285c188ce3c91c56a9f52fef74ed87045a2a` |
| `calibration.json` | 268 | `1af5f06bcb2b3709fc03d32f3b82b6e638a3dff77f08ae56ef64f0e1e673d9d6` |
| `test_evaluate.log` | 591 | `2e64217c6eae6052c43b15974febe9b5c414370b0f38b156d854d284bd46d7bc` |
| `test_outputs.json` | 22,165 | `109e055089e95f0e1be14bae547ceaaa1219bf045a5452e824d607caf56ac989` |
| `test_predict.log` | 146 | `e2e6aa87d9e8d58d6367730fec19deb30aebcd8e3dd51c59c5444382b2528714` |
| `test_result.json` | 594 | `f23fff7a83ff2b0fa0c7c64f99d44dbe864d0b271d541fe13196e74adcab60d0` |
| `validate.log` | 599 | `c02f76d06e48b578d2c9c86271d214c4368b49a2e7327ff8ddb1719cc42aa704` |
| `validation_outputs.json` | 20,476 | `d62205c326fc27b746326c65b082f17b7b300a952ecf94e20644ebf56111f70a` |
| `validation_result.json` | 600 | `8807559113c484cdc948aa82d59518738879b04f7c8329f10227eb5b4b3346da` |

The 2016 `test_outputs.json` hash matches the pre-label seal in Notion; `validation_outputs.json` matches the logged 2012 hash. ChatGPT fetched the exact main-branch bytes of all nine non-sensitive PR #213 output/log artifacts, recomputed each byte count and SHA-256 against SHA256SUMS, and all nine matched. SHA256SUMS itself is 755 bytes with SHA-256 `7ac2ffece93b4c923e26d35f8b59fc24c38373d8ad515b7f7d8165ca1c9a8c7d`. ChatGPT did not access held-out outcome labels or raw source CSVs and did not recalculate metrics.

The generated 2012 prediction file has 141 rows; two notes identify District of Columbia and Idaho at cutoff 2012-10-09 as having no published average on or before cutoff, matching the 139 evaluated observations. The 2016 prediction file has 153 rows; one note identifies District of Columbia at cutoff 2016-10-11, matching the 152 evaluated observations. These three cutoff-level records do not enumerate the separate seven state-cycle exclusions in the aggregate results note; the exact seven state/year pairs and their individual manifest/cutoff reasons are unavailable in the committed artifacts.

Claude's 23 Nov 2026 23:20 IST log reports that the first calibration process died silently after the shell reaped it, produced no output, and opened no labels beyond training years 2000/2004/2008; a tracked restart from frozen commit `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` began at approximately 17:43 UTC. This is an operator report, not independently verified process telemetry. The first attempt's exact start/end, exit code, original log references/hashes, partial-output inventory/hash/disposition, and separate restart/stop-rule rationale were not captured. The retained successful retry is distinct: `calibrate.log` (316 bytes; SHA-256 `67208e573d499fdbec65fa368eb7285c188ce3c91c56a9f52fef74ed87045a2a`) records `exit=0` and output SHA-256 `6cffe65c7fe12806e34f34d57c7a2fe116d0888c6ed9dfa1b5ce3015a927c8fc`; `calibration.json` is 268 bytes with SHA-256 `1af5f06bcb2b3709fc03d32f3b82b6e638a3dff77f08ae56ef64f0e1e673d9d6`. These successful-retry artifacts do not establish the first process's exit status or partial-output disposition.

## 4. Output freeze and label boundary

Claude's 24 Nov 00:15/00:20 IST entries report the frozen v0.2 Package E sequence completed. The aggregate results note reports a 2012 MAE tie with worse RMSE and a 2016 held-out loss to the published-average and persistence baselines. ChatGPT inspected the nine non-sensitive generated prediction/output files and logs in PR #213, independently recomputed their byte counts and SHA-256 values against SHA256SUMS, and all matched. ChatGPT did not access held-out labels or raw source CSVs and did not recalculate metrics. The exact seven-entry state-cycle ledger remains unavailable; the first attempt's exact timestamps, exit code, logs/hashes and partial-output disposition remain uncaptured. See the traceability record above for the Claude-reported silent exit/restart and the distinct successful-retry artifacts.

The required order is:

1. Complete only the authorized Package E stages under the frozen v0.2 configuration. Do not add seeds, elections, packages, transformations or retries outside the frozen specification.
2. Collect **all** raw output files and run provenance. Do not filter, edit, regenerate, rename to conceal, or selectively omit an unfavorable output.
3. Compute SHA-256 and byte count for every raw output file. Create a complete relative-path inventory and hash the inventory itself.
4. At output freeze, record the exact protocol commit, run/code commit, input manifest hash, every output path/byte count/hash, output-inventory hash, timestamp and stage completion/failure state, plus an explicit statement that 2016 labels have not yet been opened. If a later authorized test-evaluate opens them, append a subsequent entry with the seal, command, code commit, label-bundle inventory/path/bytes/hash, release timestamp and result; do not rewrite the pre-release attestation.
5. Completed by ChatGPT on 24 Nov: the nine non-sensitive PR #213 output/log files were fetched from current main and their exact byte counts and SHA-256 values independently matched against SHA256SUMS. The SHA256SUMS file itself is 755 bytes, SHA-256 `7ac2ffece93b4c923e26d35f8b59fc24c38373d8ad515b7f7d8165ca1c9a8c7d`. Any future label-based metric recalculation remains with a separately named owner-designated evaluator in the controlled environment; no label bundle was transferred to ChatGPT.
6. Claude's 24 Nov 00:20 IST entry reports that its authorized test-evaluate opened the 2016 labels after the sealed output hash matched. ChatGPT has not received or accessed those labels. Any later label-based evaluation must be performed by a separately named owner-approved evaluator inside the controlled data environment; no label bundle is transferred to ChatGPT under the current boundary.
7. Only after the independent output-integrity check and a separately authorized label release may the owner-designated evaluator compare frozen outputs with held-out labels under the frozen metrics. Claude alone records the official validation result. ChatGPT remains a documentation/metadata reviewer.

**Merged seal-order fix and test follow-up:** PR #211 merged at `2730903234196e9b38914ccb0fcab2de4e6c16ca` from exact head `1d90528de82d2a08f24ad38cf6c7c5c7bdd15eb0`; exact-head CI `45229437458` passed 4/4. PR #214 merged at current main `b111a4f918710f41650c659c40cad593419b02af` from exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5`; exact-head CI `45313425335` passed 4/4. Static main review confirms `test-evaluate` checks the output seal before MEDSL verification/loading. Review finding: the missing-seal test asserts `load_outcomes` is not called but does not instrument `h.sha256_file` for the MEDSL path; the positive asserts one load and result creation but not explicit output-read-before-MEDSL-hash order. Recommend those assertions as future hardening; this is not evidence the completed test-evaluate was unsealed. ChatGPT did not run code or tests.

## 5. Independent hash verification and mismatch procedure

The nine-file output byte-verification step is complete for the exact PR #213 main-branch artifacts listed above. Any later artifact revision or replacement requires a new inventory and the same integrity check before use. Any label-based metric recalculation remains with a separately named owner-designated evaluator; ChatGPT does not access held-out labels.

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

Claude's 24 Nov 00:15/00:20 IST entries report Package E complete under frozen v0.2. The aggregate results note reports calibration k=0.24, a 2012 MAE tie with worse RMSE, and a 2016 held-out loss to the published-average and persistence baselines. ChatGPT fetched the nine non-sensitive PR #213 output/log artifacts from main and independently verified every byte count and SHA-256 against SHA256SUMS; all matched. ChatGPT did not access held-out labels or raw source CSVs and did not recalculate metrics. The byte-counted inventory and SHA256SUMS hash are recorded above. Full run-level configuration/provenance, the separate seven state-cycle exclusions and first calibration failure's exit/log/partial-output disposition remain outstanding. No label bundle was transferred to ChatGPT.

The owner's conditional run approval was “Go, once v0.2 is frozen”; Claude reports the single Package E run completed under frozen v0.2. Claude's log reports that the first calibration process died silently and was restarted as a tracked task from the same frozen commit at approximately 17:43 UTC. The exact first-attempt timestamps, exit code, logs/hashes and partial-output disposition were not captured. The successful retry's `calibrate.log` (`exit=0`) and `calibration.json` are separate retained artifacts; they do not establish the first process's status. No additional package, seed, configuration or rerun is authorized. ChatGPT independently verified the nine non-sensitive PR #213 output/log artifacts by exact byte count and SHA-256 against SHA256SUMS; all matched. No raw source CSVs or held-out labels were accessed and no metrics were recalculated. A separate owner-designated evaluator remains required for any future label-based metric evaluation. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.
