# M2 Runbook Command Inventory — Test Contract

**Status:** M2 command inventory and runbook-binding test contract. #157 is merged (CI `45042842927`, 4/4): inventory templates execute as subprocesses, and runbook code fences are bound to known command paths/option names; full argv/value/output-status matching remains a post-M2 strengthening item. M2 was Claude-confirmed reached at 23:43 IST on 22 November 2026.

**Baseline:** main `7432a10674a531d866d851de78402520e6a4eee8` (22 November 2026; includes #157/#159/#160/#161).

## 1. Test harness rules

- Use a fresh temporary root per test; no home-directory, repository-worktree or user project paths.
- Invoke `python -m agora.cli` in a subprocess from the source checkout with `PYTHONPATH=ROOT`; this is not a clean-install proof. Capture stdout, stderr and exit status separately.
- Pin the fixture ID to `synthetic-units-v1`; capture its manifest and payload hashes from the fixture loader/run record. Do not synthesize alternate data or modify the checked-in fixture.
- Each row below is one independently executable command invocation. Do not combine commands with shell chaining; a failure must identify the exact row.
- Assert stable exit code and stable public status/code text, not timestamps, random IDs, absolute paths or full JSON snapshots.
- For read-only commands, assert source file hashes/mtimes and directory contents are unchanged.
- For write commands, assert only the documented synthetic target changed. Denial cases must leave no partial store, backup or restore target.
- Assert the subprocess does not import `agora.sim` or `agora.sim.engine`; no network socket or connector is opened.
#157 now parses `OPERATOR_RUNBOOK.md` code fences and checks that command paths and option names exist in the inventory; it separately executes the inventory templates as subprocesses, checks exact inventory exit sets and names B12. It does not execute the extracted runbook argv or compare every value and required output/status token. This is follow-up traceability hardening, not a reversal of Claude's M2 confirmation.

## 2. Command inventory

| ID | Phase | Exact argv after `agora` | Expected exit | Required assertion |
|---|---|---|---:|---|
| P01 | Fixture catalogue | `pilot list` | 0 | Lists `synthetic-units-v1`; read-only; no project created. |
| P02 | Guided start | `pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>` | 0 | Completed result; nine named stages; run record exists; `data_class=synthetic`, `engine_invoked=false`, `validated_prediction_enabled=false`; report label is simulated/synthetic. |
| P03 | Unknown fixture denial | `pilot start --fixture __unknown_fixture__ --workdir <fresh-workdir>` | 2 | `FX_UNKNOWN_FIXTURE`; no project/store/workdir side effect. |
| P04 | Existing workdir denial | `pilot start --fixture synthetic-units-v1 --workdir <nonempty-workdir>` | 2 | `WORKDIR_NOT_EMPTY`; existing sentinel bytes unchanged; no project created. Implemented by merged #130. |
| P05 | Missing fixture argument | `pilot start --workdir <fresh-workdir>` | 2 | `FX_FIXTURE_REQUIRED`; no project/store/workdir side effect. |
| P06 | Symlinked workdir root | `pilot start --fixture synthetic-units-v1 --workdir <symlink-to-outside-empty-dir>` | 2 | `WORKDIR_UNSAFE_PATH`; merged #132 rejects the direct workdir-root symlink before creating the project; outside directory remains empty. |
| P07 | Symlinked fixture path | `pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>` | 2 | `FX_UNSAFE_PATH`; #132 rejects symlinked fixture directory/manifest/payload and #135 adds explicit `schema.json`/`binding.json` symlink coverage plus linked-directory catalogue filtering. |
| P08 | Empty fixture version | `pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>` | 2 | `FX_MANIFEST_INVALID`; merged #132 rejects empty/whitespace-only fixture versions before any project/store creation. |
| P09 | Manifest digest mismatch | `pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>` | 2 | `FX_MANIFEST_HASH_MISMATCH`; merged #132 independently pins the checked-in manifest digest, so editing manifest and payload together does not pass. |
| P10 | Symlinked workdir ancestor | `pilot start --fixture synthetic-units-v1 --workdir <symlink-parent>/new-workdir` | 2 | **Implemented in #135 (closed):** `WORKDIR_UNSAFE_PATH` before any directory creation; outside target untouched; lstat errors fail closed. |
| P11 | `..` crossing a workdir symlink | `pilot start --fixture synthetic-units-v1 --workdir <symlink-parent>/../new-workdir` | 2 | `WORKDIR_UNSAFE_PATH` before workdir/project creation; #139 covers lexical `..`, and #160 adds the intermediate-ancestor `lstat` PermissionError fail-closed mutation proof (CI `45048298704`, 4/4). |
| D01 | CSV import (standalone) | `data import-csv --project <project> --csv <synthetic-csv> --schema <schema> --role scenario_input` | 2 | `POLICY_DENIED`: the standalone command has no Principal and is refused in protected mode; nothing is written. Governed import occurs inside `pilot start` (P02). |
| D02 | Snapshot list | `data snapshots --project <project>` | 0 | Includes the exact import ID and metadata fields; no raw row values. |
| D03 | Import metadata | `data show --project <project> --import-id <import-id>` | 0 | Prints the selected manifest metadata only. |
| D04 | Rejected-row listing | `data rejected --project <project> --import-id <import-id>` | 0 | Emits only source row number, column name and stable error code; no raw rejected value. Empty rejected set is valid. |
| D05 | Unknown import | `data show --project <project> --import-id __missing__` | 2 | `IMPORT_NOT_FOUND`; source unchanged. |
| A01 | Audit timeline | `audit timeline --decisions <decisions-db> --audit <audit-db> --decision-id <decision-id>` | 0 | At least one selected stored transition/audit event; opaque identifiers only; includes read-only notice. |
| A02 | Missing timeline | `audit timeline --decisions <decisions-db> --audit <audit-db> --decision-id __missing__` | 1 | `NOT_FOUND:`; stores unchanged. |
| A03 | Anchor verification | `audit verify --audit <audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain` | 0 | `INTACT:`; JSON verdict is valid; includes `local sidecar` trust note. |
| A04 | Broken anchor/chain | `audit verify --audit <tampered-audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain` | 1 | `NOT INTACT:`; no repair or file mutation. |
| R01 | Reconciliation | `reconcile --decisions <decisions-db> --audit <audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain` | 0 | `OK:`; counts show zero missing/conflict/source-invalid/orphan; read-only stores unchanged. |
| R02 | Reconciliation blocked | `reconcile --decisions <decisions-db> --audit <tampered-audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain` | 2 | `RECONCILE_BLOCKED:`; no findings classified; no store changed. |
| H01 | Held outcomes | `outcomes held --decisions <decisions-db>` | 0 or 1 | Exit 0 only when none held (`OK:`); exit 1 when held (`HELD:`). JSON contains opaque IDs/state/reason only; read-only. |
| H02 | Held store blocked | `outcomes held --decisions <missing-or-invalid-db>` | 2 | `HELD_BLOCKED:`; nothing listed or changed. |
| B01 | Backup | `backup --project <synthetic-project> --dest <new-backup-dir>` | 0 | Backup manifest exists and says synthetic-only; verify expected chain/anchor metadata and hashes. #127 requires `run_record.json` with `data_class=synthetic`; this is not a per-file fixture allowlist. |
| B02 | Backup verification | `backup verify --backup <backup-dir>` | 0 | Plain success verdict; all manifest files and chain/anchor verified. |
| B03 | Restore | `restore --backup <backup-dir> --target <new-target-dir>` | 0 | On success every restored file matches the manifest and chain/anchor verify. On failure the partial target is removed; do not claim an atomic publish before the copy. |
| B04 | Unmarked source refusal | `backup --project <unmarked-project> --dest <new-backup-dir>` | 2 | `SOURCE_NOT_SYNTHETIC`; no destination or copied bytes. |
| B05 | In-tree symlink refusal | `backup --project <project-with-outside-symlink> --dest <new-backup-dir>` | 2 | `UNSAFE_PATH`; outside target not read/copied; no destination. |
| B06 | Malformed manifest refusal | `backup verify --backup <malformed-backup>` | 2 | `BACKUP_MANIFEST_INVALID`; stable blocked result, no uncaught traceback. |
| B07 | Restore tamper refusal | `restore --backup <tampered-backup> --target <new-target-dir>` | 2 | Stable `BACKUP_FILE_MODIFIED`, `BACKUP_NOT_INTACT` or `RESTORED_NOT_INTACT` result; partial target removed; backup unchanged. |
| B08 | Project-root symlink refusal | `backup --project <symlink-to-outside-project> --dest <new-backup-dir>` | 2 | `UNSAFE_PATH`; merged #134 rejects a directly symlinked/reparse-point project root before reading `run_record.json` or audit files. Parent-component symlinks and nested pre-read links still require separate B11 coverage. |
| B09 | Backup/restore root symlink refusal | `backup verify --backup <symlink-to-outside-backup>` or `restore --backup <backup-dir> --target <symlink-to-outside-target>` | 2 | `UNSAFE_PATH`; merged #134 rejects direct backup-root/data/manifest and restore-target symlink/reparse-point paths before manifest read or target write. Parent-component symlinks remain open; outside sentinel untouched. |
| B10 | Source snapshot changed during backup | `backup --project <synthetic-project-with-concurrent-anchored-writer> --dest <new-backup-dir>` | 2 | #148 holds the source writer lock; #159 maps B10 to `test_real_writer_cannot_append_while_backup_holds_the_snapshot` and observes the OS lock wrapper (CI `45045492204`, 4/4). A pre-syscall scheduling gap and factory-entry companion test remain; a kernel-confirmed contention probe is follow-up. |
| B11 | Backup parent/nested pre-read symlink | `backup --project <symlink-parent>/project-with-linked-run-record-or-chain --dest <new-backup-dir>` | 2 | **Implemented in merged #136/#139:** `UNSAFE_PATH` before outside `run_record.json`, chain or anchor reads; #136 adds ancestor/pre-read guards and #139 closes lexical `..` normalization. Exact-head CI `45006493190`/#139 `45011493565` passed 4/4. |
| B12 | Backup path lstat failure | `backup --project <path-with-unreadable-ancestor> --dest <new-backup-dir>` | 2 | Dedicated `test_B12_lstat_failure_on_an_intermediate_ancestor_fails_closed` is named in #157's coverage map and present on main; pilot workdir ancestor PermissionError denial/mutation proof is separately merged in #160. |
| B13 | `..` crossing a symlink component | `backup --project <symlink-parent>/../project --dest <new-backup-dir>` | 2 | **Merged #139:** both backup and pilot path walkers refuse any lexical `..` component before `abspath()` and use one captured `lstat()` result with `stat.S_ISLNK`; exact-head CI `45011493565` passed 4/4. Remaining pilot path-test gap: intermediate-ancestor lstat failure and plain-`..` pilot coverage. |

## 3. CLI contract notes

- Standalone `agora data import-csv` requires `--project`, `--csv`, `--schema`, and `--role` but is refused with `POLICY_DENIED` in protected mode because no Principal is supplied; governed import occurs inside `pilot start` (P02). D01 expects exit 2. `agora data snapshots`, `show` and `rejected` are read-only exact-import inspection commands.
- `agora data snapshots` requires `--project`; `show` and `rejected` also require `--import-id`.
- `agora outcomes held` is read-only. Exit 1 means a hold exists; it is not a command failure.
- `agora reconcile` is a read-only detector. Repair remains an API-only operation and is not part of this command inventory.
- `agora audit timeline` verifies the hash chain before displaying events; `agora audit verify` checks the chain against the local sidecar anchor. The sidecar cannot detect coordinated rollback of both chain and anchor.
#148 source snapshot locking and one manifest snapshot for verify/restore are merged (CI `45026655360`, 4/4); #154 strict manifest typing is merged (CI `45037406804`, 4/4); #159 updates B10 to the real-writer OS-lock test (CI `45045492204`, 4/4); #160 adds the pilot ancestor-lstat PermissionError mutation proof (CI `45048298704`, 4/4); #161 adds atomic run-record publication (CI `45051090990`, 4/4).

## 4. Post-M2 runbook-proof strengthening

Claude's 23:43 IST entry confirms M2 reached and records the completed synthetic rehearsal. For stronger future traceability, extend the test so it extracts and executes every `agora` code-fence command from `docs/OPERATOR_RUNBOOK.md`, compares the full argv/value sequence to one inventory row, asserts exact exit code and required stdout/stderr status tokens, and maps every row to a named proof. Current #157 checks command path/option-name binding and executes inventory templates; do not describe it as full literal-runbook execution.

No commands were executed to prepare this specification.


## 4. Run-record contract checks (API-level, no engine)

The command test loads the resulting `run_record.json` through `load_run_record(project)` and checks required fields, wrong types, synthetic data class, false engine/prediction flags, hashes, fixture blocks and stage results. #161 adds failure-atomic temp+fsync+exclusive hard-link publication (CI `45051090990`, 4/4). Remaining `RUN_PROVENANCE_SPEC.md` follow-up: exact integer `provenance_version`, timezone-aware RFC3339, manifest/envelope timestamp equality and complete report/export provenance fields.

Acceptance additionally requires exact repository SHA (not `unknown`), fixture ID/version, independently pinned manifest digest, exact input-manifest/scenario/schema/binding/ontology/policy fingerprints, stable timestamps/status enums, and failure-atomic record publication. Mutation proofs must show the test fails when each required-field, hash-cross-check, manifest binding or atomic-publication guard is removed.
