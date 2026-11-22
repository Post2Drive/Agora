# M2 One-Command Start — Planning Specification

**Status:** Planning only. The owner has approved local synthetic M2 implementation after the three primary post-M1 hardening fixes merged in #122. The installer/orchestration change is not implemented; Claude has claimed the checked-in fixture plus one-command start as the next slice. #123's initial run-record component is merged but partial.
**Prerequisite:** Claude explicitly confirmed M1 in the 09:05 IST AI Collaboration Log entry. The owner approved local synthetic M2 at 10:50 IST after #122 closed the primary hardening sequence; implementation remains bounded by the M2 checklist and safety restrictions.
**Boundary:** Offline/local synthetic fixtures and temporary local stores only.

## 1. Operator outcome

A new operator should be able to start the supported synthetic workflow from a clean checkout using one documented command, without configuring credentials, network identity, external services or real-data connectors.

The current M1 entry point is:

```bash
agora pilot --workdir ./tmp-agora-pilot
```

This is a guided component, not the final M2 one-command contract: it currently uses in-module synthetic input, does not select the proposed checked-in fixture catalogue and does not persist the complete run-provenance envelope. Do not describe it as M2 complete.

## 2. Proposed M2 command contract

Candidate interface (not implemented):

```bash
agora pilot start --fixture <fixture-id> --workdir <new-empty-directory>
```

The command should:
1. Validate runtime version and local package/dependency state.
2. List available fixtures when `--fixture` is omitted only if interactive selection is explicitly requested; non-interactive use must fail with a stable code and list valid IDs.
3. Verify fixture manifest, schema, binding and content hashes before opening governed stores.
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
- Tests assert stage order, fixture hashes, immutable run record, denial stop and no engine import.
- Offline test proves no network request or external connector is attempted.
- Windows and Ubuntu supported runtime matrix passes on the exact implementation head.
- Runbook command inventory matches the tested command and output.

## 5. Explicit non-goals

No simulation, forecast, calibration, backtest, engine wiring, real data, credentials, network connectors, external write-back, or mutation of existing studies. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.
