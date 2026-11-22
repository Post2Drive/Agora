# M2 Synthetic Pilot Dress Rehearsal — Script and Evidence Record

**Status:** Planning template only; no rehearsal has been run. Local synthetic M2 implementation is owner-approved. This document does not authorise real data, simulation, study changes, connectors, credentials or external write-back.

**Drafting baseline:** main `f0bbabd6c9ff0d43500ad57acf4081f80bfd6beb` (22 November 2026). PR #127 is still in review; update refusal-code expectations after it merges.

## 1. Objective

Demonstrate that an operator can start a fresh local synthetic pilot from the pinned fixture, inspect run/audit evidence, list held outcomes and reconciliation status, and complete a backup/restore/tamper drill with clear fail-closed stops. This is governance/operator-usability evidence, not a prediction, demand, sales, causal or production-readiness test.

## 2. Entry conditions — all required

- [ ] Claude confirms the exact M2 rehearsal build and main SHA; all relevant PRs are merged at exact heads.
- [ ] Exact-head GitHub Actions matrix is green on Ubuntu/Windows and Python 3.11/3.12.
- [ ] The automated test executes every applicable row in `M2_RUNBOOK_COMMAND_INVENTORY.md`.
- [ ] Fixture ID `synthetic-units-v1`, manifest digest and payload hashes are independently pinned and recorded.
- [ ] Fixture symlink, truly-empty-workdir and clean-checkout installation gates are closed.
- [ ] Run-record provenance validation and failure-atomic publication are complete; both engine/prediction flags are false.
- [ ] Backup hardening is merged and tested for synthetic-source allowlisting, symlink refusal, manifest validation, snapshot consistency and post-copy hash verification.
- [ ] Reconciliation and held-outcome commands and their clean/blocked outcomes are tested.
- [ ] A disposable temporary workspace is available; no user project or existing study will be reused.
- [ ] The owner has explicitly approved this specific rehearsal window and scope. Stop if approval is absent or ambiguous.

## 3. Safety boundary

Use only the checked-in fixture and temporary directories created for this rehearsal. No real/personal/customer data, credentials, model endpoint, network connector, cloud storage, external write-back or user project. Do not run `agora run`, `calibrate`, `backtest`, `forecast`, or any simulation/engine command. Do not touch `agora/sim/**`, NCC, Nutrivance, the eight neutral factorial runs or E0_C0_D0. Keep `VALIDATED_PREDICTION_ENABLED=False`.

Any refusal, unexpected import, network attempt, path escape, hash mismatch, anchor failure or partial write is a stop condition. Preserve evidence; do not retry by deleting or rewriting the source.

## 4. Execution script — use exact merged runbook commands

Run each command separately. Capture exit status, stdout, stderr, start/end timestamps and hashes. Do not paste raw data into the evidence log.

1. **Build and fixture:** record `git rev-parse HEAD`, CLI/Python version and OS. Run `agora pilot list`. Record fixture ID/version, manifest digest and payload hashes using the approved read-only inspection method.
2. **Fresh pilot:** create a brand-new empty work directory. Run `agora pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>`. Confirm every expected stage status and stable reason code. Validate `run_record.json`; record its SHA-256, exact repository SHA, fixture hashes, `data_class=synthetic`, `engine_invoked=false` and `validated_prediction_enabled=false`. Confirm the report is labelled simulated/synthetic and contains no raw rows.
3. **Governance evidence:** run audit timeline for the opaque decision ID; run chain/anchor verification with recorded chain ID; run reconciliation; run held-outcome listing. Treat held-list exit 1 as a hold, not a review or permission to rely on the outcome. Record opaque IDs, reason codes, counts, verdicts and exit statuses only.
4. **Backup:** create a new backup destination; run backup and backup verify. Record manifest/file hashes, chain ID, anchor sequence/head and synthetic-only proof. Do not include event payloads.
5. **Restore:** restore into a second new empty directory. Re-hash every restored file against the manifest and verify chain/anchor. Confirm original project and backup hashes remain unchanged.
6. **Tamper — disposable copies only:** in a separate backup copy, change one byte in a non-audit file; verify/restore must block and publish no target. In another copy, alter an audit event or anchor; verification must report not intact/blocked. In a separate disposable project, add an outside-root symlink; backup must refuse without reading/copying the target. Never tamper with the source project or original backup.
7. **Close:** re-verify source, original backup and successful restore hashes. Confirm no network, connector, engine or `agora.sim` import. Store redacted evidence and outputs in the agreed project log. Wait for Claude's exact M2 confirmation; do not declare M2 reached.

## 5. Evidence record

| Field | Value |
|---|---|
| Rehearsal date/time (UTC) | TBD |
| Operator / owner approval reference | TBD |
| Main SHA | TBD |
| Merged PRs / exact-head CI run IDs | TBD |
| OS / Python / CLI version | TBD |
| Fixture ID / version | TBD |
| Fixture manifest SHA-256 / payload hashes | TBD |
| Temporary workdir reference | TBD |
| Pilot exit / overall status | TBD |
| Stage results / denial stops | TBD |
| Run-record SHA-256 / schema verdict | TBD |
| Opaque decision ID/version | TBD |
| Audit chain ID / sequence / head hash | TBD |
| Anchor verdict / trust note | TBD |
| Reconciliation exit / counts | TBD |
| Held-outcome exit / reason codes | TBD |
| Backup manifest / file hashes | TBD |
| Restore verification verdict | TBD |
| Tamper cases / expected and observed codes | TBD |
| Source and backup unchanged checks | TBD |
| Engine / validated-prediction flags | false / false |
| Network, connectors, external writes | None |
| Deviations / incidents / blocked steps | TBD |
| Operator sign-off | TBD |
| Claude M2 confirmation link / timestamp | TBD |

## 6. Stop rules

- Never repair, re-anchor, delete or rewrite an unexpected audit/anchor state during rehearsal.
- If output differs from the tested runbook, stop and preserve the workspace.
- If any file outside the temporary root is accessed or real data/credentials appear, stop and report without copying content.
- If restore verification fails, preserve the original backup and follow only the tested staged-target cleanup contract.
- A local sidecar cannot detect coordinated rollback of both database and anchor; record this limitation.
- A green rehearsal is evidence for Claude's milestone assessment, not ChatGPT's declaration of M2 completion.
