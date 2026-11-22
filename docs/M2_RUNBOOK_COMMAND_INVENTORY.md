# M2 Runbook Command Inventory — Test Contract

**Status:** Draft acceptance inventory for Claude's M2 item 8. This is a documentation contract, not evidence that commands have been executed. The automated test must run only in temporary directories using the checked-in synthetic fixture. It must never invoke the simulation engine, network, connectors, credentials, real data or `agora/sim/**`.

**Baseline:** main `15a92c56fdac14bb6266eec4acbd15b528d4b035` (22 November 2026). #127 backup hardening, #130 partial strict run-record loader/non-empty-workdir guard and #132 fixture integrity/direct workdir-root symlink hardening are merged. Exact-head CI for #132 (`44997320523`) passed 4/4. Clean-install proof and workdir-ancestor symlink coverage remain open.

## 1. Test harness rules

- Use a fresh temporary root per test; no home-directory, repository-worktree or user project paths.
- Resolve the installed CLI entry point in a subprocess. Capture stdout, stderr and exit status separately.
- Pin the fixture ID to `synthetic-units-v1`; capture its manifest and payload hashes from the fixture loader/run record. Do not synthesize alternate data or modify the checked-in fixture.
- Each row below is one independently executable command invocation. Do not combine commands with shell chaining; a failure must identify the exact row.
- Assert stable exit code and stable public status/code text, not timestamps, random IDs, absolute paths or full JSON snapshots.
- For read-only commands, assert source file hashes/mtimes and directory contents are unchanged.
- For write commands, assert only the documented synthetic target changed. Denial cases must leave no partial store, backup or restore target.
- Assert the subprocess does not import `agora.sim` or `agora.sim.engine`; no network socket or connector is opened.
- The test must fail if a documented command row is silently removed, duplicated, or changes its argv, expected exit code or required status token. Keep this file's inventory machine-readable by stable IDs in the table.

## 2. Command inventory

| ID | Phase | Exact argv after `agora` | Expected exit | Required assertion |
|---|---|---|---:|---|
| P01 | Fixture catalogue | `pilot list` | 0 | Lists `synthetic-units-v1`; read-only; no project created. |
| P02 | Guided start | `pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>` | 0 | Completed result; nine named stages; run record exists; `data_class=synthetic`, `engine_invoked=false`, `validated_prediction_enabled=false`; report label is simulated/synthetic. |
| P03 | Unknown fixture denial | `pilot start --fixture __unknown_fixture__ --workdir <fresh-workdir>` | 2 | `FX_UNKNOWN_FIXTURE`; no project/store/workdir side effect. |
| P04 | Existing workdir denial | `pilot start --fixture synthetic-units-v1 --workdir <nonempty-workdir>` | 2 | `WORKDIR_NOT_EMPTY`; existing sentinel bytes unchanged; no project created. Implemented by merged #130. |
| P05 | Missing fixture argument | `pilot start --workdir <fresh-workdir>` | 2 | `FX_FIXTURE_REQUIRED`; no project/store/workdir side effect. |
| P06 | Symlinked workdir root | `pilot start --fixture synthetic-units-v1 --workdir <symlink-to-outside-empty-dir>` | 2 | `WORKDIR_UNSAFE_PATH`; merged #132 rejects the direct workdir-root symlink before creating the project; outside directory remains empty. |
| P07 | Symlinked fixture path | `pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>` | 2 | `FX_UNSAFE_PATH`; merged #132 rejects a symlinked fixture directory, manifest or payload file before reading it. Add explicit per-file coverage for `schema.json` and `binding.json`; current test covers `units.csv` and `manifest.json`. |
| P08 | Empty fixture version | `pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>` | 2 | `FX_MANIFEST_INVALID`; merged #132 rejects empty/whitespace-only fixture versions before any project/store creation. |
| P09 | Manifest digest mismatch | `pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>` | 2 | `FX_MANIFEST_HASH_MISMATCH`; merged #132 independently pins the checked-in manifest digest, so editing manifest and payload together does not pass. |
| P10 | Symlinked workdir ancestor | `pilot start --fixture synthetic-units-v1 --workdir <symlink-parent>/new-workdir` | 2 | **Not implemented:** expect `WORKDIR_UNSAFE_PATH` before any directory creation; prove an outside sentinel/target remains untouched. #132 checks only the final `workdir` component, so a non-existent child beneath a symlinked parent can still be created outside the intended root. |
| D01 | CSV import | `data import-csv --project <project> --csv <synthetic-csv> --schema <schema> --role scenario_input` | 0 | Prints `imported:` plus opaque import ID; no row values printed. |
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
| B08 | Project-root symlink refusal | `backup --project <symlink-to-outside-project> --dest <new-backup-dir>` | 2 | Proposed stable `UNSAFE_PATH` before reading `run_record.json`/audit files; outside source not read/copied. |
| B09 | Backup/restore root symlink refusal | `backup verify --backup <symlink-to-outside-backup>` or `restore --backup <backup-dir> --target <symlink-to-outside-target>` | 2 | Proposed stable `UNSAFE_PATH` before manifest read or target write; outside sentinel untouched. |
| B10 | Source snapshot changed during backup | `backup --project <synthetic-project-with-concurrent-anchored-writer> --dest <new-backup-dir>` | 2 | `SNAPSHOT_CHANGED`; destination removed/not retained; source pair unchanged except for the separately controlled writer append; captured chain ID/sequence/head must match the source verdict. Use a deterministic synchronization hook in the test harness, not a timing sleep. |

## 3. CLI contract notes

- `agora data import-csv` requires `--project`, `--csv`, `--schema`, and `--role`; allowed roles are `context`, `scenario_input`, `calibration`, `validation`, and `sealed_holdout`. The test uses only `scenario_input` on the checked-in synthetic fixture.
- `agora data snapshots` requires `--project`; `show` and `rejected` also require `--import-id`.
- `agora outcomes held` is read-only. Exit 1 means a hold exists; it is not a command failure.
- `agora reconcile` is a read-only detector. Repair remains an API-only operation and is not part of this command inventory.
- `agora audit timeline` verifies the hash chain before displaying events; `agora audit verify` checks the chain against the local sidecar anchor. The sidecar cannot detect coordinated rollback of both chain and anchor.
- Backup/restore rows B01–B09 are reconciled to #127's merged behavior. B08/B09 specify remaining project/backup/restore-target root-path symlink hardening; they are not implemented on main, and Claude's next code slice is the backup root-symlink/snapshot-lock work. #130 adds partial strict run-record checks but not the full run-provenance schema. #132 completes P06–P09 direct fixture/workdir-root hardening; P10 records the remaining workdir-ancestor symlink bypass.

## 4. Acceptance gate for item 8

Item 8 is complete only when a test executes every applicable row from a clean temporary synthetic workspace, verifies the required exit/status contract and no-side-effect guarantees, and fails under deliberate mutations to the runbook command, flag, expected output, or inventory membership. A prose-only checklist or a test that mocks the command's result does not satisfy this gate.

No commands were executed to prepare this specification.


## 4. Run-record contract checks (API-level, no engine)

The command test must also load the resulting `run_record.json` through `load_run_record(project)` and reject missing required keys, wrong types (including booleans where integers are required), non-synthetic data class, either engine/prediction flag true, malformed SHA-256 values, malformed fixture blocks/file-hash maps and malformed stage results. Merged #130 implements part of this strict loader; #132 adds independently pinned fixture manifest and file hashes, but the run record still does not require the full `RUN_PROVENANCE_SPEC.md` envelope, validate the fixture block/map deeply, or publish failure-atomically.

Acceptance additionally requires exact repository SHA (not `unknown`), fixture ID/version, independently pinned manifest digest, exact input-manifest/scenario/schema/binding/ontology/policy fingerprints, stable timestamps/status enums, and failure-atomic record publication. Mutation proofs must show the test fails when each required-field, hash-cross-check, manifest binding or atomic-publication guard is removed.
