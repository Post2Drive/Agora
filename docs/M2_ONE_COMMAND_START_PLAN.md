# M2 One-Command Start — Planning Specification

**Status:** Claude's PR #125 proposes the fixture-selected `agora pilot start` and `agora pilot list`; it is open at head `914d570ce62c5d9c1157ec0470d9b948ff17dfc9`, not merged. Exact-head CI run `44993280261` has two Ubuntu jobs passed and two Windows jobs in progress. The diff does not yet prove clean installation from a fresh checkout.
**Prerequisite:** Claude explicitly confirmed M1 in the 09:05 IST AI Collaboration Log entry. The owner approved local synthetic M2 after #122 closed the primary hardening sequence. Main is `41137618f04cf44c111acfaff565663b25eb5fe3`; #123's run record remains partial. Claude owns the #125 fixture/start slice; do not duplicate it.
**Boundary:** Offline/local synthetic fixtures and temporary local stores only.

## 1. Operator outcome

A new operator should be able to start the supported synthetic workflow from a clean checkout using one documented command, without configuring credentials, network identity, external services or real-data connectors.

The current M1 entry point is:

```bash
agora pilot --workdir ./tmp-agora-pilot
```

This remains the M1 mainline component. PR #125 proposes `agora pilot start --fixture <fixture-id> --workdir <dir>` and `agora pilot list`, but it is not merged and does not prove package installation from a clean checkout. Its workdir guard checks for an existing project child, not every pre-existing file in the requested workdir.

## 2. Proposed M2 command contract

Candidate interface (not implemented):

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
