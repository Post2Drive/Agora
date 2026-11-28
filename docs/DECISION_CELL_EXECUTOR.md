# Decision cell executor: design note (first slice)

Status: library only, 28 Nov 2026. Decided by the Claude session that wrote it, under the owner's instruction of 26 Nov 2026; not independently reviewed. Mock backend only: nothing it produces is a forecast. `VALIDATED_PREDICTION_ENABLED` stays False.

Why: `record_run_result` records what a result rests on only if its caller remembers to call it. The executor makes the gate, the run and the record one call, `execute_event_fork`, and releases output only after the record exists.

## Decisions

| Question | Decision | Reason |
|---|---|---|
| Which option first? | FORK_FROM_EVENT only; all others are refused before the gate. | The spec's with-and-without comparison, using the existing verified `Simulation.fork_from`. |
| What is added to branch A? | Every listed statement of the item, in its recorded wording, as `news` in the round after the event round, with no opinion shift. The caller chooses nothing. | The gate checks the wording against the recorded list and hashes the labels into the action fingerprint, so a second approval covers what runs. A caller-supplied event or shift would not be covered by either. A subset is a CHANGE_INPUTS matter. |
| Who works out cost and snapshot status? | The executor, from the source project. The snapshot probe is a real fork into a throwaway directory. | A caller cannot understate the budget or assert that a snapshot verifies. |
| How is the without-event branch recorded? | It is not recorded on its own. The two branches are one result, the comparison, whose hash covers both final states. | The comparison rests on the item, so stamping it is correct. A stamp on the baseline alone would be false, so the baseline is not offered as a result. |
| What if the run succeeds and recording fails? | No output is released. Branches are built in a staging directory that moves to its final place only after the record is written and the stamps are read. | An unrecorded result could never be stamped. |
| What if recording succeeds and a later step fails? | The record stays, the output is removed and the result id is spent. | A record without output misleads nobody; output without a record could. This includes a record committed but not anchored. |
| Kill switch | Polled before the gate, before every round and before recording; only exactly `False` continues. | Fail closed. |
| Reading | `read_event_fork` returns the comparison and its current stamps together, and refuses an unrecorded result, a changed manifest or a changed branch database (including changes still in the write-ahead log). | A later retraction reaches whoever reads the result through this call. |

## Limits

- `source`, `out_dir`, the study state, the kill-switch probe, statement sources and judgments, and any extra basis items or parent results are trusted service inputs. Nothing proves that `source` is the project of that study.
- If `source` was itself produced from a recorded result, the service must name it as a parent, or retractions behind it are not carried over.
- A process that dies mid-run leaves a `.executing` directory that blocks that result id until an operator removes it.
- The read check covers the manifest and the two branch databases, not the reply caches or other files. Someone who can write the output directory can still copy files from it without using this call, and so without stamps.
- Reads perform no permission check. There is no service boundary, command, screen or report; adding a network service needs a separate security review.

## Not built

CONTINUE, FORK_FROM_EARLIER, RERUN_FROM_START and CHANGE_INPUTS execution; a segment-level comparison view; live model backends; governed or signed-receipt runs (`fork_from` refuses governed sources).
