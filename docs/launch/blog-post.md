# Your agent ships incoherent work — structural checks won't catch it

*Draft. Lead with the failure, not the philosophy.*

## The failure

I generated an admin dashboard spec with an agent. It passed `verify`. It built.
It ran. It also contained, three lines apart:

- "admins must see all data"
- "no user data is exposed without explicit consent"

Two requirements in direct conflict, shipped as if both were fine. Nothing
caught it, because nothing was looking for *conflict*. The output was valid. It
was just incoherent.

This is the shape of most agent failures that matter. Not malformed JSON —
contradictory intent that survives every structural check.

## Why schema agents don't catch it

Schema/tool-calling agents are excellent at **execution**: call tools, emit valid
structure. They are poor at **deliberation**: holding several partially-competing
requirements at once, noticing when two of them fight, and deciding when the set
is coherent enough to ship.

A graph-based scratchpad helps a little — until you measure it. We built the
graph-only version as an ablation: same thoughts, same links, same contradictions,
but no gate. It shipped incoherent work **3/3** times, exactly like the plain
baseline. Structure alone buys nothing.

## What we built

A **deliberation layer with a contradiction gate**, exposed over **MCP**:

- Thoughts live in a substrate: `branch`, `link <how>`, `name <type>`, `hold`,
  `contradict`, `resolve`, `release`, `ready`.
- A **salience field** scores each thought from named signals — conflict,
  reference, recency, proximity, mass — with every weight in one loggable config.
  No hidden constants.
- **Open contradictions are first-class.** They show up in the field, and the
  gate refuses to incarnate a ready slice while one is unresolved. It can be
  resolved, or honestly set aside (dormant). Silent incoherence is not allowed;
  deliberate deferral is.
- The output stage (WORD → FLESH) *enforces* the gate and traces every artifact
  back to the thoughts that produced it.

Because it's MCP, your existing agent stays your agent. It reasons in the
substrate when it needs to hold a conflict, then commits a coherent slice to
your normal output schema.

## The evidence — two claims, measured separately

It's tempting to say "the substrate catches contradictions." That's two claims
wearing one coat, and only one is hard. So `bench.py` measures them apart.

### Claim 1: gating — given a conflict is recognized, does the gate stop it?

3 tasks with a planted requirement contradiction, 2 coherent controls:

| pipeline | contradictions surfaced | incoherent shipped | false blocks |
|---|---|---|---|
| plain schema agent | 0/3 | 3/3 | 0/2 |
| graph-only ablation | 0/3 | 3/3 | 0/2 |
| **with the gate** | **3/3** | **0/3** | **0/2** |

The incoherent artifacts from the baseline *verify and execute* — structural
checks miss semantic incoherence. The ablation shows the gate, not the graph, is
doing the work.

### Claim 2: detection — does an agent find conflicts without being told?

3 **external, unlabeled** tasks where the conflict is not pre-marked:

| arm | detected | incoherent shipped when detected |
|---|---|---|
| deterministic pipelines (all) | 0/3 | 3/3 |
| live model, spontaneous | 0/3 | — |
| live model, prompted to look | 2/3 | **0/3** |

The deterministic pipelines — including this one — cannot detect an unlabeled
conflict. That's not a bug to hide; it's the boundary of the claim. A live model
found 2/3 when told to look, and *when it did*, the gate blocked the incoherent
ship every time. And with a live model driving `agent.py`, a run reached READY
with a slice whose dependencies fell outside it; the gate refused it, and
auto-resume handed the reason back so the model could re-mark a corrected slice.

**The honest summary:** the gate does the gating; the model does the detection.
If you want the first without the second, this is what it looks like.

## The idea underneath

There's a reason this is called the *silent layer*. The thesis — developed as art
under the name Noema — is that reasoning has a moment before language, where a
mind holds a problem as weight and tension rather than as sentences. We don't
claim an LLM literally thinks pre-linguistically. But the *design stance* — give
the agent a place with weight, where conflicts are physical and a gate stands
between thought and word — turns out to be practically useful, not just poetic.

## Honest limitations

- The benchmark is small, and the deterministic pipelines are scripted. Treat the
  numbers as a demonstration of the mechanism, not a leaderboard.
- Detection is the weak link, and it's the model's, not the layer's. The
  substrate only helps once a conflict is named.
- Free-tier models are flaky; the live arm is best-effort.
- This is an early attempt at a *category*. Whether "deliberation layer" belongs
  next to memory and execution layers is exactly what I want to find out.

## Try it

```
python3 mcp_server.py --selftest
python3 bench.py
```

https://github.com/ThinkIbrokeIt/mobile-build-planner
