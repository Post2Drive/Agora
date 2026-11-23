# M3 Design — Governed Scenario Input to the Simulation Engine

> **Governance update — 23 November 2026, 22:52 IST:** Agora main is `7400ec462fa6182a262b6a15571d2441d1490543` after #207. Protocol v0.1 remains frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1` with manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; the freeze authorizes no run, import or flag change. #205 merged at exact head `9d5c466ec886b27e7c83c5c13695810cb44ed08d` (run `45222866705`, 4/4), adding optional per-option leaning and the Package E harness/driver. `docs/VALIDATION_RUN_SPEC.md` v0.2 is merged but DRAFT; the owner's conditional freeze pre-approval applies only if the v0.2 change remains within the five named additions and leaves splits, metrics, baselines, data and manifest unchanged. The current `test-evaluate` driver reads/verifies and loads MEDSL before checking `--sealed-sha`; no held-out labels may be opened until that order is fixed and mutation-proved. Package A is predeclared NOT EVALUABLE; Package R/M5 is dropped. No run or flag change is authorized; M3 remains unreached and `VALIDATED_PREDICTION_ENABLED=False`.

**Status:** Design and implementation record assessed against Agora main `7400ec462fa6182a262b6a15571d2441d1490543` (23 November 2026). Protocol v0.1 is frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1`; manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. PR #205 adds optional per-option leaning to deterministic projection and a local Package E harness/driver. Exact-head CI run `45222866705` passed 4/4. The v0.2 run specification is present on main but remains DRAFT; no run is authorized. Package A is predeclared NOT EVALUABLE. The production CLI remains default-deny and `VALIDATED_PREDICTION_ENABLED=False`.

**Post-#197 / #198 / #199 / #201 / #202 / #203 / #205 review note:** #197 adds held-descriptor read-side snapshots; writer opens remain path-based and Python <3.11 fails closed. #198/#199 add Principal-bound receipts and adapter-origin checks, but in-process sentinels and `object.__setattr__` remain a limitation; the fixture adapter is test-only and no production identity adapter exists. #205 adds optional per-option leaning and the Package E harness/driver (exact head `9d5c466ec886b27e7c83c5c13695810cb44ed08d`, run `45222866705`, 4/4). #207 security hardening merged at exact head `687822c5870b66aba9c00890088b5efb95785267` with run `45225751700` 4/4. Static review found a label-custody defect in `agora/validation/run_election_validation.py`: `test-evaluate` calls `_verify` and `load_outcomes` on MEDSL before validating `--sealed-sha`. This contradicts the v0.2 run spec and custody boundary; no held-out labels may be read until corrected. The v0.2 file is DRAFT, Package A is NOT EVALUABLE, and no run is authorized. The only owner-approved `agora/sim/**` path remains `agora/sim/engine.py`.

## 1. M3 target contract (not yet an operational proof)

**Target contract:** a governed run must start from one exact, approved, immutable tabular import, with a policy check before source bytes are read; deterministic projection; a failure-atomic provenance envelope written before round 0; resume refusal on any input change; and reports that carry the trace and the EXPLORATORY label.

**Current mainline boundary:** #198/#199 now carry and verify a Principal-bound receipt and reject hand-built Principals that lack adapter-origin provenance. This closes the earlier missing-receipt and trusted-issuer-only checks, but not the in-process trust boundary: `_ISSUED`/`_MINT` are importable module objects, a caller can pass the sentinel to the public receipt constructor, and `object.__setattr__` can mutate receipt fields. The fixture adapter accepts a caller-supplied fixture table and is not production authentication. The production CLI's `_governed_policy()` still returns `None`, so it denies before snapshot bytes are opened. #197 hardens read-side SQLite snapshots only; writer opens remain path-based and Python <3.11 fails closed. The end-to-end governed-run contract is therefore not demonstrated on main. Not proved: that outputs match reality (Track B, under `VALIDATION_PROTOCOL.md`).

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

**Owner decisions and scope:** at 05:54 IST on 23 November 2026, the owner approved the initial `agora/sim/engine.py` slice implemented in #171. Later, the owner delegated design choices for validation quality to Claude; Claude then recorded the A–D design proposal. The owner explicitly accepted Claude's written 23 November A–D design approval in the owner's chat message. This records acceptance of the A–D design decisions, not a grant of additional code-path authority. The only explicit owner approval for an `agora/sim/**` path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized.

**Still blocked:** no dataset/validation run until the test-evaluate driver verifies the output seal before any MEDSL hash/read, a regression test proves that missing/wrong seals do not touch label bytes, evaluator custody is reviewed/merged, and the conditional v0.2 freeze and named run-go preconditions are satisfied. Production identity/policy remains default-deny; the in-process receipt limitations remain. The owner-controlled private repository still lacks the selected MEDSL and Ember raw-file handoff; P2D PR #5 contains only the 12 FiveThirtyEight CSVs. Agora's 15-row hash-only register has SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. Package R/M5 is dropped; Package A is NOT EVALUABLE under v0.2. Keep `_governed_policy()` fail-closed and `VALIDATED_PREDICTION_ENABLED=False`.