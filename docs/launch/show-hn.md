# Show HN draft

**Title:** Show HN: A contradiction gate for AI agents (MCP)

**Body:**

I kept watching coding agents ship plans that quietly contradicted themselves —
"admins see all data" sitting next to "no data without consent" — and then pass
every structural check, because a plan with a contradiction in it is still a
valid plan. Linters and `verify` steps don't catch it. The model that wrote it
usually doesn't either.

So I built a small **deliberation layer + contradiction gate** that sits between
the model and its output. An agent reasons in a substrate of "thoughts" —
branch, link, name, hold, contradict — and the layer tracks the field around
them (a salience score per thought; open contradictions as first-class objects).
When the agent marks a slice ready, a gate refuses to turn it into output while
an unresolved contradiction is open. It can be resolved, or honestly set aside
(dormant). It speaks **MCP**, so any tool-calling host can drive it.

I split the benchmark into the two claims, because they're different and only
one is actually hard (`bench.py`):

**1. Gating — given a conflict is recognized, does the gate stop incoherent
output?** On 3 tasks with a planted requirement contradiction and 2 coherent
controls:

- plain schema agent — surfaced 0/3, shipped incoherent work 3/3
- graph-only ablation (same thought graph, no gate) — identical: 0/3, 3/3
- with the gate — surfaced 3/3, shipped incoherent 0/3, 0 false blocks on controls

The ablation is the point: merely structuring reasoning as a graph buys nothing.
The gate is what helps. The incoherent artifacts it ships *verify and run* —
which is exactly the failure mode.

**2. Detection — does an agent find conflicts without being told?** On 3
*external*, unlabeled tasks where the conflict is not pre-marked: every
deterministic pipeline detected 0/3, including this one. A live model (OpenRouter,
free tier) spotted 0/3 spontaneously and 2/3 when prompted to look. **When it did
detect one, the gate blocked the incoherent ship 0/3 times.**

So the honest headline: the gate works when a conflict is recognized; *finding*
unlabeled conflicts is the model's job, not the substrate's. That's the split I
wanted to measure, and it's the part I'd most like other agent builders to poke
at.

Try it with no host:
```
python3 mcp_server.py --selftest
python3 bench.py
```

It's Python, stdlib + pyyaml, no service. Caveats: the benchmark is small and the
deterministic pipelines are scripted; the live arm is best-effort and rate-limited.
"Deliberation layer" is my framing, not a proven category. I'm interested in
whether conflict-as-first-class + gate is useful to other agent builders, and
where it breaks.

Repo: https://github.com/ThinkIbrokeIt/mobile-build-planner
