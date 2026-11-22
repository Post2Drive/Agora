# M2 One-Command Start — Planning Specification

**Status:** Fixture-selected `agora pilot start` and `agora pilot list` are merged in #125 (head `914d570ce62c5d9c1157ec0470d9b948ff17dfc9`, exact-head CI `44993280261`, 4/4). #130 refuses non-empty workdirs; #132 pins the fixture manifest and rejects direct fixture/workdir-root symlinks and empty versions; #135 rejects workdir symlink ancestors and filters linked fixture directories; #139 rejects lexical `..` in backup/pilot path walkers (exact-head CI `45011493565`, 4/4). Clean-install/start acceptance remains partial because tests do not prove installation from a clean checkout.
**Prerequisite:** Claude explicitly confirmed M1 in the 09:05 IST AI Collaboration Log entry. The owner approved local synthetic M2 after #122 closed the primary hardening sequence. Main is `1719d4c552d22e88109cee7623b3b7146ee5ef39`; #123/#125/#130's run record remains partial.
**Boundary:** Offline/local synthetic fixtures and temporary local stores only.

## 1. Operator outcome

A new operator should be able to start the supported synthetic workflow from a clean checkout using one documented command, without configuring credentials, network identity, external services or real-data connectors.

The current M1 entry point is:

```bash
agora pilot --workdir ./tmp-agora-pilot
```

Main includes `agora pilot list` and fixture-selected `agora pilot start --fixture <fixture-id> --workdir <dir>` (#125), non-empty-workdir refusal (#130), pinned fixture manifest/direct-path checks (#132), workdir-ancestor and linked-fixture filtering (#135), and lexical `..` refusal in pilot/backup path walkers (#139). Clean package installation from a clean checkout remains unproven.

## 2. Merged command surface and remaining acceptance contract

Merged interface on main (#125):

```bash
agora pilot start --fixture <fixture-id> --workdir <new-empty-directory>
```

The command should:
1. Validate runtime version and local package/dependency state.
2. List available fixtures with `agora pilot list`; non-interactive start must require an exact fixture ID and return stable codes for missing/unknown IDs.
3. Verify fixture manifest, schema, binding and content hashes before opening governed stores; independently pin the manifest digest, reject symlinks and reject manifest-plus-payload changes.
4. Refuse a non-empty work directory unless an explicit, separately reviewed resume mode exists.
5. Provision temporary local stores without overwriting existing files or silently bootstrapping an existing anchor.
6. Execute only the governed synthetic pipeline stages; do not import or call `agora.sim.engine`.
7. Persist and verify the immutable run envelope specified by `docs/RUN_PROVENANCE_SPEC.md`.
8. Print each stage, opaque identifiers, stable result codes and next safe action; stop immediately on a denial or integrity failure.

## 3. Failure contract

- Missing dependency/runtime: actionable installation guidance; no store creation.
- Unknown fixture or manifest mismatch: fail before source import/store mutation.
- Non-empty work directory: refuse; preserve every existing file.
- Policy denial: show the stable denial code and stop before the next protected read/write.
- Anchor/chain failure: fail closed; never auto-bootstrap, reset or repair.
- Run-record write/verification failure: report incomplete; never label the pilot successful.

## 4. Acceptance evidence

- Clean-checkout subprocess test executes the documented command.
- Tests assert stage order, fixture hashes, immutable run record, denial stop and no engine import; add a clean-install test, a pre-existing non-empty workdir sentinel test, manifest-plus-payload tamper mutation and symlink escape mutations.
- Offline test proves no network request or external connector is attempted.
- Windows and Ubuntu supported runtime matrix passes on the exact implementation head.
- Runbook command inventory matches the tested command and output.

## 5. Explicit non-goals

No simulation, forecast, calibration, backtest, engine wiring, real data, credentials, network connectors, external write-back, or mutation of existing studies. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.
