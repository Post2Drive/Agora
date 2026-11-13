# Neutral starting opinions

## Problem
In choice mode (`agora/sim/population.py`, the choice-mode block), each agent's
starting stance was overwritten by the highest of its sampled option preferences.
With all option leanings at 0.0, that maximum is about +0.3 for every segment, so
the run starts above the configured segment means.

Observed in ncc-factorial-150/E0_C0_D0: segment starts +0.28 to +0.35 against
configured means of 0.00, +0.05, 0.00, -0.05 and -0.15. The brand account's
configured stance of +0.8 started at 0.00 because account preferences default to 0.0.

## Fix
Keep the sampled stance as the starting opinion. Option preferences still choose the
pack. See `patches/neutral-start-fix.patch`.

## Still needed for a fully neutral run
- Brand account: set `stance` to 0.0 in neutral scenarios. With the fix, its configured
  +0.8 would otherwise apply. Influence 2.0 is a separate design question.
- Re-run all eight factorial conditions after the fix. E0_C0_D0 from the current study
  is not a neutral baseline.
- Check the persona text for tone.

## Not in this branch
The laptop copy of `population.py` also has an exclusive-group change from 8 Nov
(`*.pre_outcome_audit.bak`). It is not in GitHub `main`, so this patch was written for
the laptop file and is not a full sync of the code.
