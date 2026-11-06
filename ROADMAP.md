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
- [x] The report agent searches simulation activity directly (post index) instead of writing it back into the graph

## Phase 2b: All major platforms and the local website (this release)
- [x] 11 platforms in three kinds (feed, forum, chat), each with its own follow graph, writing style and vocabulary
- [x] `agora web`: a local website covering upload and prompt, build progress, graph, setup review and editor, simulation control with live feeds and charts, and a results view
- [x] Local-only safety: binds to localhost, checks the host header, requires a custom header on every change, never touches paths outside the workspace

## Phase 3: Report and interaction (this release)
- [x] Analysis layer that computes every number deterministically: opinion shifts, for/against shares, actions as a share of the people actually eligible, decisions with each voter's reason, influencers, most-engaged posts, recurring phrases, busiest groups, cost per outcome
- [x] Report agent that writes section by section from those numbers and from real posts found by search. Invented numbers and citations are removed. Outputs a printable HTML report and Markdown
- [x] Ask questions about the results (answers cite real posts)
- [x] Chat with anyone from the simulation, using their persona, memory, posts, votes and actions
- [x] Interview a group: the same question to a sample of AI voices, with a yes/unsure/no tally
- [x] Add news or an official post while a run is going (stored with the run, so resume stays exact)
- [x] Fork a study to try a variation, then compare studies side by side
- [x] Website: Report and Interact steps, an "add an event" box, Fork, a Compare page. Command line: `report`, `ask`, `chat`, `interview`, `inject`, `fork`, `compare`

## Phase 4: Analytics
- Seed opinions from real data (reviews, comments, surveys, sales)
- Fit opinion-dynamics and conversion parameters to observed results
- Backtests: hide recent data, predict it, and score the error
- Monte Carlo ensembles: ranges and probabilities, plus sensitivity to each assumption

## Phase 5: Product
- Web UI polish: PDF export button, guided tour, saved interview sets
- Windows installer, Docker image, Mac and Linux packages
- Documentation and demo scenarios

## Licensing and compliance (with Phase 5)
- `NOTICE` and third-party licence list for all dependencies (and audit them in CI)
- Show model licence notices when a model is used (e.g. "Built with Llama")
- Contributor guidelines (CONTRIBUTING, DCO sign-off), code of conduct, security policy
- Name and trademark check before public launch
- Data and privacy notes: what stays local, how to share projects safely
