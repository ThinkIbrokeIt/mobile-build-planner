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
- **The evidence (proof):** `bench.py`, split into two claims so neither hides
  the other:
  - *Gating* (deterministic, 3 planted + 2 controls): 0/3 vs 3/3, plus the
    graph-only ablation proving the gate — not the graph — is the value; 0 false
    blocks on controls.
  - *Detection* (3 external, unlabeled tasks): every deterministic pipeline 0/3;
    live model 0/3 spontaneous, 2/3 prompted; **when detected, the gate shipped
    incoherent 0/3 times**.
  - The live-run gate catch (dangling deps) + auto-resume recovery.
  - One-command `--selftest`.
- **The theory (soul):** the silent layer / Noema. Motivating *why*, never the
  engineering *what*.

## Sequence
1. Package + quickstart (done): engineer-first README, `examples/`, MCP config.
2. Demo asset (done): `scripts/demo.sh`, `docs/demo.cast`, `docs/demo.svg` hero.
3. Benchmark hardened (done): external tasks + live detection + prompted arm.
4. Show HN + blog post (drafted in this folder; finalize against merged numbers).
5. Workshop paper on conflict-aware deliberation.
6. One integration (agent framework or memory layer); collect third-party
   replications as social proof.

## Submission checklist
- [x] Repo public, default branch = `master`, PR #1 merged, branch deleted.
- [x] README hero renders on GitHub (SVG animates; transcript fallback present).
- [x] `python3 mcp_server.py --selftest` and `python3 bench.py` work from a fresh
      clone with only `pyyaml` installed.
- [x] Replace `<link>` placeholders in `show-hn.md` / `blog-post.md`.
- [x] Honest caveat wording settled: gating is the layer's; detection is the model's.
- [ ] Post order: blog first (linkable), then Show HN pointing at it.
- [ ] Watch the first 2 hours of HN comments; answer "strawman baseline" with the
      external/prompted arms, and "the layer doesn't detect" with agreement +
      the split.

## Reply bank (for the first 2 hours)
- *"Your baseline is a strawman."* The deterministic pipelines are scripted — we
  say so. The external/unlabeled set and the live-model arms are the answer to
  "you told it": there, detection is 0/3 spontaneous and 2/3 prompted, and the
  gate still shipped 0/3 incoherent when a conflict was named.
- *"The layer doesn't detect conflicts."* Correct — and we split the benchmark to
  say exactly that. Detection is the model's job; the gate is the layer's. The
  value is refusing to ship what the model already knows is conflicted.
- *"Why not just a system prompt?"* A prompt asks the model to notice; it does
  not persist a conflict object or refuse output. The gate is deterministic and
  mechanical: no conflict marked, no block. A prompt cannot guarantee that.
- *"This is just LangGraph / memory."* Memory stores state; this refuses to
  commit incoherent state. It composes with either — it's an MCP server.

## Kill signal
If the engineering copy starts leading with "pre-linguistic reasoning" or
"physics," we're off-position. That language lives in `PHILOSOPHY.md` and the art
release. Engineering copy says: conflicts as first-class, the gate, composes via MCP.

## Success metrics
Eval reproductions by others, installs, GitHub stars, external runs of
`bench.py` — not vibes.
