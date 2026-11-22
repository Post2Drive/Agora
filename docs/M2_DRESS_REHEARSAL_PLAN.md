# M2 Synthetic Pilot Dress Rehearsal — Script and Evidence Record

**Status:** Completed synthetic rehearsal evidence recorded by Claude at 23:43 IST on 22 November 2026; M2 is Claude-confirmed reached. This document records that rehearsal and does not authorise another run, real data, simulation, study changes, connectors, credentials or external write-back.

**Rehearsal main:** `7432a10674a531d866d851de78402520e6a4eee8` (22 November 2026). Exact-head CI: #157 `45042842927`, #159 `45045492204`, #160 `45048298704`, #161 `45051090990`, and Claude's M2 confirmation run `45052033418` all passed 4/4.

## 1. Objective

Demonstrate that an operator can start a fresh local synthetic pilot from the pinned fixture, inspect run/audit evidence, list held outcomes and reconciliation status, and complete a backup/restore/tamper drill with clear fail-closed stops. This is governance/operator-usability evidence, not a prediction, demand, sales, causal or production-readiness test.

## 2. Recorded entry evidence

- [x] Claude's exact M2 confirmation names main `7432a10674a531d866d851de78402520e6a4eee8`; M2 CI run `45052033418` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- [x] Merged implementation heads relevant to the rehearsal include #144/#145 clean install/start, #157 runbook/inventory binding, #159 B10 mapping, #160 pilot ancestor-lstat denial proof and #161 atomic run-record publication; exact-head CI for #157/#159/#160/#161 passed 4/4.
- [x] The test suite's runbook inventory templates execute as local subprocesses and assert the simulation engine was not loaded; #157 also binds code-fenced runbook command paths/option names.
- [x] Fixture ID `synthetic-units-v1`; logged manifest hash `sha256:1bc5020b9874a8065c787c6e6df756fad4d4c25ffd402b5e5149843be465f18f`; binding/schema/CSV hash prefixes are recorded below.
- [x] Fresh temporary workdir `/tmp/reh`; no user project or existing study reused.
- [x] Run record is written atomically by #161; engine and validated-prediction flags are false. Strict provenance-version/timezone/report completeness remains a follow-up limitation.
- [x] Reconciliation, held-outcome listing, backup, verify, restore and disposable tamper cases are recorded below.
- [ ] Separate rehearsal-window approval reference and operator sign-off are not reproduced in Claude's 23:43 entry; do not infer them from CI or milestone confirmation.


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
6. **Tamper — disposable copies only:** in a separate backup copy, change one byte in a non-audit file; verify/restore must block and publish no target. In another copy, alter an audit event or anchor; verification must report not intact/blocked. In a separate disposable project, add an in-tree symlink and test project/backup/target root symlinks; backup/verify/restore must refuse before reading or writing outside the temporary root. Never tamper with the source project or original backup.
7. **Close:** re-verify source, original backup and successful restore hashes. Confirm no network, connector, engine or `agora.sim` import. Store redacted evidence and outputs in the agreed project log. Wait for Claude's exact M2 confirmation; do not declare M2 reached.

## 5. Evidence record

| Field | Value |
|---|---|
| Rehearsal date/time | 22 November 2026, 23:43 IST (18:13 UTC; Claude log entry) |
| Operator / owner approval reference | M2 owner-approved local synthetic scope in the collaboration log; separate rehearsal-window reference/sign-off not reproduced in the 23:43 entry |
| Main SHA | `7432a10674a531d866d851de78402520e6a4eee8` |
| Merged PRs / exact-head CI run IDs | #157 `45042842927`, #159 `45045492204`, #160 `45048298704`, #161 `45051090990`; M2 confirmation `45052033418` — all 4/4 |
| OS / Python / CLI version | Not specified in the log entry |
| Fixture ID / version | `synthetic-units-v1`; fixture version not specified |
| Fixture manifest SHA-256 / payload hashes | Manifest `sha256:1bc5020b9874a8065c787c6e6df756fad4d4c25ffd402b5e5149843be465f18f`; binding `26ce5a25c9057015`, schema `ecb46b903dcda2de`, units.csv `69c649f1a11594ca` (logged prefixes) |
| Temporary workdir reference | `/tmp/reh` |
| Pilot exit / overall status | `pilot list` rc0; `pilot start` completed, nine stages OK, rc0 |
| Stage results / denial stops | Nine stages OK; no denial stop on the happy path |
| Run-record SHA-256 / schema verdict | `aeb5b005ac297513…` (prefix only in log); atomic record publish on main via #161 |
| Opaque decision ID/version | `decision-synthetic-001`; version not stated |
| Audit chain ID / sequence / head hash | `synthetic-pilot-chain`; sequence 4; full head hash not reproduced |
| Anchor verdict / trust note | `INTACT`, `anchored_verified`, `local_sidecar`, rc0 |
| Reconciliation exit / counts | rc0; matched 2; conflict/missing/orphan 0 |
| Held-outcome exit / reason codes | rc0; held 0; outcomes 1 |
| Backup manifest / file hashes | 11 files; chain INTACT; detailed manifest/file hash list not reproduced |
| Restore verification verdict | Backup verify OK; restore OK for 11 files; rc0 |
| Tamper cases / expected and observed codes | Event edit: NOT INTACT rc1; reconcile CHAIN_INVALID rc2. Last chain row deletion: truncation_detected (chain 3 < anchor 4) rc1. Backup CSV byte append: BACKUP_FILE_MODIFIED on verify and restore, rc2. Direct UPDATE on live chain refused by append-only trigger. |
| Source and backup unchanged checks | Live chain direct UPDATE refused; tamper cases used copied/disposable backup material; full source/backup hash comparison not reproduced |
| Engine / validated-prediction flags | false / false |
| Network, connectors, external writes | None reported; rehearsal described as local synthetic only |
| Deviations / incidents / blocked steps | Anchor trust is local-sidecar only; coordinated rollback of chain and sidecar together is not detected. No simulation engine call. |
| Operator sign-off | Not stated in the log entry |
| Claude M2 confirmation link / timestamp | AI Collaboration Log, Claude 23:43 IST entry: https://app.notion.com/p/41bd77d284ed81dfa2e7dd34a1dd5fff |


## 6. Stop rules

- Never repair, re-anchor, delete or rewrite an unexpected audit/anchor state during rehearsal.
- If output differs from the tested runbook, stop and preserve the workspace.
- If any file outside the temporary root is accessed or real data/credentials appear, stop and report without copying content.
- If restore verification fails, preserve the original backup and follow only the tested staged-target cleanup contract.
- A local sidecar cannot detect coordinated rollback of both database and anchor; record this limitation.
- Claude's exact 23:43 IST confirmation already records M2 reached; this evidence record does not let ChatGPT independently declare the milestone or authorise production/external action.
