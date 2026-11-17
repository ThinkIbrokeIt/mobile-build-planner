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

The claim I actually tested, with a small benchmark (`bench.py`): a plain schema
agent emits structured output but has no representation of conflict. On 5 tasks
(3 with a planted requirement contradiction, 2 coherent controls):

- plain schema agent — surfaced 0/3 contradictions, shipped incoherent work 3/3
- graph-only ablation (same thought graph, no gate) — identical: 0/3, 3/3
- with the gate — surfaced 3/3, shipped incoherent 0/3, 0 false blocks on controls

The ablation is the point: merely structuring reasoning as a graph buys nothing.
The gate is what helps. The incoherent artifacts it ships *verify and run* —
which is exactly the failure mode.

Try it with no host:
```
python3 mcp_server.py --selftest
python3 bench.py
```

It's Python, stdlib + pyyaml, no service. Honest caveats: the benchmark is small
and partly scripted (there's an optional live-model arm), and "deliberation
layer" is my framing, not a proven category. I'm interested in whether the
conflict-as-first-class + gate pattern is useful to other agent builders, and
where it breaks.

Repo: <link>
