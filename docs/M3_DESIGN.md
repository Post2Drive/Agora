# M3 Design — Governed Scenario Input to the Simulation Engine
\n> **Governance update — 23 November 2026, 22:40 IST:** Protocol v0.1 is frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1` with manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. This freeze authorizes no run, data import or flag change. Claude reports all 15 pinned source files match the manifest and 74 relevant benchmark-metrics/engine tests pass on main. The target-output check remains partial: the base election scenarios and exact mappings to/from AGORA outputs, run command and evaluator command are not yet specified. v0.2 is required before a run. The owner’s conditional v0.2 freeze pre-approval is limited to mappings, run command and backend; splits, metrics, baselines, data and manifest must remain unchanged. A conditional run go applies only after v0.2 freeze and all gates. M3 is not declared reached. See `docs/EVALUATOR_CUSTODY.md`.

**Status:** Design and implementation record assessed against Agora main `3872f2401a8c6c6de097ad82a701414e8b1a26c9` (23 November 2026). M3 implementation evidence and limitations below remain as recorded. Protocol v0.1 is frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1` with manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; the owner posted the exact freeze sentence at 22:14 IST and Claude recorded it at 22:16 IST. The freeze authorizes no run, no import and no flag change. Claude's 22:40 pre-run report records 15/15 pinned source files matching the manifest and 74 relevant tests passing, but target-output checks are partial because base scenarios, mappings, run invocation and evaluator command are not yet specified. A versioned v0.2 run specification is required. The owner's conditional v0.2 pre-approval is limited to mappings, run command and backend; splits, metrics, baselines, data and manifest must remain unchanged. The conditional run go applies only after v0.2 is frozen and all gates pass. M3 remains unreached; `VALIDATED_PREDICTION_ENABLED=False`.

**Post-#197 / #198 / #199 / #201 / #202 / #203 review note:** #197 adds `read_stable_bytes()` and `open_ro_snapshot()` for held-descriptor, identity-checked read-side snapshots; writer opens remain path-based and Python <3.11 fails closed. #198 adds a Principal-bound receipt (CI `45170449040`, 4/4); #199 adds adapter-origin provenance (CI `45173316190`, 4/4). Residual: `_ISSUED`/`_MINT` remain accessible in-process, the public receipt constructor accepts the sentinel, and `object.__setattr__` bypasses immutability. The fixture adapter is test-only; no production identity adapter exists and the CLI remains default-deny. Docs #201 adds the 15-row hash-only manifest; #202 records E/A and drops Package R; #203 corrects manifest statuses to `PLANNED - NOT EXECUTED` and merged with CI `45213851626` 4/4. The current manifest SHA-256 is `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. None of these docs merges adds raw data or authorizes a run. The owner posted the complete freeze sentence at 22:14 IST; Claude recorded v0.1 frozen at 22:16 IST. A v0.2 run specification is required because mappings and commands are missing. The only explicit owner-approved `agora/sim/**` path remains `agora/sim/engine.py`.

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

**Still blocked:** no dataset/validation run until the direct-engine in-process trust limitation is resolved or explicitly bounded by the approved threat model, production identity/policy remains default-deny, evaluator custody/label release is established, the owner-controlled private repository contains the selected E/A raw files and complete per-file manifest, and the owner pastes the prepared freeze sentence for protocol #202. P2D PR #5 remains open/draft/unmerged with only the 12 FiveThirtyEight CSVs; MEDSL and Ember raw files remain in Claude's workspace only. Agora #203 contains a 15-row hash-only register with current SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. Package R/M5 is dropped; no retail acquisition or substitute is in scope. Keep `_governed_policy()` fail-closed and `VALIDATED_PREDICTION_ENABLED=False`.


## 9. Post-merge review findings and current operator boundary

The merged slices improve the implementation boundary but do not yet establish an operator-usable approved workflow:

- #198 adds an exact-type Principal-bound authorization receipt, verified by the engine before governed execution. #199 adds an adapter-origin marker and rejects hand-built Principals that do not carry it. Both have exact-head CI 4/4.
- **Residual in-process trust limitation:** Python code in the same process can import the module-private `_ISSUED` and `_MINT` sentinels. A caller can pass `_MINT` to the public `AuthorizationReceipt` constructor, and `object.__setattr__` bypasses the receipt's `__setattr__` guard. The synthetic adapter also accepts a caller-supplied fixture table. Treat this adapter as test-only, not production authentication; a real process/adapter trust boundary is absent.
- The CLI's `_governed_policy()` still returns `None`; the policy-required scenario-input builder therefore denies before opening snapshot bytes. Do not inject a permissive callback or bypass this gate.
- #197 replaces several read-side path reopen operations with held-descriptor snapshots and file-identity checks. `AuditChainStore` writer opens remain path-based, so write-side path replacement is not covered. Python before 3.11 fails closed rather than reopening by path because SQLite `Connection.deserialize` is unavailable.
- Hash semantics are resolved in #178: `base_scenario_hash` is captured from `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`.
- The CLI form remains `agora run PROJECT --governed-input IMPORT_ID --binding FILE --pack FILE --mapping FILE`, but it is not currently an executable operator workflow because the production policy source denies. Do not run the legacy `agora run PROJECT` path as a substitute.
- The owner has not authorized a dataset simulation or validation run. The owner's one-run approval remains dormant; protocol #202 is merged but still DRAFT. Claude's 21:58 entry provides the complete replacement freeze sentence naming protocol `6d06088cf7954bd41f003544f5ec61675389bcc1` and manifest `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; it awaits owner paste. The selected scope is Packages E and A only; Package R/M5 is dropped. The 15-row Agora manifest is hash-only, P2D PR #5 remains unmerged, and the approved MEDSL/Ember raw files remain in Claude's workspace only. Evaluator custody and the complete owner-controlled private data handoff remain open. Keep `VALIDATED_PREDICTION_ENABLED=False`.

These are completion gates, not permission for ChatGPT to edit source. The owner-approved `agora/sim/engine.py` path remains the only approved `agora/sim/**` path; no source changes are included here.

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

The selected election window is training 2000/2004/2008, validation 2012, held-out test 2016; use the latest FiveThirtyEight daily state average on or before each cutoff and report previous-election state-margin persistence separately. MEDSL uses the `TOTAL` row where present, otherwise sums modes; never double-count both. Ember is the owner-approved 16-Nov-2026 snapshot, monthly rows only, with quarterly rows excluded. Package R/M5 was dropped by owner decision; retail is untested and no retail baseline or substitute remains active. The five owner-approved design values are merged in protocol #202. Claude's replacement freeze sentence is awaiting owner paste; the protocol remains DRAFT. The separate-process evaluator's restricted scope, output custody and label-release boundary remain unestablished. No dataset run is authorized; M3 remains unreached pending Claude's exact confirmation and `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.
