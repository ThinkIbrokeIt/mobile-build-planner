# Internal brief — introducing the silent layer (team only)

This is OUR document, not the committee's. Present tense, declarative. The
external assets (`show-hn.md`, `blog-post.md`) are a separate later pass.

## Single target
Agent / MCP builders who ship features with multiple constraints and have felt
the "it passed every check and it's still wrong" failure. One target first.

## Position
A **deliberation layer + contradiction gate** that composes with schema agents
over MCP. We are not a rival to tool-calling agents or memory layers; we are the
layer they're missing: a place to hold a conflict, and a gate that won't let one
ship. Offer, not ask.

## Asset stack (keep separate — do not conflate)
- **The gate (product):** `mcp_server.py` + `forge`/`mbp`. Installable, provable.
- **The evidence (proof):** `bench.py` — 0/3 vs 3/3, plus the ablation showing the
  gate (not the graph) is the value; the live-run gate catch; one-command `--selftest`.
- **The theory (soul):** the silent layer / Noema. Motivating *why*, never the
  engineering *what*.

## Sequence
1. Package + quickstart (done): engineer-first README, `examples/`, MCP config.
2. Show HN + blog post (drafted in this folder).
3. Workshop paper on conflict-aware deliberation; harden the benchmark (live arm
   on all tasks, external tasks).
4. One integration (agent framework or memory layer); collect third-party
   replications as social proof.

## Kill signal
If the engineering copy starts leading with "pre-linguistic reasoning" or
"physics," we're off-position. That language lives in `PHILOSOPHY.md` and the art
release. Engineering copy says: conflicts as first-class, the gate, composes via MCP.

## Success metrics
Eval reproductions by others, installs, GitHub stars, external runs of
`bench.py` — not vibes.
