# Roadmap

Agora aims to cover the full multi-agent social simulation pipeline — graph,
environment, simulation, report, interaction — and add the analytics layer most
LLM swarms lack.

## Phase 1: Core engine (done)
- [x] Swappable model backends (Ollama, OpenAI-compatible, mock), response cache, model policy
- [x] Hardware detection and suggested sizes
- [x] Project folders with an SQLite store, atomic rounds, and exact resume after a crash
- [x] Simulated X, Reddit and WhatsApp groups with feeds and ranking
- [x] LLM voices with persona and memory, plus a crowd driven by opinion dynamics
- [x] Events, polls/committee decisions, conditional events, conversions, trial experiences
- [x] CLI: `hardware`, `new`, `check`, `run`, `status`, `feed`

## Phase 2: Upload, graph and setup (this release)
- [x] `agora create --docs ... --prompt "..."`: upload documents and describe what to predict
- [x] Import PDF, DOCX, TXT, MD, CSV/TSV, JSON and HTML into chunks, stored inside the project
- [x] An ontology built from the prompt, then entity and relation extraction for each chunk (resumable), with alias merging and source facts
- [x] Offline interactive graph viewer (`graph.html`), plus GraphML and JSON export
- [x] Drafts segments, named accounts, groups, timeline, decisions, actions to predict and individual personas, cleaning or replacing any answer it cannot use
- [x] Agents see relevant graph facts each round (BM25 retrieval)
- [ ] Write simulation activity back into the graph (Phase 3, for the report agent)

## Phase 2b: All major platforms and the local website (this release)
- [x] 11 platforms in three kinds (feed, forum, chat), each with its own follow graph, writing style and vocabulary
- [x] `agora web`: a local website covering upload and prompt, build progress, graph, setup review and editor, simulation control with live feeds and charts, and a results view
- [x] Local-only safety: binds to localhost, checks the host header, requires a custom header on every change, never touches paths outside the workspace

## Phase 3: Report and interaction
- Report agent that can search posts, opinions, polls and the graph
- HTML and PDF reports: opinion trajectories, key quotes, themes, conversion funnel, cost per outcome
- Chat with any agent, interview a segment, add an event mid-run, fork and compare scenarios

## Phase 4: Analytics
- Seed opinions from real data (reviews, comments, surveys, sales)
- Fit opinion-dynamics and conversion parameters to observed results
- Backtests: hide recent data, predict it, and score the error
- Monte Carlo ensembles: ranges and probabilities, plus sensitivity to each assumption

## Phase 5: Product
- Web UI polish: chat with agents, report pages, comparing scenarios side by side
- Windows installer, Docker image, Mac and Linux packages
- Documentation and demo scenarios

## Licensing and compliance (with Phase 5)
- `NOTICE` and third-party licence list for all dependencies (and audit them in CI)
- Show model licence notices when a model is used (e.g. "Built with Llama")
- Contributor guidelines (CONTRIBUTING, DCO sign-off), code of conduct, security policy
- Name and trademark check before public launch
- Data and privacy notes: what stays local, how to share projects safely
