# M2 Runbook Command Inventory — Test Contract

**Status:** Draft acceptance inventory for Claude's M2 item 8. This is a documentation contract, not evidence that commands have been executed. The automated test must run only in temporary directories using the checked-in synthetic fixture. It must never invoke the simulation engine, network, connectors, credentials, real data or `agora/sim/**`.

**Baseline:** main `f0bbabd6c9ff0d43500ad57acf4081f80bfd6beb` (22 November 2026). #127 backup hardening is still a draft at the time of this inventory; backup refusal-code expectations below are conditional on #127 merging unchanged.

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
| P03 | Unknown fixture denial | `pilot start --fixture __unknown_fixture__ --workdir <fresh-workdir>` | 2 | `FX_FIXTURE_REQUIRED` or the stable unknown-fixture code defined by the merged CLI; no store/workdir side effect. Pin the exact code after reading the merged implementation. |
| P04 | Existing workdir denial | `pilot start --fixture synthetic-units-v1 --workdir <nonempty-workdir>` | 2 | `WORKDIR_NOT_EMPTY`; existing sentinel bytes unchanged; no project created. |
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
| B01 | Backup | `backup --project <synthetic-project> --dest <new-backup-dir>` | 0 | Backup manifest exists and says synthetic-only; verify expected chain/anchor metadata and hashes. This row depends on #127's merged synthetic-source gate and path hardening. |
| B02 | Backup verification | `backup verify --backup <backup-dir>` | 0 | Plain success verdict; all manifest files and chain/anchor verified. |
| B03 | Restore | `restore --backup <backup-dir> --target <new-target-dir>` | 0 | Target is published only after all manifest hashes and chain/anchor verify; every restored file matches manifest. |
| B04 | Unmarked source refusal | `backup --project <unmarked-project> --dest <new-backup-dir>` | 2 | After #127 merges: `SOURCE_NOT_SYNTHETIC`; no destination or copied bytes. |
| B05 | Symlink refusal | `backup --project <project-with-outside-symlink> --dest <new-backup-dir>` | 2 | After #127 merges: `UNSAFE_PATH`; outside target not read/copied; no destination. |
| B06 | Malformed manifest refusal | `backup verify --backup <malformed-backup>` | 2 | After #127 merges: `BACKUP_MANIFEST_INVALID`; stable blocked result, no uncaught traceback. |
| B07 | Restore tamper refusal | `restore --backup <tampered-backup> --target <new-target-dir>` | 2 | Stable file/manifest/chain refusal; target absent or empty; backup unchanged. |

## 3. CLI contract notes

- `agora data import-csv` requires `--project`, `--csv`, `--schema`, and `--role`; allowed roles are `context`, `scenario_input`, `calibration`, `validation`, and `sealed_holdout`. The test uses only `scenario_input` on the checked-in synthetic fixture.
- `agora data snapshots` requires `--project`; `show` and `rejected` also require `--import-id`.
- `agora outcomes held` is read-only. Exit 1 means a hold exists; it is not a command failure.
- `agora reconcile` is a read-only detector. Repair remains an API-only operation and is not part of this command inventory.
- `agora audit timeline` verifies the hash chain before displaying events; `agora audit verify` checks the chain against the local sidecar anchor. The sidecar cannot detect coordinated rollback of both chain and anchor.
- Backup/restore rows B01–B07 must be reconciled with the exact merged #127 CLI behavior and codes before the test is implemented. Do not claim #127 behavior while it remains in review.

## 4. Acceptance gate for item 8

Item 8 is complete only when a test executes every applicable row from a clean temporary synthetic workspace, verifies the required exit/status contract and no-side-effect guarantees, and fails under deliberate mutations to the runbook command, flag, expected output, or inventory membership. A prose-only checklist or a test that mocks the command's result does not satisfy this gate.

No commands were executed to prepare this specification.
