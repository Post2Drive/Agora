# M3 Exit Evidence — Claude Milestone Declaration Checklist

**Status:** Working checklist, not a milestone declaration. Main assessed at `4a0607f8946e32ef828b47183099ead4f8ae2bd7` (23 November 2026); Claude's latest entry explicitly says M3 not reached. The owner's one-run approval is received but dormant. The owner approved five design values on 23 November (B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, temperature 0 with cache on); they become effective only when merged into the protocol and frozen. P2D PR #5 remains open/draft/unmerged at branch head `b06b29cb2071f048f0c234f65c1014ea4677d33d`, with 12 FiveThirtyEight CSVs and a per-file SHA-256 manifest. Claude's STEP 5 report states source and committed-destination bytes/hashes, plus Windows checked-out bytes/hashes, match for all 12 CSVs; the 4,679-byte manifest file SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. ChatGPT inspected PR metadata, manifest and import README only; it did not fetch raw CSV bytes or independently reproduce Claude's checks. The manifest is only a FiveThirtyEight sub-manifest, not the complete all-package manifest. Corrected-2024 and 2020 polling coverage, MEDSL/M5/Ember files and evaluator custody remain incomplete. The freeze sentence remains incomplete because its manifest field is the literal `<sha>` placeholder. No dataset has been run, no protocol is frozen, and only Claude's exact collaboration-log entry may declare M3 reached.

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
4. **FiveThirtyEight sub-manifest verification is reported complete; package coverage and protocol gates remain open.** P2D PR #5 at branch head `b06b29cb2071f048f0c234f65c1014ea4677d33d` is open/draft/unmerged and contains 12 FiveThirtyEight CSVs (94,181,506 bytes) pinned to source commit `4c1ff5e3aef1816ae04af63218015066e186c147` under CC BY 4.0. Claude's STEP 5 report states source and committed-destination byte counts/SHA-256 values match for all 12 CSVs and the Windows checked-out files match; the 4,679-byte manifest file SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. ChatGPT did not fetch raw CSV bytes or independently reproduce these checks. The PR remains unmerged, so the files are not in P2D main or Agora main. The 2024 general-average CSV is explicitly uncorrected; corrected-2024 and 2020 coverage are not established. Claude reports `pres_pollaverages_1968-2016.csv` is a daily state-level publisher-average series without individual poll records or sample sizes; use the latest same-state/office published average on or before each cutoff as the draft default baseline, and do not compute a sample-size-weighted 28-day mean from it. The individual-poll alternative is not selected unless the owner explicitly asks Claude to try the live links. Election-return, retail and adoption package files/licences and the complete all-package manifest remain outstanding. The owner freeze sentence contains literal `<sha>`; the owner-named evaluator's access/custody remains unestablished.
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
- [x] Claude's STEP 5 report states that all 12 FiveThirtyEight CSVs and Windows checked-out files match the pinned source and committed-destination byte counts/SHA-256 values; manifest-file SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. ChatGPT did not independently fetch raw CSV bytes.
- [ ] Owner accepts/merges P2D PR #5 and supplies the remaining corrected-2024/2020 poll assets, election-return, retail and adoption files with exact bytes, SHA-256, immutable source version and licence/terms records in the owner-controlled private repository.
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

The private Post2Drive data repository main remains `5c8787a410a1aacaa9be9933b1c725a0b12e9689`. FiveThirtyEight import PR #5 is open/draft/unmerged at branch head `b06b29cb2071f048f0c234f65c1014ea4677d33d`. Its `DATASET_MANIFEST.csv` records 12 CSV files (94,181,506 bytes), pinned to FiveThirtyEight/data commit `4c1ff5e3aef1816ae04af63218015066e186c147`, licence CC BY 4.0 and per-file SHA-256 values. The manifest blob ID is `308dfbd4fec4de36ffe1bda9dd3d15ec88870f8b`, a Git object ID rather than the file checksum; the 4,679-byte manifest file SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. Claude's STEP 5 report states that all 12 source and committed-destination bytes/hashes and Windows checked-out bytes/hashes match. ChatGPT inspected manifest and import README metadata only; raw CSV bytes were not downloaded or independently verified by ChatGPT.

| Relative path under `validation-data/elections/fivethirtyeight-polls/` | Bytes | Per-file SHA-256 |
|---|---:|---|
| `old_model/2024_presidential_primary_averages_old_model.csv` | 23,289 | `fb6d3f09936126651d60f30bc1559703611dc6b3cf28ef6185116d3e952a4c26` |
| `old_model/donald_trump_favorability_old_model.csv` | 82,705 | `4c39fe81a0d753551395c5436aa920546e1c4caf4611fed481b6ac98955c973a` |
| `old_model/generic_ballot_averages_old_model.csv` | 229,659 | `caae521c49a1ec9387a84a1a40f8f5a4555215513334cb667474d4f2ff130840` |
| `old_model/joe_biden_approval_old_model.csv` | 105,827 | `a65f9320d7202809289a4de50032892a282c8e73970057b87bf58899ed5f4849` |
| `old_model/kamala_harris_approval_old_model.csv` | 84,376 | `7cb826b1b247fdcb7fcbb941586c1b0c042f39a45f5828c40d3c6e3dfd8431b8` |
| `old_model/mike_pence_favorability_old_model.csv` | 46,274 | `4e174e4affc7dfedb847d75cc1fbb162eba61ffb77961085e45c224a71613f03` |
| `old_model/nikki_haley_favorability_old_model.csv` | 23,681 | `edbba323c9c857adffe991cb4ce4720a33944828a0e4349b5a75a8b019bbddc3` |
| `old_model/ron_desantis_favorability_old_model.csv` | 48,231 | `60a6d875a0b201f29280facd6fe59d26fe147005445790676ec281fbc6ab6e20` |
| `polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv` | 1,604,311 | `c66cf38aa566c3dfa0b50823e8259d9631bfb5ab830c18af13dd54204a8d8b35` |
| `polls/2024-averages/presidential_primary_averages_2024.csv` | 11,407,331 | `0d22110875abddbed1b0709553ba9e2c20e459f0ca8254961e321c9ac18791cc` |
| `polls/pres_pollaverages_1968-2016.csv` | 50,438,309 | `b897a8bc5f17ad0a2e959422cb8ec480dab5fcf25555b8eaaed60472ce68efcd` |
| `polls/pres_primary_avgs_1980-2016.csv` | 30,087,513 | `d30dd11829cd8748cbe3bfbb326d7708f03f3c3abe323edf43d29c0f7501944d` |

The 2024 general-average file is explicitly uncorrected. The 12 rows do not establish corrected 2024 or 2020 coverage. These files are not in P2D main or Agora main until PR #5 is merged; no raw data was added to Agora.

**Other packages:** MEDSL V20 is absent; PR #5 says Dataverse requires a guestbook response and none was submitted. M5 files are absent and remain blocked on the owner's Kaggle terms review; Rossmann was not selected. Ember's official monthly CSV is absent and awaits owner approval; do not substitute the older third-party 16-Nov candidate. No complete three-package manifest exists.

No raw benchmark files were downloaded by ChatGPT, no dataset was imported into Agora, and no simulation or validation was run.

## 8. Owner approvals received — 23 November 2026 (status, not milestone completion)

### A–D design acceptance

The owner explicitly accepted Claude's written 23 November A–D design approval in the owner's chat message. This is acceptance of the design decisions, not an expansion of repository-path authorization. Within `agora/sim/**`, the only authorized path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized.

### Run approval — received, dormant

**Owner's run approval received 23 November 2026; status: RECEIVED, DORMANT.** The owner's approved scope is exactly one run per frozen configuration on the election, retail and adoption public datasets named in the frozen protocol, no tuning and no reruns for better numbers, all results reported including losses to the naive baseline, and no NCC, Nutrivance or P2D data.

This approval remains dormant until all preconditions are met: the protocol is separately frozen by the owner's freeze approval below; the complete selected datasets and per-file SHA-256 manifest are committed in the owner-controlled private repository; required implementation slices are merged and Claude records M3 reached; and the independent evaluator and custody are in place. Claude reports source/destination verification complete for the 12 FiveThirtyEight CSVs and the manifest file SHA-256 is recorded, but P2D PR #5 remains unmerged and the complete all-package manifest, corrected-2024/2020 coverage and MEDSL, M5/Rossmann and Ember files remain incomplete. This record does not authorize a run now, a second run, prediction enablement or any data outside the named public sets. No run has been made.

### Owner freeze sentence — received but incomplete; protocol NOT frozen

The owner supplied this sentence on 23 November 2026:

“I approve freezing `docs/VALIDATION_PROTOCOL.md` as merged at commit 34e5cc39b2bb9f53ca6be0dc057de53e5aa5532c, with dataset manifest `<sha>` and evaluator ChatGPT (separate process, sees only the frozen protocol, manifest and raw outputs). This approves no run and no flag change.”

The evaluator name is recorded as ChatGPT. The sentence is **not effective** because the manifest value is the literal placeholder `<sha>` and no complete all-package committed per-file manifest is available. The FiveThirtyEight sub-manifest SHA-256 recorded above is not a substitute for the complete manifest hash. The owner approved B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, and LLM temperature 0 with cache on; these values become effective only when merged into the protocol and covered by a complete freeze sentence. The protocol stays draft/unfrozen.

To make a freeze effective, the owner must re-paste the freeze sentence with the new merged protocol commit SHA and actual complete dataset-manifest SHA after all files, licences, parameters and evaluator custody are verified. This approves no run and no flag change. `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.