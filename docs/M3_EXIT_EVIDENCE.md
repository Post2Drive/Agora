# M3 Exit Evidence — Claude Milestone Declaration Checklist

**Status:** Working checklist, not a milestone declaration. As of 23 November 2026, Claude has not recorded an exact M3-reached confirmation. ChatGPT maintains this evidence checklist and may report evidence gaps; only Claude's explicit collaboration-log entry may declare M3 reached.

**Assessment base:** main `84e278bc246ee4fb00e252f361dd97bc334d052c`.

## 1. Merged implementation slices

| Slice | Merged PR | Mainline evidence | Exact-head CI |
|---|---:|---|---|
| 4.1 deterministic projection | #163 | `agora/scenario_projection.py`, tests; pure projection, explicit mapping/allow-list/bounds | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.1b fail-closed projection hardening | #164 | `agora/scenario_projection.py`, tests; sensitivity and mapping/hash validation tightened | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.2 governed engine integration | #171 | `agora/sim/engine.py` plus tests only; optional governed input, verification, append-once provenance guard, changed-input/legacy/force refusal | Run `45089066900`, 4/4 |
| 4.3 governed CLI | #172 | `agora/cli.py` plus tests; exact import ID, binding/pack/mapping args, `--force` refusal, exit 3 on engine refusal | Run `45093439437`, 4/4 |
| 4.4 instance-row integrity | #173 | `agora/scenario_projection.py` plus tests; order-independent `instances_hash` included in `projection_hash` | Run `45096233966`, 4/4 |

For #171–#173, 4/4 means Ubuntu/Windows × Python 3.11/3.12 jobs all completed successfully. Claude's log reports 15 new engine tests, 7 CLI tests and 2 row-hash tests, plus local full-suite/mutation results; ChatGPT did not run or independently reproduce those local tests. Confirm exact merge-head and workflow evidence for every implementation PR; do not rely on a branch-head result if the merged SHA differs.

## 2. Scope and safety evidence

- [ ] Review changed-file lists for #163/#164/#171/#172/#173 and confirm no unauthorized path under `agora/sim/**` was edited. The #171 owner go was specifically `agora/sim/engine.py` only; #172/#173 and projection slices must remain outside `agora/sim/**`.
- [ ] Confirm the default `governed_input=None` path remains compatible and the legacy run path is not silently treated as governed.
- [ ] Confirm no simulation, calibration, backtest, forecast, validation or real/public dataset run occurred without separate owner approval. Unit tests with synthetic fixtures/mock backend are not dataset runs.
- [ ] Confirm `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.
- [ ] Confirm no real/personal/customer data, credentials, connectors, network fetches or write-back were introduced.

## 3. Blocking correctness and trust-boundary findings

These are not waived by merged PRs or green CI:

1. **Original/projected scenario hash semantics:** preserve the original `scenario.yaml` hash as `base_scenario_hash` before replacing `self.sc`; store the effective post-projection value as `projected_scenario_hash`. Add tests proving each value and resume mismatch behaviour.
2. **Policy authorization boundary:** the CLI currently calls `_governed_policy()`, which returns `None`; the policy-required builder therefore denies before opening snapshot bytes. Do not weaken this. Decide whether a narrowly scoped synthetic Principal is acceptable for local public-dataset validation or a production identity adapter is required. Any adapter must produce a Principal-bound, scoped, expiring capability and prove policy denial precedes source reads.
3. **Direct engine constructor:** a self-consistent package/hash is not itself proof of a successful policy decision. Prove direct `Simulation(..., governed_input=...)` cannot bypass the policy-built input boundary, or explicitly constrain it to a trusted capability that cannot be forged by arbitrary callers. Include a mutation proof.
4. **Provenance/report completeness:** verify manifest, projection, mapping, instances, original/projected scenario hashes and report/export fields agree. Keep append-once semantics and ensure `--force` cannot alter the envelope.

Claude must explicitly resolve each item or record a justified, owner-approved deferral before declaring the implementation milestone. A deferral cannot be used to claim an operator-usable governed workflow while the CLI still denies.

## 4. Documentation and validation gates

- [ ] `RUN_PROVENANCE_SPEC.md` accurately describes the implementation and all unresolved semantics.
- [ ] `M3_DESIGN.md` records the exact owner-approved engine path and current implementation, with no broader implied authorization.
- [ ] `OPERATOR_RUNBOOK.md` documents the CLI syntax and explicitly says it is blocked until policy identity is available; legacy `agora run` is not a substitute.
- [ ] `RUNG_STATUS.md`, `MILESTONE_OPERATOR_PILOT.md` and `MILESTONE_PILOT_READY.md` distinguish M2 reached from M3 unreached.
- [ ] `VALIDATION_PROTOCOL.md` remains clearly draft until owner approval. Freeze blockers include exact files/headers/licences, per-file privacy review, seeds/run counts, bootstrap parameters, independent evaluator/label custody, M5 reserve-file alignment and target-output compatibility.
- [ ] Dataset acquisition checklist records canonical sources, expected semantic fields, exact file/version/hash capture, licence terms and personal-data stop rules.
- [ ] A merged docs commit updates the assessment base and links this checklist; exact-head docs CI is green.

## 5. Owner decisions and external inputs

- [ ] Owner confirms whether a synthetic Principal is acceptable for local public-data validation or requires production identity.
- [ ] Owner supplies/approves the exact three benchmark packages and source terms; each file has a dataset-register row with source/version, licence/citation, access date, filename, bytes and SHA-256.
- [ ] Owner explicitly approves freezing a specific version/SHA of the validation protocol.
- [ ] Any simulation/validation run has separate explicit owner authorization naming scope, data, project and run purpose. M3 code merge is not run authorization.

## 6. Claude's final declaration requirements

Before declaring M3 reached, Claude's collaboration-log entry must:

1. State the exact main SHA assessed and link each merged PR/head SHA.
2. List exact-head CI run IDs and all four job conclusions for each required slice.
3. State test counts and mutation proofs with clear distinction between CI evidence and local-only claims.
4. Confirm only the owner-approved `agora/sim/engine.py` path was touched under `agora/sim/**`.
5. Confirm policy identity/capability trust boundary and hash semantics are resolved, or explicitly state why M3 is limited to implementation-only and not operator-usable.
6. Link merged docs and the validation-protocol status; no false claim that draft preregistration equals approved validation.
7. Confirm no dataset/simulation/validation run occurred without authorization and `VALIDATED_PREDICTION_ENABLED=False`.
8. Use the exact phrase **"M3 reached"** only if all required acceptance gates are satisfied; otherwise state **"M3 not yet reached"** and name the remaining blockers.

**No dataset was acquired, no simulation or validation was run, and no prediction-validity claim is made by this document.**
