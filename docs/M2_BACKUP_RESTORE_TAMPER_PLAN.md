# M2 Backup, Restore and Tamper Drills — Planning Specification

**Status:** Local synthetic backup/verify/restore CLI is implemented by merged PR #120; this plan remains the safety/hardening and operator-drill specification. No operator tamper drill or rehearsal has been run.
**Boundary:** M1 was confirmed by Claude's 09:05 IST log entry. The current owner instruction approves local synthetic M2 implementation, but the 10:50 owner decision orders the three post-M1 hardening fixes before further M2 build. Temporary local synthetic stores only; this does not authorise simulation, real data, credentials, connectors, write-back or any protected study mutation.

## 1. Backup consistency contract

The audit SQLite database and its JSONL anchor are one logical integrity pair. A backup must capture a mutually consistent snapshot of both while writers are quiesced or under a reviewed snapshot/locking mechanism. Copying them at unrelated times is not an acceptable backup.

A backup manifest should record:
- Backup ID and UTC timestamp.
- Chain ID and exact paths/relative names.
- SQLite integrity-check result.
- Anchor verification status, sequence and head hash.
- SHA-256 of the backup database and anchor bytes.
- Tool/runtime version and synthetic fixture/run ID.
- Whether writers were quiesced and how the snapshot was obtained.

Never include event payload values, personal data, credentials or secrets in the manifest.

## 2. Restore procedure — CLI component merged; hardening pending

Merged command surface (#120; exact-head Actions run `44986367729` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs):

```bash
agora backup --project <project-dir> --dest <new-empty-backup-dir>
agora backup verify --backup <backup-dir>
agora restore --backup <backup-dir> --target <new-empty-target-dir>
```

The current implementation verifies the source chain/anchor before copying, snapshots SQLite files with SQLite's backup API, writes per-file SHA-256 values to `BACKUP_MANIFEST.json`, verifies manifest membership/hashes and the backup chain/anchor before restore, refuses non-empty targets, and verifies the restored chain/anchor.

Post-merge review found two races that must be fixed before operator reliance:
- `backup()` does not hold the same `AnchorStore.lock()` across source verification and copying the audit SQLite/anchor pair. An anchored append can interleave after the source verdict or between the DB and anchor copies; the function can return success with an inconsistent pair.
- `restore()` verifies the backup, then copies files, but only verifies the restored chain/anchor afterward. It does not re-hash every restored file against the manifest after the copy; a non-audit file changed after pre-verification can be restored without detection.
- The source is not proven synthetic: `_files(project)` recursively copies every file, follows symlinks through `Path.is_file()`/`shutil.copy2`, and the manifest hardcodes `synthetic_only=True`. No project marker or fixture-hash allowlist is checked, so arbitrary files, credential/config files or symlink targets can be copied under a false synthetic label.
- `verify_backup()` does not validate `manifest_version` or `synthetic_only`, and `files` is only a type annotation, not a runtime check. A malformed `files` list can reach `.items()` and raise `AttributeError` instead of a stable `BackupBlocked` result.

1. Stop all writers and preserve the current pair unchanged.
2. Verify the backup manifest and both component hashes.
3. Restore both files to a new isolated directory; never overwrite the source pair in place.
4. Run SQLite integrity checks and the read-only chain/anchor verifier.
5. Require the expected chain ID, sequence and head hash.
6. Compare the restored pair to the backup manifest.
7. Record the restore result and operator identity in a separate protected record.
8. Resume writes only after a clean verification and explicit approval.

A missing or invalid anchor is an incident, not permission to bootstrap a replacement. Never move an anchor backwards to make a restored chain appear valid.

## 3. Tamper drill matrix

Planned synthetic-only cases:
- Modify an audit event byte/field: chain verification must fail.
- Delete or reorder an audit row: chain verification must fail.
- Truncate the chain below the anchor: verification must fail.
- Remove, corrupt or alter the anchor: anchor verification must fail.
- Supply the wrong chain ID: verification must fail.
- Restore a chain from backup with a different anchor: mismatch must be detected.
- Restore a mutually consistent older chain+anchor pair: document that a local sidecar cannot detect coordinated rollback by an actor able to rewrite both files. This is a known trust limitation, not a passing security control.
- Simulate an unanchored tail: protected appends and repair must stop; preserve both stores.
- Inject an anchored writer between source verification and backup pair copy: the backup must block or hold the shared anchor lock until a consistent pair is captured.
- Mutate a non-audit backup file after pre-verification but before/during restore copy: restore must fail, remove its staged target, and preserve the original backup.
- Point backup at an unmarked/non-synthetic project and at a project containing a symlink to an outside file: both must fail closed without reading/copying the target or writing a `synthetic_only` manifest.
- Tamper `manifest_version`, set `synthetic_only` false, replace `files` with a list, or corrupt `chain_id`/digest values: verification must return stable blocked codes, never an uncaught exception.

## 4. Acceptance evidence

- Automated tests operate only on temporary local files and synthetic fixtures.
- Each tamper case asserts a stable blocked/error status and no silent repair.
- Restore tests verify exact hashes, chain ID, sequence and head.
- Failure tests prove original stores and backup bytes remain unchanged.
- Backup concurrency tests prove the same `AnchorStore.lock()` spans source verification and audit DB/anchor snapshot; removing the lock must fail the test.
- Restore tests re-hash every staged restored file against the manifest after copy and verify the chain/anchor before publishing the target; removing post-copy hash verification must fail the test.
- Backup tests require a verified synthetic project marker/fixture allowlist, reject symlinks and unapproved paths, and prove the manifest's `synthetic_only` value is evidence-based.
- Manifest tests validate version, synthetic-only flag, chain ID, and a relative-path-to-SHA256 mapping; malformed schemas return stable blocked codes.
- A separately approved rehearsal log records command, SHA, fixture hashes, results and operator sign-off.

## 5. Explicit non-goals

No production backup target, cloud storage, network connector, external write-back, real data, credentials, simulation or mutation of existing studies.
