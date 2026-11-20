# Governance audit log: operating and recovery notes

Agora's governance audit log is a JSON Lines file at
`<project>/governance/audit.jsonl`. Each record contains an event type, an
ISO-8601 recording timestamp, the previous record's SHA-256 hash, and its own
SHA-256 hash. Hashes are calculated over canonical UTF-8 JSON (sorted keys,
compact separators, no non-finite numbers). The first record links to the
all-zero genesis hash.

## Concurrency and durability

Writers take an exclusive operating-system lock on the adjacent
`audit.jsonl.lock` sidecar before verifying the current chain and appending.
The lock is released by the OS if a process exits. The append uses `O_APPEND`
and calls `fsync` after writing. These mechanisms reduce concurrent-writer
races and request that the operating system flush the record; they do not
promise identical power-loss guarantees on every filesystem, network share,
controller, virtualised disk or storage device. Keep the audit directory on a
filesystem whose locking and sync semantics are understood and tested.

Readers using `verify()` take the same lock, so they do not inspect a record
while an Agora writer is in its critical section. External programs that edit
or replace the file without taking the sidecar lock can still race with Agora.

## Backup and independent anchoring

- Back up `audit.jsonl` together with the project identifier, backup timestamp,
  and the reported final `last_hash`.
- Prefer versioned, access-controlled backups in a separate failure/security
  domain. Restrict write/delete access independently from the running Agora
  process.
- Periodically publish or sign the final hash using an independently governed
  system (for example, a separately controlled signing key or immutable object
  retention). Keep the signed/anchored hash and its timestamp outside the
  project directory. Key custody and rotation must be defined by the operator.
- Test restoration from backup and compare the restored chain's final hash to
  the independently retained anchor.

The hash chain alone is **tamper-evident, not immutable**. An attacker able to
rewrite the whole file can recompute every subsequent hash. Without a separately
protected signature/anchor, the chain cannot prove that an older prefix was not
rewritten or that a suffix was not deleted.

## Truncation, corruption and recovery

`verify()` fails closed on malformed JSON, non-object records, blank lines,
invalid timestamps/hashes, hash mismatches, broken links and an incomplete
final line. `append()` refuses to extend a log that fails verification. Agora
does not silently truncate, skip, repair, or automatically rebuild audit
history.

If verification fails:

1. Stop writers for the affected project and preserve the original log and
   sidecar lock file as evidence; do not edit the original in place.
2. Make a byte-for-byte copy and record its SHA-256, file size, timestamps and
   the verifier's line/reason result.
3. Compare against independently stored backups and anchored final hashes.
4. Restore a complete verified backup as a new recovery copy, retaining the
   corrupt original separately. If only a verified prefix is recoverable,
   preserve the original and prefix as separate artifacts and document the
   exact missing/corrupt range; do not present the prefix as a complete log.
5. Record the recovery decision, operator, source backup, hashes and any known
   gap in a separately protected incident/recovery record before resuming writes.

A missing final newline is treated as an incomplete record, not automatically
trimmed. Manual truncation is permitted only on a recovery copy after the
complete valid prefix has been identified and independently checked. Never
claim continuity across a removed suffix unless a trusted external anchor
supports it.

## Scope and limitations

This is local hash-chain integrity and process-level writer serialisation. It
is not a WORM store, digital signature system, remote audit service, tamper-proof
ledger, enterprise retention policy or substitute for operating-system access
controls. Network filesystem behaviour must be validated separately.
