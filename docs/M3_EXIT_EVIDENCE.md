# M3 Exit Evidence — Claude Milestone Declaration Checklist

**Status:** Working checklist, not a milestone declaration. Main assessed at `4a0607f8946e32ef828b47183099ead4f8ae2bd7` (23 November 2026); Claude's latest entry says M3 NOT reached. The owner's one-run approval is received but dormant. The owner approved five design values on 23 November (B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, temperature 0 with cache on); they become effective only when merged into the protocol and frozen. The freeze sentence remains incomplete because its manifest field is the literal `<sha>` placeholder and the per-file manifest is absent. The owner named ChatGPT as a separate-process evaluator, but the evaluator's restricted scope, output custody and label-release boundary are not established. No dataset has been run, no protocol is frozen, and only Claude's exact collaboration-log entry may declare M3 reached.

**Post-#197/#198/#199 status:** #197 RT06 read-side held-descriptor SQLite snapshot merged at exact head `5d67cb4ceed8200a9a952b05ae1db9a58c3b0ba6`, merge `5cbe4cfbb82039543d408ab5c67e045e17e10a99`, exact-head CI `45167913607` passed 4/4. #198 Principal-bound authorization receipt merged at exact head `d3a8435bbabc28a1e488d87b752b1350b99c687d`, merge `4a55f2efd44da7aea54adda6ca7787471dd97cba`, CI `45170449040` passed 4/4. #199 adapter-origin check merged at exact head `851bbf1a217f018695133ee9c42f1c538fa088f0`, merge/current main `4a0607f8946e32ef828b47183099ead4f8ae2bd7`, CI `45173316190` passed 4/4. ChatGPT docs #196 merged at exact head `f9d34afa5914ee1cd2ccfd39a722fbb791ac4591`, merge `34e5cc39b2bb9f53ca6be0dc057de53e5aa5532c`, CI `45170530846` passed 4/4 (seven docs-only paths). #197 is read-side only; AuditChainStore writer opens remain path-based and Python <3.11 fails closed. #198/#199 leave an in-process trust limitation: `_ISSUED`/`_MINT` are accessible, receipt construction accepts the sentinel, `object.__setattr__` bypasses immutability, and the fixture adapter is caller-configurable/test-only. Production CLI remains default-deny.

**Assessment base:** main `4a0607f8946e32ef828b47183099ead4f8ae2bd7` (23 November 2026; latest code merge #199, latest docs merge #196). Exact-head CI: #197 run `45167913607` 4/4; #198 run `45170449040` 4/4; #199 run `45173316190` 4/4; #196 run `45170530846` 4/4.

## 1. Merged implementation slices

| Slice | Merged PR | Mainline evidence | Exact-head CI |
|---|---:|---|---|
| 4.1 deterministic projection | #163 | `agora/scenario_projection.py`, tests; pure projection, explicit mapping/allow-list/bounds | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.1b fail-closed projection hardening | #164 | `agora/scenario_projection.py`, tests; sensitivity and mapping/hash validation tightened | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.2 governed engine integration | #171 | `agora/sim/engine.py` plus tests only; optional governed input, verification, append-once provenance guard, changed-input/legacy/force refusal | Run `45089066900`, 4/4 |
| 4.3 governed CLI | #172 | `agora/cli.py` plus tests; exact import ID, binding/pack/mapping args, `--force` refusal, exit 3 on engine refusal | Run `45093439437`, 4/4 |
| 4.4 instance-row integrity | #173 | `agora/scenario_projection.py` plus tests; order-independent `instances_hash` included in `projection_hash` | Run `45096233966`, 4/4 |
| 4.6 base/projected scenario hashes | #178 | `agora/sim/engine.py` plus tests only, within the owner's named scope; original `scenario.yaml` hash is `base_scenario_hash`, separate `projected_scenario_hash` binds it to `projection_hash` | Run `45113858688`, 4/4 |
| RT06 read-side SQLite snapshot | #197 | Held-descriptor read-side snapshots for audit chain, anchor and run-record/seal checks; writer opens remain path-based; Python <3.11 fails closed | Run `45167913607`, 4/4 |
| 4.7 Principal-bound authorization receipt | #198 | Receipt minted after Principal-bound allow and revalidated in the engine; in-process sentinel and `object.__setattr__` limitations remain | Run `45170449040`, 4/4 |
| 4.7a adapter-origin provenance | #199 | Hand-built Principals without adapter-origin marker denied; same-process sentinel access remains possible | Run `45173316190`, 4/4 |

For #171–#173 and #178, 4/4 means Ubuntu/Windows × Python 3.11/3.12 jobs all completed successfully. Claude's log reports 15 new engine tests, 7 CLI tests, 2 row-hash tests and four hash-split regression cases, plus local full-suite/mutation results; ChatGPT did not run or independently reproduce those local tests. For #178, exact head `a620feb98d342250e29ded132781630fcb31f395` passed run `45113858688` 4/4. Its diff changes only `agora/sim/engine.py` and `tests/test_engine_governed_input.py`; the sole `agora/sim/**` path remains the owner-approved `engine.py`. Confirm exact merge-head and workflow evidence for every implementation PR; do not rely on a branch-head result if the merged SHA differs.

**Supporting validation utility (not an M3 engine slice):** #175 adds pure benchmark metrics/baselines in `agora/validation/benchmark_metrics.py`; exact PR-head CI `45105990141` passed 4/4. Follow-up #176 hardens boolean, date and window validation and pins the official M5 RMSSE scale convention (differences start at the first non-zero training observation; pre-sale leading zeros are excluded); exact-head CI `45110601617` passed 4/4. #179 adds strict `samples`, `min_clusters` and `alpha` guards; exact-head CI `45116463242` passed 4/4. #180 adds a non-negative seed guard (merged at `82c830fd`, merge commit `76ee7625`; exact-head CI run `45119572140` passed 4/4). These supporting utilities do not complete the governed engine slices or authorize data use; no dataset run is authorized.

**Documentation evidence:** ChatGPT docs PR #181 merged at exact head `73a4947efc1beb94b55718568a1d453d579bae1b` (merge commit/main `9dad1c8f9ab9ccc3c73aee76403cecab222d25e6`); exact-head CI run `45122674011` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Its five changed paths were exclusively `docs/**`. This is documentation evidence only; it does not close the policy-authorization, validation-protocol approval or dataset-register gates.

**Subsequent mainline security and documentation evidence — 23 November 2026:**
- Track A PR #183 merged at exact head `0f870e22aad3d2496a5da872c21c5871106e262d`; exact-head CI `45126668732` passed 4/4. It adds static symlink/reparse-point refusal for audit chain, anchor and lock paths. This does not prove resistance to concurrent path replacement; that TOCTOU boundary remains conditional on the owner's threat-model decision.
- Backup RT05b PR #186 introduced the run-record/seal checks (exact head `b50e1e3f6386e6762de83c08023721d7882a720e`, run `45137276771`, 4/4). Follow-up RT05c PR #189 merged at exact head `21b540ee91cbfb47335156c8f2c2510b1b4d7d45`, merge `757da519f7af2c75a515ca42c6d23015d9e47123`, exact-head CI `45141079904` passed 4/4; it closes missing-record, status-plus-run-ID downgrade and malformed-ID cases for backup verification/restore. RT05d PR #192 merged at exact head `bdf13a0663e5498c9d2e857817769985a8419e94`, merge/current main `3e55e5505cda38a2ccfdc93a3e9996120ebb659e`, exact-head CI `45150068645` passed 4/4; it adds strict source-record/seal preflight before destination creation/copy and re-checks copied bytes before publication. The source-side backup preflight gap is closed on main. The owner-gated path-based SQLite reopen TOCTOU boundary remains; see `RUNG_STATUS.md`.
- Dataset download guide and M3 documentation/exit checklist were included in ChatGPT docs PR #174, merged at exact head `e231961494a849d092c45a9a9377855fe30f188b` (merge commit `aeb9ab08046268674ef7c848f78ad17fb2002738`); exact-head CI `45107961493` passed 4/4. Ten changed paths were all under `docs/**`.
- Follow-up ChatGPT docs PR #188 merged at exact head `3704728a9623365c7c7e2dd7b736cd2d53fcd175` (merge `a2473cf1bd196e84fdc6301152c30b7ac94f1bd1`); exact-head CI `45138934878` passed 4/4. Five changed paths were all under `docs/**`.
- Latest ChatGPT docs PR #191 merged at exact head `02a88463529559009adec76c052be94621aa557e` (merge `705fe5cfa157b36fd75c93a141afe39255c08b65`); exact-head CI `45148838308` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Six changed paths were exclusively under `docs/**`; it refreshed the M3 evidence and the owner-controlled private-repository handoff.

These supporting security, metrics and documentation merges do not resolve the production identity/policy boundary, do not freeze the validation protocol, and do not authorize dataset acquisition/use or a simulation/validation run.



## 2. Scope and safety evidence

- [ ] Review changed-file lists for #163/#164/#171/#172/#173/#178 and confirm no unauthorized path under `agora/sim/**` was edited. #171 and #178 touch only the owner-approved `agora/sim/engine.py`; #172/#173 and projection slices remain outside `agora/sim/**`.
- [ ] Confirm the default `governed_input=None` path remains compatible and the legacy run path is not silently treated as governed.
- [ ] Confirm no simulation, calibration, backtest, forecast, validation or real/public dataset run occurred without separate owner approval. Unit tests with synthetic fixtures/mock backend are not dataset runs.
- [ ] Confirm `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.
- [ ] Confirm no real/personal/customer data, credentials, connectors, network fetches or write-back were introduced.

## 3. Blocking correctness and trust-boundary findings

These are not waived by merged PRs or green CI:

Resolved by #178: `base_scenario_hash` is captured from the original `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`. Exact-head CI passed 4/4.

1. **Production policy source remains absent.** `agora/cli.py::_governed_policy()` returns `None`; the policy-required scenario-input builder denies before snapshot bytes are opened. Preserve this default-deny behaviour. Do not inject a permissive callback or bypass it.
2. **Receipt/Principal provenance has a same-process limitation.** #198 requires an exact-type Principal-bound receipt and #199 rejects hand-built Principals without the adapter-origin marker. However `_ISSUED` and `_MINT` are reachable module objects in the same Python process; the public receipt constructor accepts `_MINT`, and `object.__setattr__` bypasses the setter. The synthetic fixture adapter accepts caller-supplied fixture definitions and is test-only. No production identity adapter or process-isolated trust boundary exists. Do not describe this as production authentication.
3. **Read/write path-race coverage is incomplete.** #197 adds held-descriptor, identity-checked read-side snapshots for audit-chain, anchor and run-record/seal verification. `AuditChainStore` writer opens remain path-based. Python <3.11 fails closed because `Connection.deserialize` is unavailable; no path-reopen fallback is permitted.
4. **Dataset and protocol gates remain open.** The FiveThirtyEight handoff is partial, four large CSVs remain outstanding, and no complete per-file SHA-256/source/licence manifest is recorded. Election, retail and adoption package files and licences remain to be pinned. The owner freeze sentence contains literal `<sha>`; bootstrap count/seed/interval and LLM sampling settings are not frozen. The owner-named evaluator is ChatGPT in a separate process, but access/custody is not established.
5. **Run approval is dormant.** The owner's one-run approval is received but applies only after an effective protocol freeze, complete data manifest, implementation gates and Claude's M3-reached confirmation. No dataset, simulation or validation run is authorized now.

Claude must state these residuals accurately and must not declare M3 reached while required milestone gates remain incomplete.


## 4. Documentation and validation gates

- [ ] `RUN_PROVENANCE_SPEC.md` accurately describes the implementation and all unresolved semantics.
- [ ] `M3_DESIGN.md` records the exact owner-approved engine path and current implementation, with no broader implied authorization.
- [ ] `OPERATOR_RUNBOOK.md` documents the CLI syntax and explicitly says it is blocked until policy identity is available; legacy `agora run` is not a substitute.
- [ ] `RUNG_STATUS.md`, `MILESTONE_OPERATOR_PILOT.md` and `MILESTONE_PILOT_READY.md` distinguish M2 reached from M3 unreached.
- [ ] `VALIDATION_PROTOCOL.md` remains clearly draft until owner approval. Freeze blockers include exact files/headers/licences, per-file privacy review, seeds/run counts, bootstrap parameters, independent evaluator/label custody, M5 reserve-file alignment and target-output compatibility.
- [ ] Dataset acquisition checklist records canonical sources, expected semantic fields, exact file/version/hash capture, licence terms and personal-data stop rules.
- [ ] A merged docs commit updates the assessment base and links this checklist; exact-head docs CI is green.

## 5. Owner decisions and external inputs

- [x] Owner accepted Claude's A–D design decisions on 23 November 2026. This is design acceptance, not expanded path authorization; only `agora/sim/engine.py` is approved under `agora/sim/**`.
- [x] Owner confirmed that the synthetic-fixture Principal is acceptable for strictly local validation on approved public datasets only. Production CLI remains blocked/default-deny.
- [x] Owner approved the five protocol design values: bootstrap B=2000; bootstrap RNG seed 20261123; percentile interval; one preregistered seed per configuration; LLM temperature 0 with cache on. These become effective only when merged into `docs/VALIDATION_PROTOCOL.md` and covered by a complete owner freeze sentence.
- [ ] Owner completes the four outstanding FiveThirtyEight CSVs and supplies the election-return, retail and adoption source files with exact per-file bytes, SHA-256, immutable source version and licence/terms records in the owner-controlled private repository.
- [ ] Owner establishes the named ChatGPT separate-process evaluator's restricted access to only the frozen protocol, manifest and raw outputs, plus output custody and label-release procedure.
- [ ] Owner reissues the protocol-freeze sentence with the actual merged protocol commit SHA and complete dataset-manifest SHA. The received sentence used literal `<sha>` and is not effective.
- [ ] Any simulation/validation run remains dormant until all freeze and data gates are satisfied and Claude has declared M3 reached; the owner's one-run approval does not authorize a run now.


## 6. Claude's final declaration requirements

Before declaring M3 reached, Claude's collaboration-log entry must:

1. State the exact main SHA assessed and link each merged PR/head SHA.
2. List exact-head CI run IDs and all four job conclusions for each required slice.
3. State test counts and mutation proofs with clear distinction between CI evidence and local-only claims.
4. Confirm only the owner-approved `agora/sim/engine.py` path was touched under `agora/sim/**`.
5. Confirm the policy identity/capability trust boundary is resolved or explicitly state why M3 is limited to implementation-only and not operator-usable; cite #178 for the now-implemented base/projected hash semantics.
6. Link merged docs and the validation-protocol status; no false claim that draft preregistration equals approved validation.
7. Confirm no dataset/simulation/validation run occurred without authorization and `VALIDATED_PREDICTION_ENABLED=False`.
8. Use the exact phrase **"M3 reached"** only if all required acceptance gates are satisfied; otherwise state **"M3 not yet reached"** and name the remaining blockers.

**No dataset was acquired, no simulation or validation was run, and no prediction-validity claim is made by this document.**


## 7. Dataset handoff status — 23 November 2026

The private Post2Drive data repository main is `5c8787a410a1aacaa9be9933b1c725a0b12e9689`. FiveThirtyEight import PR #5 is still open/unmerged at branch commit `15c9a053291925813ef568466a92fc5460f6b554`; the eight files below exist only on that PR branch at `validation-data/elections/fivethirtyeight-polls/old_model/`. The owner-reported/connector-inspected inventory lists no SHA-256 for any of them. Git blob IDs are not SHA-256 file checksums.

| File in Post2Drive/Post2Drive PR #5 branch | Bytes | SHA-256 recorded? |
|---|---:|---|
| `old_model/2024_presidential_primary_averages_old_model.csv` | 23,289 | No |
| `old_model/donald_trump_favorability_old_model.csv` | 82,705 | No |
| `old_model/generic_ballot_averages_old_model.csv` | 229,659 | No |
| `old_model/joe_biden_approval_old_model.csv` | 105,827 | No |
| `old_model/kamala_harris_approval_old_model.csv` | 84,376 | No |
| `old_model/mike_pence_favorability_old_model.csv` | 46,274 | No |
| `old_model/nikki_haley_favorability_old_model.csv` | 23,681 | No |
| `old_model/ron_desantis_favorability_old_model.csv` | 48,231 | No |

The eight CSVs total 644,042 bytes. The PR also includes README/licence/import notes. None of these files is in Post2Drive main or Agora main.

Four additional FiveThirtyEight files are missing from PR #5 and both main trees. Their byte counts below are upstream-reported sizes, not measured destination sizes; none has a SHA-256 recorded:

| Missing upstream-relative path | Reported bytes | SHA-256 recorded? |
|---|---:|---|
| `polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv` | 1,604,311 | No |
| `polls/2024-averages/presidential_primary_averages_2024.csv` | 11,407,331 | No |
| `polls/pres_pollaverages_1968-2016.csv` | 50,438,309 | No |
| `polls/pres_primary_avgs_1980-2016.csv` | 30,087,513 | No |

The uncorrected 2024 general file is not a substitute for corrected 2024 averages. Other 2020 polling files are linked in the import README but were not imported. The import README states CC BY 4.0 and the PR includes the upstream licence text.

**Other benchmark packages:**

- **MEDSL V20:** no CSV or codebook in Post2Drive main, PR #5 changed-file set, or Agora main. External candidate only: `mathis-group/cas-201-data-project` commit `1358bc6047f0c22989d37fa64ac03ee755bd17e`, `data/medsl/countypres_2000-2024.csv` (10,222,208 bytes) plus codebook. Not present in either target repository; only MD5 `bd6661282936006b4ef4f5ee71418f3e` is recorded for the candidate, not SHA-256. Candidate CC0 1.0; not owner-approved.
- **M5 Walmart / Rossmann:** no `calendar.csv`, `sales_train_validation.csv`, `sell_prices.csv`, `sales_train_evaluation.csv` or Rossmann files in either target repository. No hashes. M5 remains blocked on owner review of Kaggle competition terms.
- **Ember monthly EV:** no Ember file in either target repository. External candidate only: `Awes0mer/fuel-cars-pollution` commit `2c21f1edced7aae884314ebc28c89ab212f30563`, `data/raw/ember_ev_monthly/monthly_ev_sales.csv` (7,695,642 bytes). SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2` is recorded in Agora docs for this external 16-Nov candidate snapshot, not for a file in either target repository; the official Ember source had a newer 18-Nov update. Candidate CC BY 4.0; not owner-approved.

No raw benchmark files were downloaded by ChatGPT. The Agora main tree contains no raw benchmark files. No complete per-file manifest exists; no dataset has been run.

## 8. Owner approvals received — 23 November 2026 (status, not milestone completion)

### A–D design acceptance

The owner explicitly accepted Claude's written 23 November A–D design approval in the owner's chat message. This is acceptance of the design decisions, not an expansion of repository-path authorization. Within `agora/sim/**`, the only authorized path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized.

### Run approval — received, dormant

**Owner's run approval received 23 November 2026; status: RECEIVED, DORMANT.** The owner's approved scope is exactly one run per frozen configuration on the election, retail and adoption public datasets named in the frozen protocol, no tuning and no reruns for better numbers, all results reported including losses to the naive baseline, and no NCC, Nutrivance or P2D data.

This approval remains dormant until all preconditions are met: the protocol is separately frozen by the owner's freeze approval below; the complete selected datasets and per-file SHA-256 manifest are committed in the owner-controlled private repository; required implementation slices are merged and Claude records M3 reached; and the independent evaluator and custody are in place. The four outstanding FiveThirtyEight CSVs remain an acquisition blocker. This record does not authorize a run now, a second run, prediction enablement or any data outside the named public sets. No run has been made.

### Owner freeze sentence — received but incomplete; protocol NOT frozen

The owner supplied this sentence on 23 November 2026:

“I approve freezing `docs/VALIDATION_PROTOCOL.md` as merged at commit 34e5cc39b2bb9f53ca6be0dc057de53e5aa5532c, with dataset manifest `<sha>` and evaluator ChatGPT (separate process, sees only the frozen protocol, manifest and raw outputs). This approves no run and no flag change.”

The evaluator name is recorded as ChatGPT. The sentence is **not effective** because the manifest value is the literal placeholder `<sha>` and no complete committed per-file manifest is available. The owner approved B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, and LLM temperature 0 with cache on; these values become effective only when merged into the protocol and covered by a complete freeze sentence. The protocol stays draft/unfrozen.

To make a freeze effective, the owner must re-paste the freeze sentence with the new merged protocol commit SHA and actual complete dataset-manifest SHA after all files, licences, parameters and evaluator custody are verified. This approves no run and no flag change. `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.