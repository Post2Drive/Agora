# M3 Design — Governed Scenario Input to the Simulation Engine

**Status:** Design and implementation record (23 November 2026; assessed main `e3b0a58004298af05f9242795715b62d566941b7`). The owner gave written approval at 05:54 IST for the exact `agora/sim/engine.py`-only scope in section 3. That slice is merged in #171; the non-simulation CLI and projection follow-ups are merged in #172 and #173 (with #163/#164 implementing and hardening the pure projection). This document and those merges do not authorize a simulation/validation run, dataset use, real or personal data, connectors, credentials, write-back, or validated prediction. The production CLI currently denies governed runs because no production identity adapter exists.

## 1. What M3 proves (and nothing more)

A simulation run can be started from one exact, approved, immutable tabular import, with:
policy check before bytes are read; a deterministic projection; a failure-atomic provenance envelope written before
round 0; resume that refuses any change; reports that carry the trace and the EXPLORATORY label.
Not proved: that outputs match reality (that is Track B, under `VALIDATION_PROTOCOL.md`).
`VALIDATED_PREDICTION_ENABLED` stays `False`; no connectors, credentials, network, write-back, real or personal data.

## 2. Findings from live code that shape the design

- `Simulation.prepare()` (`engine.py`) builds the world from `population.build(self.sc)`. The population is driven by
  `Scenario.segments` (`share`, `stance_mean`, `stance_sd`, `stubbornness`, `activity`, `influence`, `openness`) plus counts.
  So the natural projection target is a **derived Scenario** (segments), not a change to `population.py` or `world.py`.
- Resume compares only a 16-hex `scenario_hash` and `--force` bypasses it. A governed run must not be forceable past its envelope.
- Run metadata lives in `Store.set_meta/get_meta`; it is the natural place for the append-once envelope.
- `cli.py` imports the engine lazily; pilot/data paths are engine-free. Must stay so.
- `agora/pilot.py` already builds the envelope shape (`RUN_PROVENANCE_SPEC.md`); reuse its canonical-manifest/hash code.

## 3. Owner-approved `agora/sim/**` edit scope (implemented in #171)

| Path | Edit | Reason |
|---|---|---|
| `agora/sim/engine.py` | Add optional `governed_input` argument to `Simulation`; in `prepare()` (a) verify envelope, (b) persist it in `Store` meta before `write_population`, atomically with it, (c) on resume re-verify stored envelope == requested and ignore `--force` for governed runs; legacy runs unchanged. | Only place the lifecycle boundary exists. |

**Explicitly NOT in scope:** `agora/sim/population.py`, `world.py`, `llm_agent.py`, `memory.py`, `opinion.py`,
`timing.py`, `platforms/**`. The projection is a pure function outside the tree that returns a derived `Scenario`;
`population.build` consumes it unchanged. If implementation proves another sim file is needed, I stop, revise this
design, and ask for a new named go. (This is narrower than ChatGPT's proposal, which listed population.py and a conditional world.py.)

## 4. Non-sim scope (Claude code PRs, no owner sim-go needed but same review/CI rules)

1. New `agora/scenario_input.py`: `build_envelope(project, import_id, binding, policy, scenario)` and
   `project_segments(envelope, snapshot) -> Scenario` (pure, deterministic, allow-listed columns, bounds, stable ordering,
   explicit assumption register; no inference of weights/behaviour without a declared mapping). Policy and anchor checks run
   before the snapshot is opened (reuse `ontology/binding.py` protected path).
2. `agora/cli.py`: `run --governed-input <import_id> ...` (exact id; `latest` rejected); lazy engine import kept.
3. `agora/report/*`: carry envelope fields, EXPLORATORY SIMULATION label; block export if envelope missing/inconsistent.
4. Docs: update `RUN_PROVENANCE_SPEC.md`.
Order: (4.1) adapter + tests with no engine edit; (4.2 after named go) engine.py; (4.3) CLI/report.

## 5. Tests and mutation proofs (each must fail when the guard is removed)

1. Policy denied -> snapshot file never opened (spy on open).
2. `latest`/path/unknown import id rejected; changed source bytes rejected.
3. Projection deterministic: same input -> same projection hash; reordered rows -> same hash; unknown/unmapped column, out-of-bound value, null violation, prohibited sensitivity class -> reject.
4. Envelope written before round 0; simulate crash after envelope/before population -> no run that looks valid; crash after -> run complete or absent (single transaction).
5. Resume identical -> ok; changed import/bytes/manifest/schema/binding/ontology/policy/scenario -> refuse, original envelope byte-identical; `--force` does not bypass.
6. Legacy run (no envelope) cannot resume through governed path; not silently upgraded.
7. Report/export without or with altered envelope -> blocked; label present; `VALIDATED_PREDICTION_ENABLED` is False and unchanged (AST/value check).
8. No network/connector import, no writes outside project root, fake LLM backend only in tests (no model call).
Mutations: remove policy pre-check, remove hash compare, make envelope write non-atomic, let `--force` skip, drop label — each flips a test red.

## 6. Rollback

Governed path is opt-in (`governed_input` default `None`); legacy path is byte-for-byte the old code path.
Rollback = revert the single engine.py PR; adapter, CLI flag and report fields become inert. No data migration; envelopes are append-only metadata in per-run stores.

## 7. Acceptance gates

As ChatGPT's list (12 gates) with this narrowed scope: exact-head CI 4/4, full suite green, only `engine.py` touched under `agora/sim/**`, `VALIDATED_PREDICTION_ENABLED=False`, no run of the engine on any real dataset (tests use the fake backend and synthetic fixture only).

## 8. Owner decision and remaining gates

**Owner decision recorded:** at 05:54 IST on 23 November 2026, the owner approved editing `agora/sim/engine.py` only, per this design. That scope was implemented in #171. Any additional path under `agora/sim/**` requires a new written owner approval naming the exact path and design revision.

**Still blocked:** no validation run until the production identity/policy adapter is available and fail-closed, the validation protocol is explicitly approved and frozen in a merged documentation commit, and the owner supplies the benchmark files with licence/version/hash records. No dataset or simulation run is authorized by this design. `VALIDATED_PREDICTION_ENABLED` remains `False`.


## 9. Post-merge review findings and current operator boundary

The merged slices establish a governed-input implementation path, but they do not yet establish an operator-usable approved path:

- The CLI's `_governed_policy()` currently returns `None`; the policy-required scenario-input builder therefore denies before opening snapshot bytes. Do not inject a permissive callback or bypass this gate.
- Review the direct `Simulation(..., governed_input=...)` constructor as a trust boundary. The engine verifies package hash consistency and projection integrity, but a caller-supplied package's internal hashes alone do not prove that `build_scenario_input()` completed a successful Principal-bound policy decision. Require a non-forgeable, scoped authorization/capability or make the trusted construction boundary explicit and enforceable. Add a mutation test that bypassing the policy-built path is denied.
- Preserve the original `scenario.yaml` hash before replacing `self.sc` with the projected scenario. Store that original value as `base_scenario_hash` and the effective projected scenario hash as `projected_scenario_hash`; pin both in tests and ensure resume rejects changes without rewriting the append-once envelope.
- The CLI form is `agora run PROJECT --governed-input IMPORT_ID --binding FILE --pack FILE --mapping FILE`. It is not currently an executable operator workflow because the production policy source denies. Do not run the legacy `agora run PROJECT` path as a substitute for governed benchmark input.
- The owner has not authorized any dataset simulation or validation run. The validation protocol remains draft; keep `VALIDATED_PREDICTION_ENABLED=False`.

These are completion gates, not permission for ChatGPT to edit source. Any additional path under `agora/sim/**` requires a separate written owner approval naming the exact path.
