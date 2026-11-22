# M2 Backup, Restore and Tamper Drills — Planning Specification

**Status:** #120 backup/verify/restore CLI and #127 hardening are merged. #127 adds the synthetic run-record gate, in-tree symlink/unsafe-path refusal, manifest schema validation, copied chain/anchor re-verification and post-copy restored-file hashes; exact-head Actions run `44994798420` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Current main is `15a92c56fdac14bb6266eec4acbd15b528d4b035` after #132 fixture/workdir hardening (exact-head CI `44997320523`, 4/4); that fixture change does not close the separate backup project/backup/target root-symlink or source-pair snapshot-lock gaps. This document remains the operator safety/drill specification; no operator tamper drill or rehearsal has been run.
**Boundary:** M1 was confirmed by Claude's 09:05 IST log entry. Local synthetic M2 implementation is owner-approved. Temporary local synthetic stores only; no simulation, real data, credentials, connectors, write-back or protected study mutation.

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

## 2. Restore procedure — CLI and hardening merged; operator validation pending

Merged command surface (#120; exact-head Actions run `44986367729` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs):

```bash
agora backup --project <project-dir> --dest <new-empty-backup-dir>
agora backup verify --backup <backup-dir>
agora restore --backup <backup-dir> --target <new-empty-target-dir>
```

The merged #127 patch changes the prior #120 behavior as follows:
- Backup requires `run_record.json` with `data_class == "synthetic"`; otherwise it blocks with `SOURCE_NOT_SYNTHETIC`.
- Symlinks in the source/backup tree and unsafe manifest-relative paths are refused with `UNSAFE_PATH`.
- The manifest validator requires version 1, `synthetic_only is True`, a nonblank chain ID and a safe relative-path-to-lowercase-SHA256 mapping; malformed manifests block with `BACKUP_MANIFEST_INVALID`.
- After copying the source files, backup re-verifies the copied chain/anchor; a changed or invalid pair blocks with `SNAPSHOT_CHANGED` and removes the incomplete destination.
- The root paths themselves are not explicitly checked with `lstat` before use: project/backup/restore-target root symlinks can redirect the initial run-record/manifest reads or destination writes. Reject a symlinked root before any read/write, including a symlinked parent where the safety contract requires it.
- `backup()` does not hold one shared `AnchorStore.lock()` across initial verification and the audit DB/anchor pair snapshot, and the post-copy check compares verifier status rather than a captured sequence/head. Add a shared-lock or equivalent snapshot protocol and prove exact chain ID, sequence and head equality.
- Restore re-hashes every copied file against the manifest before success; a mismatch blocks with `RESTORED_NOT_INTACT`.

#127 adds tests and mutation proofs for the synthetic gate, symlink refusal, manifest validation, snapshot re-verification and restore re-hashing. Exact-head CI run `44994798420` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. The operator command test and tamper rehearsal are still outstanding. Do not infer from the merged hardening that an operator rehearsal has occurred.

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
- Inject an anchored writer between source verification and backup pair copy: the backup must hold the same `AnchorStore.lock()` across verification and copy, or compare captured chain ID/sequence/head and block/retry on any change; comparing only a generic verifier status is insufficient.
- Mutate a non-audit backup file after pre-verification but before/during restore copy: restore must fail, remove its staged target, and preserve the original backup.
- Point backup at an unmarked/non-synthetic project: expect `SOURCE_NOT_SYNTHETIC` and no destination.
- Place a symlink inside the source or backup tree, or use an unsafe relative manifest path: expect `UNSAFE_PATH` and no outside-target read/copy.
- Make the project root, backup root or restore target root a symlink to an outside directory: expect `UNSAFE_PATH` before marker/manifest reads or destination writes; prove the outside sentinel is untouched.
- Tamper `manifest_version`, set `synthetic_only` false, replace `files` with a list, or corrupt `chain_id`/digest values: expect `BACKUP_MANIFEST_INVALID`, never an uncaught exception.
- Change the copied chain/anchor during backup: expect `SNAPSHOT_CHANGED` and no retained partial backup.
- Mutate a non-audit file after backup verification but before/during restore copy: expect `RESTORED_NOT_INTACT` and no published target.

## 4. Acceptance evidence

- Automated tests operate only on temporary local files and synthetic fixtures.
- Each tamper case asserts a stable blocked/error status and no silent repair.
- Restore tests verify exact hashes, chain ID, sequence and head.
- Failure tests prove original stores and backup bytes remain unchanged.
- #127 CI and mutation evidence covers the synthetic run-record gate, symlink/path refusal, manifest schema, copied chain/anchor re-verification and restored-file re-hashing. Preserve exact-head CI evidence in the milestone docs.
- The current synthetic gate is the `run_record.json` `data_class=synthetic` check; this is not equivalent to a separately pinned fixture-hash allowlist for every file in a project. Keep the scope distinction explicit.
- The automated runbook command test must exercise backup/verify/restore and each stable refusal code in temporary synthetic directories.
- A separately approved rehearsal log records command, SHA, fixture hashes, results and operator sign-off.
- A separately approved rehearsal log records command, SHA, fixture hashes, results and operator sign-off.

## 5. Explicit non-goals

No production backup target, cloud storage, network connector, external write-back, real data, credentials, simulation or mutation of existing studies.
