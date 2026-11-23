# M3 Design — Governed Scenario Input to the Simulation Engine

**Status:** Design and implementation record (23 November 2026; latest main `e29ee4b1428fbc27458b547cc8c68bd4833c6ff2`). The owner gave written approval at 05:54 IST for the exact `agora/sim/engine.py`-only scope in section 3. #171 and #178 implement that approved engine slice; #172/#173 and #163/#164 provide the CLI/projection follow-ups. Supporting metrics #175/#176/#179/#180, static symlink/reparse-point hardening #183, and backup record fixes #189/#192 are merged. Latest docs-only PR #195 merged at exact head `fedab29c7d1e5b3d67e252d73bb97c9ae37acf93` (merge/current main `e29ee4b1428fbc27458b547cc8c68bd4833c6ff2`, exact-head CI `45160887328`, 4/4; six docs-only paths). The owner delegated the design choices recorded in the collaboration log: include concurrent path replacement in the synthetic/validation threat model; use the synthetic-fixture Principal for local public-data validation only; keep production CLI default-deny; use the conditional 2000–2016 polls fallback if corrected 2024 general averages are unavailable; and apply the proposed bias controls. Claude's written design approval A–D (TOCTOU slice, Principal receipt, validation controls and independent evaluator) is recorded in the log, but the separate owner acceptance paste for the broader A–D bundle is not present. The only explicit owner approval for an `agora/sim/**` path remains `agora/sim/engine.py`; no other `agora/sim/**` path is authorized. The protocol is not frozen and no dataset run is authorized. Production CLI remains fail-closed; implementation and mutation proofs are pending. The polls full window is conditional on all four required owner files and their per-file SHA-256/source/licence manifest; if the corrected 2024 general asset is unavailable, the 2000–2016 fallback must be a separate preregistration. Bias controls are proposed for freeze, not frozen. No dataset has been run; M3 remains unreached and only Claude's exact collaboration-log confirmation can declare it reached. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.

**Post-#192 / #195 review note:** #189 closes the missing-record, status-plus-run-ID downgrade and malformed-ID cases on backup verification/restore. #192 closes the source-side consistency follow-up: `backup()` applies the strict run-record/seal invariant before destination validation/creation/copy and re-checks the copied record before manifest publication; exact-head CI `45150068645` passed 4/4. #195 is the latest documentation merge (exact head `fedab29c7d1e5b3d67e252d73bb97c9ae37acf93`, merge/current main `e29ee4b1428fbc27458b547cc8c68bd4833c6ff2`, CI `45160887328`, 4/4; six `docs/**` paths). Static symlink/reparse-point refusal remains distinct from path-replacement race resistance. The owner delegated the design choice to include concurrent local path replacement in the synthetic/validation threat model; Claude's handle-based SQLite-open fix and mutation proofs are pending. Claude's A–D design proposal is recorded, but the collaboration log does not contain a separate owner acceptance of the expanded implementation-path bundle. The design proposal does not supersede the existing path-level approval boundary: only `agora/sim/engine.py` has explicit owner approval under `agora/sim/**`; any additional `agora/sim/**` path requires a separate written owner approval naming that path.

## 1. M3 target contract (not yet an operational proof)

**Target contract:** a governed run must start from one exact, approved, immutable tabular import, with a policy check before source bytes are read; deterministic projection; a failure-atomic provenance envelope written before round 0; resume refusal on any input change; and reports that carry the trace and the EXPLORATORY label.

**Current mainline boundary:** the engine integration and CLI entry point are merged, but the production CLI's `_governed_policy()` returns `None`, so it denies before snapshot bytes are opened. The direct `Simulation(..., governed_input=...)` constructor still verifies package/hash/projection consistency without proof of a successful Principal-bound policy decision. In addition, `Principal` is publicly constructible and the current policy gate trusts the synthetic issuer string rather than verifiable adapter issuance; the receipt slice must close both trust gaps. The end-to-end governed-run contract is therefore not demonstrated on main. Not proved: that outputs match reality (Track B, under `VALIDATION_PROTOCOL.md`).

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

**Owner decisions and scope:** at 05:54 IST on 23 November 2026, the owner approved the initial `agora/sim/engine.py` slice implemented in #171. Later, the owner delegated design choices for validation quality to Claude; Claude then recorded the A–D design proposal. The collaboration log contains a suggested owner acceptance paste for the broader A–D bundle, but not a separate owner statement accepting those expanded implementation paths. This document records the design choices, not a grant of additional code-path authority. The only explicit owner approval for an `agora/sim/**` path remains `agora/sim/engine.py`; obtain written owner approval naming any additional `agora/sim/**` path before editing it.

**Still blocked:** no validation run until the direct-engine policy trust boundary is closed, an approved identity/policy source is available and fail-closed, the validation protocol is explicitly approved and frozen in a merged documentation commit, and the owner supplies the benchmark files with licence/version/hash records. The CLI remains default-deny because `_governed_policy()` returns `None`; do not weaken that denial. No dataset or simulation run is authorized by this design. `VALIDATED_PREDICTION_ENABLED` remains `False`.


## 9. Post-merge review findings and current operator boundary

The merged slices establish a governed-input implementation path, but they do not yet establish an operator-usable approved path:

- The CLI's `_governed_policy()` currently returns `None`; the policy-required scenario-input builder therefore denies before opening snapshot bytes. Do not inject a permissive callback or bypass this gate.
- Review the direct `Simulation(..., governed_input=...)` constructor as a trust boundary. The engine verifies package hash consistency and projection integrity, but a caller-supplied package's internal hashes alone do not prove that `build_scenario_input()` completed a successful Principal-bound policy decision. Static inspection also finds an issuance gap in the current M1 identity layer: `Principal` is a public dataclass, `principal_policy()` accepts any `Principal`, and `decide_principal()` trusts the issuer string; the exact `BoundPolicy` type check does not prove the object was actually issued by `SyntheticFixtureAdapter`. Existing red-team coverage rejects a hand-built Principal with an untrusted issuer, but does not cover a hand-built Principal using the trusted synthetic issuer, an allowed role/project and a future expiry. The receipt slice must close both gaps: prove adapter issuance, then mint and verify a non-forgeable scoped receipt. Add a red-team test for the trusted-issuer hand-built Principal and assert denial before snapshot metadata read, backend/Store construction, provenance write or population side effect.
- Hash semantics are resolved in #178: `base_scenario_hash` is captured from `scenario.yaml` before projection; `projected_scenario_hash` is a separate 16-hex digest binding the base hash to `projection_hash` (rows, mapping and segments). The merged tests cover both values, row/mapping changes and unchanged-envelope resume refusal; exact-head CI run `45113858688` passed 4/4.
- The CLI form is `agora run PROJECT --governed-input IMPORT_ID --binding FILE --pack FILE --mapping FILE`. It is not currently an executable operator workflow because the production policy source denies. Do not run the legacy `agora run PROJECT` path as a substitute for governed benchmark input.
- The owner has not authorized any dataset simulation or validation run. The validation protocol remains draft; keep `VALIDATED_PREDICTION_ENABLED=False`.

These are completion gates, not permission for ChatGPT to edit source in this documentation task. The accepted A–D design approval defines Claude's separate code-slice scope; no source changes are included here.


## 10. Owner-delegated design choices — pending code (23 November 2026)

The owner delegated the identity and TOCTOU design choices for the stated objective of unbiased, genuine validation. These choices are recorded here as design decisions only; they do not establish implementation completion, protocol freeze, M3 reached or permission to run data.

### 10.1 Identity and authorization receipt

- **Validation identity:** use the existing synthetic-fixture Principal only for strictly local validation runs against owner-approved public datasets. No real people, personal data, private operational data or production identities are in scope.
- **Authorization proof:** the direct engine path must require an opaque, Principal-bound authorization receipt minted only after a successful allow decision by the trusted synthetic-fixture adapter. Bind it to issuer, subject, role, expiry and the exact project, import ID, binding ID, dataset/schema and scenario/manifest hashes. Revalidate allow, scope and expiry before Store construction, provenance writes or population creation.
- **Untrusted inputs:** reject missing, forged, wrong-type, denied, expired, cross-project, wrong-import/binding and tampered-package receipts. A caller-supplied mapping, plain dictionary or self-asserted allow flag is not proof.
- **Production boundary:** keep production CLI fail-closed. _governed_policy() continues to return None; do not add a permissive production fallback or weaken the denial. A production identity adapter requires a separate approval and design.
- **Claude-proposed code scope B (not a separate owner path approval):** the opaque Principal-bound receipt design spans `agora/principal.py`, `agora/scenario_inputs.py`, `agora/cli.py` and `agora/sim/engine.py`. The collaboration log records the design proposal but not a separate owner acceptance of this expanded file list. The only explicit `agora/sim/**` path approval remains `agora/sim/engine.py`; obtain a separate written owner approval naming any additional `agora/sim/**` path before editing it. No receipt implementation is claimed in this documentation update.

### 10.2 TOCTOU threat-model decision

Concurrent local path replacement is **in scope** for the synthetic and validation path. The planned fix is to open SQLite once and retain the database handle/connection for chain, anchor and seal checks; verify file identity through the held handle and do not reopen the database by pathname after a separate path check. The implementation must include mutation proofs demonstrating that a path-reopen regression is detected and that replacement/repointing cannot redirect the verified database between checks. This is a planned code slice, not a claim of current race resistance. No source code is changed by this documentation PR.

### 10.3 Validation controls and remaining gates

The proposed fixed splits, prior-election/seasonal-naive baselines, loss comparisons, 95% uncertainty ranges for every metric, no-test-tuning rule, one-run-per-frozen-config rule and package stop rules are in VALIDATION_PROTOCOL.md. The full polling window requires all four owner-reported files plus exact per-file bytes/SHA-256/source-commit/licence evidence; the conditional 2000–2016 fallback must be separately preregistered if the corrected 2024 general asset is unavailable. These controls remain proposed until the owner explicitly freezes a reviewed, merged protocol. The identity receipt, handle-based SQLite fix, complete source-file/licence/hash register, independent evaluator and all other freeze blockers must be resolved before any validation run. M3 remains unreached pending Claude's exact log confirmation. VALIDATED_PREDICTION_ENABLED=False remains mandatory.

