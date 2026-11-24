# M3 Design — Governed Scenario Input to the Simulation Engine

**Status:** Design and implementation record assessed against current main `d2302c1d6d04bffa23cdee861ce75de2fc3861bd` after #208/#209 workflow-only merges, #213 Package E artifact merge, #214 seal-control merge and #215 synthetic showcase merge. #215 is outside the M3 engine/protocol scope. The `agora/sim/**` approval boundary remains `agora/sim/engine.py` only. #205/#207/#211/#213/#214 exact-head CI passed 4/4; #208/#209 dependency-only workflow merges passed 4/4. #213 exact head `699ab1739aad4a654ae98e339de23e8b8321d6b7` merged at `5ec1bdd62d562cb8ef2ef58d54b61d717232e4ec`; #214 exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5` merged at `b111a4f918710f41650c659c40cad593419b02af`. ChatGPT independently verified the SHA-256 and byte count of all nine PR #213 repository artifacts against SHA256SUMS; all matched. No held-out labels were accessed and no metrics were recalculated. The nine-file byte-counted inventory and SHA256SUMS hash are recorded in EVALUATOR_CUSTODY.md; complete run configuration, the exact seven state-year exclusions and first-calibration-failure disposition remain outstanding. Row-level exclusion details remain Claude-reported and are not independently checked by ChatGPT. Package A is NOT EVALUABLE; Package R/M5 is dropped; M3 remains unreached.

**Post-#197 / #198 / #199 / #205 / #207 / #211 review note:** #197 adds `read_stable_bytes()` and `open_ro_snapshot()` for held-descriptor, identity-checked read-side snapshots used by audit-chain, anchor and run-record/seal verification; exact-head CI `45167913607` passed 4/4. This does not harden `AuditChainStore` writer opens, which remain path-based. Python <3.11 fails closed because SQLite `Connection.deserialize` is unavailable. #198 adds a Principal-bound authorization receipt and verifies it in the engine; exact-head CI `45170449040` passed 4/4. #199 adds adapter-origin provenance and rejects a hand-built Principal with no origin marker; exact-head CI `45173316190` passed 4/4. Residual: the module sentinels `_ISSUED` and `_MINT` are accessible to Python code in the same process, `AuthorizationReceipt.__init__` accepts the sentinel, and `object.__setattr__` bypasses its immutability guard. The caller-supplied fixture table is test-only; no production identity adapter exists. The CLI remains default-deny because `_governed_policy()` returns `None`. The v0.1 protocol file is frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1`; the 15-row manifest was finalized separately by #203 (merge `3872f2401a8c6c6de097ad82a701414e8b1a26c9`, SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`) before v0.2 freeze. The freeze authorized no run. The additive v0.2 run specification was merged and is now FROZEN at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` under the owner's pre-approval; Claude reports the frozen Package E calibration, validation and test-evaluate stages complete; the 2016 held-out result is a loss to both baselines. The only explicit owner-approved `agora/sim/**` path remains `agora/sim/engine.py`.

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

As ChatGPT's list (12 gates) for the initial governed-engine implementation: exact-head CI 4/4, full suite green, only `engine.py` touched under `agora/sim/**`, and `VALIDATED_PREDICTION_ENABLED=False`. The earlier no-benchmark-run boundary was subsequently superseded by the owner's conditional approval for one offline Package E benchmark on approved public datasets after v0.2 freeze; Claude reports that run completed with the mock backend and crowd agents only. This does not establish production/operator readiness, validated prediction, or permission for any additional run. No customer/personal data, production identity, LLM-agent run, network access or write-back is authorized.

## 8. Owner decision and remaining gates

**Owner decisions and scope:** at 05:54 IST on 23 November 2026, the owner approved the initial `agora/sim/engine.py` slice implemented in #171. Later, the owner delegated design choices for validation quality to Claude; Claude then recorded the A–D design proposal. The owner explicitly accepted Claude's written 23 November A–D design approval in the owner's chat message. This records acceptance of the A–D design decisions, not a grant of additional code-path authority. The only explicit owner approval for an `agora/sim/**` path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized.

**Still blocked:** M3 is not declared reached; Claude's exact canonical declaration is absent and main's M3 documentation is not yet synchronized because ChatGPT PR #210 remains draft/unmerged. Output-integrity review of merged #213 is complete. The separate seven state-cycle exclusions and first calibration silent-exit/partial-output disposition remain undocumented. PR #214 seal-control tests pass 4/4 CI but need stronger assertions for missing-seal MEDSL hashing and valid-seal read/hash ordering. Production identity/policy adapter remains absent and CLI remains default-deny; `VALIDATED_PREDICTION_ENABLED=False`. Package A is NOT EVALUABLE and Package R/M5 is dropped.




## 9. Post-merge review findings and current operator boundary

The merged slices improve the implementation boundary but do not yet establish an operator-usable approved workflow:

- #198 adds an exact-type Principal-bound authorization receipt, verified by the engine before governed execution. #199 adds an adapter-origin marker and rejects hand-built Principals that do not carry it. Both have exact-head CI 4/4.
- **Residual in-process trust limitation:** Python code in the same process can import the module-private `_ISSUED` and `_MINT` sentinels. A caller can pass `_MINT` to the public `AuthorizationReceipt` constructor, and `object.__setattr__` bypasses the receipt's `__setattr__` guard. The synthetic adapter also accepts a caller-supplied fixture table. Treat this adapter as test-only, not production authentication; a real process/adapter trust boundary is absent.
- The CLI's `_governed_policy()` still returns `None`; the policy-required scenario-input builder therefore denies before opening snapshot bytes. Do not inject a permissive callback or bypass this gate.
- #197 replaces several read-side path reopen operations with held-descriptor snapshots and file-identity checks. `AuditChainStore` writer opens remain path-based, so write-side path replacement is not covered. Python before 3.11 fails closed rather than reopening by path because SQLite `Connection.deserialize` is unavailable.
- Hash semantics are resolved in #178: `base_scenario_hash` is captured from `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`.
- The CLI form remains `agora run PROJECT --governed-input IMPORT_ID --binding FILE --pack FILE --mapping FILE`, but it is not currently an executable operator workflow because the production policy source denies. Do not run the legacy `agora run PROJECT` path as a substitute.
- The owner's conditional run go (“Go, once v0.2 is frozen”) was limited to the frozen Package E stages. Claude reports calibration/validation/test-evaluate completed once; no extra package, data, seed, configuration or rerun is authorized. The 15-row hash-only manifest remains unchanged. PR #213 merged the output/log bundle and SHA256SUMS into main. ChatGPT independently verified the SHA-256 and byte count of all nine PR #213 repository artifacts against SHA256SUMS; all matched. No held-out labels were accessed and no metrics were recalculated. The package lacks a complete byte-counted inventory, separately hashed inventory, full run configuration and first calibration failure disposition. No label bundle was accessed. `VALIDATED_PREDICTION_ENABLED=False`.

These are completion gates, not permission for ChatGPT to edit source. The owner-approved `agora/sim/engine.py` path remains the only approved `agora/sim/**` path; no source changes are included here.

**#205 Package E addition, #211 label-gate correction and #214 test follow-up:** #205 exact-head CI `45222866705` passed 4/4. #211 moved the `test_outputs.json` SHA-256 check before MEDSL verification/loading; exact head `1d90528de82d2a08f24ad38cf6c7c5c7bdd15eb0`, merge `2730903234196e9b38914ccb0fcab2de4e6c16ca`, CI `45229437458` passed 4/4. #214 merged missing-seal negative and matching-seal positive controls at `b111a4f918710f41650c659c40cad593419b02af`; exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5`, exact-head CI `45313425335` passed 4/4. Review finding: missing-seal test instruments `load_outcomes` but not MEDSL `sha256_file`; positive test proves one load and result creation but not explicit test-output-read-before-MEDSL-hash ordering. Recommend those assertions as follow-up. ChatGPT did not run code or tests.


## 10. Owner-delegated design choices — implementation status and remaining gates (23 November 2026)

The owner delegated the identity and TOCTOU design choices for the stated objective of unbiased, genuine validation. These choices are recorded here as design decisions only; they do not establish implementation completion, protocol freeze, M3 reached or permission to run data.

### 10.1 Identity and authorization receipt

- **Validation identity:** use the existing synthetic-fixture Principal only for strictly local validation runs against owner-approved public datasets. No real people, personal data, private operational data or production identities are in scope.
- **Authorization proof:** the direct engine path must require an opaque, Principal-bound authorization receipt minted only after a successful allow decision by the trusted synthetic-fixture adapter. Bind it to issuer, subject, role, expiry and the exact project, import ID, binding ID, dataset/schema and scenario/manifest hashes. Revalidate allow, scope and expiry before Store construction, provenance writes or population creation.
- **Untrusted inputs:** reject missing, forged, wrong-type, denied, expired, cross-project, wrong-import/binding and tampered-package receipts. A caller-supplied mapping, plain dictionary or self-asserted allow flag is not proof.
- **Production boundary:** keep production CLI fail-closed. _governed_policy() continues to return None; do not add a permissive production fallback or weaken the denial. A production identity adapter requires a separate approval and design.
- **Implementation status:** #198 implements the Principal-bound receipt across `agora/principal.py`, `agora/scenario_inputs.py`, `agora/cli.py` and the already-approved `agora/sim/engine.py`; #199 adds the adapter-origin marker in `agora/principal.py`. Exact-head CI passed 4/4 for both. The owner confirmed that the synthetic-fixture Principal is acceptable for strictly local validation on approved public datasets only; production CLI remains blocked/default-deny. These merges do not authorize any additional `agora/sim/**` path; `agora/sim/engine.py` remains the only owner-approved path. Residual: the in-process `_ISSUED`/`_MINT` sentinels are reachable, receipt construction accepts `_MINT`, and `object.__setattr__` bypasses the setter. The caller-supplied fixture adapter is test-only; production identity is absent and CLI policy remains `None`.

### 10.2 TOCTOU threat-model decision

Concurrent local path replacement is **in scope** for the synthetic and validation path. #197 merged a read-side implementation that reads audit-chain, anchor and run-record/seal SQLite snapshots through a held descriptor, checks file identity before and after reading, and does not reopen the verified database by pathname. Exact-head CI `45167913607` passed 4/4. This is not full writer-side race resistance: `AuditChainStore` still opens its SQLite database by path. Python <3.11 fails closed because `sqlite3.Connection.deserialize` is unavailable; it must not fall back to a path reopen. Any additional race-hardening slice must name its exact files and preserve the existing owner path approvals.

### 10.3 Validation controls and remaining gates

The selected election window remains training 2000/2004/2008, validation 2012 and held-out test 2016; use the latest FiveThirtyEight daily state average on or before each cutoff and report previous-election state-margin persistence separately. MEDSL uses TOTAL where present, otherwise sums modes; never double-count both. Ember is not required because Package A is NOT EVALUABLE; Package R/M5 is dropped. The frozen v0.1/v0.2 splits, baselines, metrics, uncertainty, no-test-tuning, one-run and stop rules remain unchanged. v0.2 remains frozen at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`; run-spec SHA-256 `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`. Claude reports calibration k=0.24, a 2012 MAE tie with worse RMSE and a 2016 loss to published average and persistence. ChatGPT independently fetched and verified the exact bytes and byte counts of all nine non-sensitive PR #213 output/log artifacts against SHA256SUMS; all matched. No raw source CSVs or held-out labels were accessed and no metrics were recalculated. The 2016 output has one no-poll cutoff exclusion (District of Columbia, 2016-10-11); the 2012 output has two (District of Columbia and Idaho, 2012-10-09). The separate seven state-cycle exclusions, full run configuration and first calibration failure disposition remain outstanding. No additional run/data is authorized. M3 remains unreached; `VALIDATED_PREDICTION_ENABLED=False`.
