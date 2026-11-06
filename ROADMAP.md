# Roadmap

Agora aims to cover the full multi-agent social simulation pipeline — graph,
environment, simulation, report, interaction — and add the analytics layer most
LLM swarms lack.

## Phase 1: Core engine (this release)
- [x] Swappable model backends (Ollama, OpenAI-compatible, mock), response cache, model policy
- [x] Hardware detection and suggested sizes
- [x] Project folders with an SQLite store, atomic rounds, and exact resume after a crash
- [x] Simulated X, Reddit and WhatsApp groups with feeds and ranking
- [x] LLM voices with persona and memory, plus a crowd driven by opinion dynamics
- [x] Events, polls/committee decisions, conditional events, conversions, trial experiences
- [x] CLI: `hardware`, `new`, `check`, `run`, `status`, `feed`

## Phase 2: Knowledge graph and personas
- Import PDF, DOCX, TXT, MD, CSV and web pages; extract entities, relations and claims with the local model
- Store the graph (NetworkX) and explore it interactively
- Generate segments, personas, accounts and spaces from the graph to draft `scenario.yaml`
- Long-term agent memory backed by the graph

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
- Web UI: live graph, feeds, run control, report
- Windows installer, Docker image, Mac and Linux packages
- Documentation and demo scenarios
