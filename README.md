# OrgTwin — organisation map, decision memory, incident black box

Instead of asking "what happened?", ask "if I make this change, what else breaks?" — and when something does break, rebuild exactly how.

| Pillar | Module | What it does |
|---|---|---|
| Dependency map | `graph.py` | Weighted graph of systems, agents, processes, data, policies, people. `impact()` walks reverse edges and ranks who is exposed, with the path and the reason. |
| Decision memory (RAG) | `memory.py` | BM25 over decisions/policies/changes, each linked to graph nodes and to the assumptions it relied on. Arabic normalisation. |
| What-if simulation | `twin.simulate()` | Impact ranking + "decisions that assumed this stays as is" + "already appeared in incident X". |
| Black box | `blackbox.py` | Append-only, hash-chained events from humans, agents and systems (actor, permission, inputs, outputs, parent). Tampering is detected. |
| Forensics | `forensics.reconstruct()` | Who started it, data used, permissions used, first divergence (root cause), failed and skipped barriers, linked decisions, loss, detection lag, blast radius. |
| Replay | `forensics.replay()` | Re-runs the recorded trace with candidate controls; blocks cascade downstream; ranks fixes by earliest stop and loss avoided. Healthy runs are checked for false positives. |
| Explanation | `twin.narrate()` | Deterministic text. With `ANTHROPIC_API_KEY` an LLM writes it, but only from the evidence JSON; event ids and numbers are verified and it falls back if anything is not grounded. |

Demo incident `INC-2026-001`: an OCR upgrade misreads 12,500.00 as 125,000.00, PayBot skips PO matching (trusted-vendor exception) and the approval gate, and transfers EGP 125,000. Root cause is the OCR step, not the agent. Replay shows four independent fixes.

```bash
python -m unittest discover -s tests -v
pip install -r requirements.txt && python run_demo.py
```

Open http://localhost:8001 after starting the demo.

## Setup
Optional Anthropic narration reads `ANTHROPIC_API_KEY` from the environment. Copy `.env.example` to `.env` if you use a dotenv loader, or set the variable in your shell. Never commit real keys.

## Honest limits
- Seed data is one fictional finance flow. The graph, decisions and events are hand-written, not discovered. Next step: ingest real sources (ERP/IAM/ticket/audit logs, OpenTelemetry-style traces).
- Edge weights are expert estimates, not learned. Impact scores rank exposure; they are not probabilities.
- Replay is counterfactual on recorded events only. It does not model what a human or agent would have done instead.
- Root cause = earliest data divergence, else earliest control violation. Traces with several interacting causes need richer causal modelling.
- The FastAPI layer and the UI were not executed in the build environment (no FastAPI installed); the core is covered by tests. The LLM path is untested live.
