# Agora baseline assessment: capability and enforcement

Read-only assessment of main at the commit this file was merged from, 28 Nov 2026. It changes no code. Every finding names the file, test or document it rests on; anything not checked is marked **Not checked**. [Rung status](RUNG_STATUS.md) remains the canonical statement of what is implemented and wins wherever the two differ.

Labels used below, from weakest to strongest claim:

- **Implemented:** code exists.
- **Verified:** a test exercises the behaviour against its requirement.
- **Enforced:** the system refuses the prohibited action, including through other entry points.
- **Documented only:** a design or specification exists with no matching code.
- **Missing / Not checked:** nothing found, or not looked at in this pass.

## 1. Capability matrix

| Area | Status | Evidence | Gap |
|---|---|---|---|
| Study registry (projects) | Implemented | Web routes for list, create, open, delete, fork, compare: `agora/web/server.py` (routes `projects`, `fork`, `compare`) | No persisted lifecycle state (draft, ready, running, completed, validated) was found. A run's progress is reported by the `live` route only. |
| Structured study creation | Partial | `agora create` and the New Study page take name, question, documents and model settings (`agora/pipeline.py`, ROADMAP phase 2) | No fields for scope, geography, time bounds, intended use, or evidence role at creation. |
| Model providers | Implemented | `agora/llm/` (Ollama, OpenAI-compatible, Anthropic, mock, reply cache), settings and key routes in `agora/web/server.py` | End-to-end behaviour of each provider **Not checked**. |
| Settings kept apart from studies | Implemented | `agora/settings.py`, `/settings` routes | A per-run snapshot of the provider and model used **Not checked**. |
| Document ingestion with source records | Implemented | `agora/graph/ingest.py` records each file through `record_source` with data role `context`; `agora/sources/registry.py` | Test coverage of ingestion provenance **Not checked** in this pass. |
| Knowledge graph | Implemented | `agora/graph/` | Whether each relationship carries a basis (source-backed, user-defined, inferred, synthetic): **Not checked**; none was seen in the files read. |
| Scenario file (YAML) | Verified, Enforced for unknown fields | `agora/scenario.py` `_pick` raises on any unknown field; `validate` checks segment, space, poll and conversion references (lines 275 to 356) | No schema version field or compatibility check found. |
| Simulation engine | Implemented | `agora/sim/engine.py`; draws seeded per round `np.random.default_rng([seed, round, 1])` (line 709); exact resume after a crash (ROADMAP phase 1) | Reproducibility of a full run across machines **Not checked**. |
| Model-driven and crowd people kept apart | Partial | Crowd contact messages carry the reason prefix `crowd contact` (`agora/sim/engine.py`); native layer logs a reason for every message (`agora/society/store.py`) | No single field in the run output separating model-generated from rule-generated activity for every result. |
| Native communication | Implemented, Verified | `agora/society/` with tests under `tests/test_native_*` and `tests/test_society_store.py`; `agora new` defaults and warning (`agora/cli.py`, `agora/scenario.py`) | Platform adapters (phase 5), broadcast, leaving a group, invitation consent not built. Not supported for governed runs. |
| Reports | Implemented | Numbers computed deterministically in `agora/report/analysis.py`; `validate_exploratory_output` rejects predictive claim language (`agora/report/render.py` lines 26 to 41) | No per-statement label (observed, assumption, model-generated, estimate, simulated, validated). |
| Uncertainty and sensitivity | Implemented per ROADMAP phase 4 | `agora/calibrate/` (Monte Carlo ranges, sensitivity, backtest) | **Not checked** in this pass. |
| Exploratory versus validated mode | Enforced in the report writer | `agora/report/writer.py` line 34 `VALIDATED_PREDICTION_ENABLED = False`; lines 596 to 612: validated mode needs a registry ID, matches approval scope, then still refuses while the flag is False | The flag is a code constant; the CLI offers `--mode validated_prediction` (`agora/cli.py` line 783) which then refuses. The web report handler lines read show no mode argument. |
| Validation registry | Implemented | `agora/validation/registry.py` (`add_entry`, `transition_entry`, `require_approval`), `agora/validation/approval.py` | Review sequence and who may approve are in `docs/`; not re-verified here. |
| Data roles | Implemented | `ROLES = {context, scenario_input, calibration, validation, sealed_holdout}` in `agora/sources/registry.py` and `agora/tabular.py` | See section 3. |
| Publication cutoff | Implemented | `agora/cutoff.py` (`set_cutoff`, `check`), used by `agora/events.py` and `agora/news_rss.py`; `tests/test_cutoff.py` | Use by the holdout harness is covered by `tests/test_election_harness.py`; other entry points **Not checked**. |
| Ontology, actions, approvals | Verified | `agora/ontology/`, `docs/ONTOLOGY_ACTION_PROPOSALS.md`, protection flags in `agora/protection.py` | Effects are names or dry runs only; no real action execution. |
| Audit chain and anchor | Implemented, Verified | `agora/audit_chain.py`, `agora/audit_anchor.py` | Production anchor and identity adapter: not built (RUNG_STATUS). |

## 2. Engine correctness findings

1. **Conversion `requires` means "any one of".** `agora/scenario.py` line 105 documents it and `agora/sim/engine.py` line 1443 skips a person only when `a.converted.intersection(c.requires)` is empty. In the Nutrivance demo, `buy` lists both registrations, so a resident can buy after registering for **either** apartment. Because each registration is limited to one apartment's residents by `eligible_spaces`, this behaves per apartment. It is correct as implemented, but the list reads like "all of". Recommendation: say "any of" in the demo comment and, with approval, add an explicit `requires_any` name. Changing the demo YAML needs owner approval.
2. **Eligible versus triggered versus occurred.** The engine tests eligibility and the draw inside one function; the five states (possible, eligible, triggered, occurred, observed) are not recorded as separate states. Missing, not wrong.
3. **Probabilities are assumptions unless calibrated.** Demo values such as `base`, `stance_weight` and `experience.stance_mean` carry comments marking them as assumptions. The report does not yet label them as such per statement (see matrix).
4. **Random draws are seeded and recorded.** The seed is stored in run metadata (`agora/sim/engine.py` lines 445 and 571) and checked on snapshot restore (line 639).

## 3. Governance enforcement

| Rule | Documented | Implemented | Verified | Enforced |
|---|---|---|---|---|
| Validated mode cannot be switched on by configuration | Yes | Yes (`agora/report/writer.py`) | Tests mention it (`tests/test_governed_pipeline_e2e.py`, `tests/test_election_harness.py` among others); exact assertions **Not checked** | Yes for report generation. The flag is a constant, so changing it needs a code change. |
| Sealed holdout cannot be used for calibration | Yes (`docs/GOVERNANCE_HOLDOUT_PROTOCOL.md`) | Yes. Calibration and ordinary backtests read their data only through `require_registered_source` (`agora/governance.py` lines 128 to 146, called from `agora/calibrate/project.py` line 35), which matches the file's hash against the project's source registry and refuses if any matching record is `sealed_holdout`, or has any role other than `calibration`. The holdout harness separates records by source role (`agora/validation/holdout.py`). | `tests/test_governance.py`, `tests/test_g3_holdout_protocol.py` (leak cases and line 219) | Yes, for data whose bytes are in the project's own source registry. Limit: recognition is by file hash against that project's registry, so holdout data never registered in this project is not recognised. |
| Data source roles recorded | Yes | Yes (`record_source`) | **Not checked** | Role vocabulary enforced on registration (`ValueError` on an unknown role). |
| Publication cutoff | Yes | Yes (`agora/cutoff.py`) | Yes (`tests/test_cutoff.py`) | Where callers use `check`. |
| Governed entry points need policy, anchor and principal | Yes | Yes (`agora/protection.py`) | Yes (`tests/test_protected_defaults.py`) | Yes for the listed entry points; module flags relaxed only by the test fixture. |
| Knowledge transfer between studies carries only qualified results | Yes (`agora/validation/knowledge.py` exists) | **Not checked** | **Not checked** | **Not checked** |

## 4. Security: the six approved areas

Status follows `docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md` and the code in `agora/security/`; all of it is local library code with test keys, not a hosted service.

| Area | Status | Evidence |
|---|---|---|
| 1. Canonical key-list and release-manifest formats, with test vectors | Key list: Implemented, Verified (`agora/security/key_list.py`, `tests/test_receipt_key_list.py`, `tests/vectors/key_list_vectors.json`). Release manifest: **Not found** in code. | |
| 2. Root-key rollover and compromise recovery | Store-side part Implemented (`key_list.py`, `receipt_gate.py`); operator procedure and production custody Documented only | Design doc, implementation note of 27 Nov 2026 |
| 3. Durable nonce, action and audit consistency | Implemented for one local store (`agora/security/receipt_ledger.py`); across services Documented only | Design doc item 3 |
| 4. Key-list age and clock-skew limits | Implemented as constants: list age 900 seconds, key lifetime 90 days, 64 keys, skew 30 seconds (`key_list.py`, `signed_receipt.py`); design says "proposed defaults, to be confirmed by test" | Confirmation by test **Not checked** |
| 5. Authentication of the running release | **Not built.** `agora/security/run_scope.py` states release attestation is not built; the worker's release id comes from its own configuration | Design only |
| 6. Tenant isolation and key custody | Tenant id is checked in the receipt gate (`receipt_gate.py`); isolation architecture (one worker per tenant, cloud KMS) Documented only | No cross-tenant test seen |

## 5. Integration with the wider platform

The platform component names used in earlier planning conversations (nine systems) do not appear anywhere in this repository (searched all files, any letter case). Whether they are in scope for this repository is an owner decision; nothing here depends on them.

## 6. Testing and CI

- CI (`.github/workflows/tests.yml`): Ubuntu and Windows, Python 3.11 and 3.12, plus CodeQL and two Analyze jobs; seven checks must pass at the exact head before a merge.
- The last full run before this assessment passed 3747 tests (Linux, author machine); main has moved since.
- Windows jobs are the slowest; the workflow notes recent times of about 9 to 10 minutes after PR #311, with one earlier 55 minute job that left no log.
- Not checked: flaky-test history, coverage figures.

## 7. Documents that are out of date

- `ROADMAP.md` still lists the native society layer as "planned"; phases 1 to 4 and 6 are merged.
- `docs/README.md` marks the native design as "Design (not implemented)"; parts are implemented.

## 8. Prioritised plan

| # | Item | Prerequisite | Verification | Approval needed |
|---|---|---|---|---|
| 1 | ~~Make the calibrator refuse sealed holdout data~~ Withdrawn: already enforced (see section 3 and Corrections). | None | `tests/test_governance.py`, `tests/test_g3_holdout_protocol.py` | None |
| 2 | Per-statement labels in reports (observed, assumption, model-generated, estimate, simulated, validated) | Decide label vocabulary | Report tests | No |
| 3 | Persist a study lifecycle state and show it in the web UI | Decide the state list | State machine tests | No |
| 4 | Say "any of" in the demo comment and add `requires_any` (keep `requires` working). Approved 28 Nov 2026. | None | Scenario and engine tests | Owner (changes a shipped demo and the schema) |
| 5 | Record eligibility, trigger and occurrence separately for conversions | Item 4 | Engine tests, report change | No |
| 6 | Update ROADMAP and docs index for the native layer | None | Doc check | No |
| 7 | Release manifest format and running-release attestation | Hosting provider decision | Test vectors | Owner |
| 8 | Cross-tenant access tests | Tenant store design | Failing-by-design tests | No |
| 9 | Record provider and model snapshot per run | None | Run metadata test | No |
| 10 | Seeding phase 3 (apply ontology links to a run) | Owner answers on seeding | Engine tests | No |

Unknowns in this pass are listed in the matrix. A second pass should check ingestion provenance tests, graph edge basis, calibration and sensitivity, and the knowledge-transfer module.

## Corrections

- 28 Nov 2026: the first version of this document said no check in `agora/calibrate/` refused a source registered as `sealed_holdout`. That was wrong. The check lives in `agora/governance.py` (`require_registered_source`) and the calibrator calls it for every data file it reads. The first version searched only `agora/calibrate/` for the word "sealed" and did not follow the call. Section 3 and plan item 1 are corrected.
- The same pass recorded "no release-manifest format found". That stands, with one precision: the name `release_manifest` appears in `tests/test_receipt_key_list.py` and `tests/vectors/key_list_vectors.json` only as a key-list type that is rejected.
