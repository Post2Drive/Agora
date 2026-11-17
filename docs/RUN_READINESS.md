# Run readiness checklist

Docs only. Use before any simulation. Nothing here changes code.

## Code
- [ ] Repo is on `main`, head at or after `514d89d` (PR #8 merge).
- [ ] Tests pass on `main` (last recorded: 206 passed, 17 Nov 2026).
- [ ] No uncommitted changes in the checkout (`git status` clean).

## Model and runtime
- [ ] Ollama is running and `llama3.2:3b` is pulled (check with `GET http://127.0.0.1:11434/api/tags`).
- [ ] The scenario's `llm:` block sets `timeout` (1800 s is the value used by the recent studies).
- [ ] Each progress line shows `unusable 0`. Watch for HTTP 500 and timeout errors.

## Scenario
- [ ] Starting opinions are neutral (no favourite-preference overwrite). Confirmed on `main`.
- [ ] Brand account stance is 0.0 in the scenario, not inherited from an older file.
- [ ] Fresh study folder. Nothing written into an existing study folder.

## Machine
- [ ] Plugged in, lid open or sleep disabled, for the whole run.
- [ ] No other heavy job running on the machine.

## Record
- [ ] Log the commit hash, scenario file, timeout, and start time in the study notes.
- [ ] Note every interruption with its start and end time.
