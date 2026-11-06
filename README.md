# Agora

**Open-source, fully local multi-agent social simulation and prediction engine.**

Describe a situation, and Agora fills a small world with people who have personas,
memories and opinions. They talk to each other on simulated **X**, **Reddit** and
**WhatsApp-style groups**, react to news and decisions, and take real-world actions
such as registering, buying or voting. You get a prediction of what people will say
and do, with numbers you can check.

- **Fully local.** Uses your own model server (Ollama, llama.cpp, LM Studio, vLLM, or any
  OpenAI-compatible server). By default nothing leaves your machine or private network.
- **Runs on modest hardware.** A hybrid crowd: a few dozen *LLM voices* think and write,
  and thousands of *crowd agents* follow opinion-dynamics maths, reading, liking, voting,
  sharing and converting. An 8 GB laptop runs the demo overnight, and a GPU server runs
  thousands of voices.
- **Stop and resume any time.** Every round is saved atomically. Close the lid, reboot,
  or move the project folder to another machine, and the run continues to exactly the
  same result.
- **Reproducible.** The same seed gives the same world. Model replies are cached in the project.

> **Status: Phases 1 and 2 are done** (core engine, then upload, knowledge graph and automatic
> setup). Coming next: a report agent and chat with agents (3), data calibration with
> backtests and probability ranges (4), and a web UI with installers (5). See [ROADMAP.md](ROADMAP.md).

## Quick start: upload and ask

```bash
pip install -e .                      # Python 3.10+
ollama pull llama3.2:3b               # or any model server, see below
agora create my-study --docs plan.pdf notes.docx survey.csv \
     --prompt "How will residents react to the free sample, and how many will buy?"
agora run my-study                    # Ctrl+C any time; run again to resume
agora status my-study
```

`create` runs the first two stages:

1. **Upload:** reads your documents into chunks and copies them into the project.
2. **Graph:** the model proposes entity and relation types for your question, extracts
   them from every chunk, and merges duplicates and acronyms. Open
   `my-study/graph.html` to explore the result offline.
3. **Setup:** from the graph and your prompt, the model drafts who reacts (segments),
   who speaks or decides (accounts), where people talk (groups), what happens when
   (timeline and decisions), what to predict (actions), and an individual persona for
   every LLM voice. The result is a plain `scenario.yaml` you can edit.

The population size is chosen to fit about 12 hours on this machine (`--hours` to change it).
Use `--fast` to build the graph without the model, and `--mock` to try the whole pipeline
in seconds with no model at all. `agora graph my-study --add more.pdf` adds documents later.

## Quick start: hand-written scenario

```bash
agora hardware                        # what this machine can handle
agora new my-run --from scenarios/nutrivance_sampling
agora run my-run --mock               # 2-second smoke test, no model needed
```

With a real model, using [Ollama](https://ollama.com):

```bash
ollama pull llama3.2:3b
rm -r my-run && agora new my-run --from scenarios/nutrivance_sampling
agora check my-run                    # validates and estimates run time
agora run my-run                      # Ctrl+C any time; run again to resume
agora status my-run                   # polls, opinion shift by segment, conversions
agora feed my-run --platform whatsapp # read what people said
```

To use another server, set it in `scenario.yaml`, or pass `--backend openai --url http://localhost:8080 --model <name>`.

## How a round works

1. Scheduled **events** fire: news, official posts, and **polls**. A poll is a decision by
   a group, such as an association committee voting on a proposal. Later events and
   actions can depend on its result.
2. Agents wake up based on their activity level and the time of day.
3. Each agent gets a **feed**:
   - X ranks posts from people they follow, trending posts and recommendations.
   - Reddit shows hot threads in their communities.
   - WhatsApp shows unread messages in their groups.
4. **LLM voices** read their feed, memory and persona, then decide what they think and
   do: post, reply, like, repost, forward, vote, follow, or take a real-world action.
5. **Crowd agents** update their opinion with a Friedkin-Johnsen / bounded-confidence
   rule: posts from influential authors move them, views too far from their own are
   ignored, and stubborn people drift back toward where they started. They like, vote
   and share, and convert with a logistic model of stance and exposure.
6. Everything is saved in one transaction.

## Scenario files

A project is a folder with `scenario.yaml` (inputs), `agora.db` (everything that
happened) and, when created from documents, `graph.db`, `graph.html` and `sources/`. The demo in [`scenarios/nutrivance_sampling`](scenarios/nutrivance_sampling/scenario.yaml)
shows every feature:

| Section | What it defines |
|---|---|
| `segments` | Groups of people: share, persona, starting opinion, stubbornness, activity, influence, platforms |
| `accounts` | Named agents: a brand, committee members, journalists |
| `spaces` | WhatsApp groups and Reddit communities, with who joins them (`exclusive` = one home per person) |
| `events` | `news`, `post` and `poll` at given rounds, optionally only `when` a poll passed |
| `conversions` | Real-world actions to predict, with an open window, prerequisites, eligibility, crowd odds and an optional `experience` (e.g. trying the product shifts opinion) |
| `voices` | Optional individual personas for LLM voices (drafted by `create`) |
| `llm` | Backend, model, URL, parallel requests |

All adoption and opinion numbers in a scenario are **assumptions** until they are
calibrated against real data (Phase 4). Read early results as relative comparisons
("approach A beats B"), not as exact forecasts.

## Models

Agora refuses some model families by default under the project's model policy (see
`BLOCKED_FAMILIES` in `agora/llm/base.py`). Override it with `allow_blocked_models: true`.
Suggested models by machine: `llama3.2:1b` or `llama3.2:3b` (8 GB laptop), `gemma3:4b`
(16 GB), `llama3.1:8b` (6 GB+ GPU), `gemma3:12b` (12 GB+ GPU), `llama3.3:70b` (server).
Model licences apply. For example, Llama requires "Built with Llama" attribution.

## Development

```bash
pip install -e .[dev]
pytest
```

The tests cover determinism, resume after a crash in the middle of a round, gated
events, malformed model output, and the HTTP backends (using a fake server).

## Licence

Apache License 2.0. See [LICENSE](LICENSE).
