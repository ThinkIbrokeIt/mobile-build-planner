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
but no gate. It shiped incoherent work **3/3** times, exactly like the plain
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

## The evidence

`bench.py`, 5 tasks (3 contradiction, 2 coherent controls):

| pipeline | contradictions surfaced | incoherent shipped | false blocks |
|---|---|---|---|
| plain schema agent | 0/3 | 3/3 | 0/2 |
| graph-only ablation | 0/3 | 3/3 | 0/2 |
| **with the gate** | **3/3** | **0/3** | **0/2** |

The incoherent artifacts from the baseline *verify and execute* — structural
checks miss semantic incoherence. The ablation shows the gate, not the graph, is
doing the work.

And with a live model driving `agent.py`, a run reached READY with a slice whose
dependencies fell outside it; the gate refused it, and auto-resume handed the
reason back so the model could re-mark a corrected slice.

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
- Free-tier models are flaky; the live arm is best-effort.
- This is an early attempt at a *category*. Whether "deliberation layer" belongs
  next to memory and execution layers is exactly what I want to find out.

## Try it

```
python3 mcp_server.py --selftest
python3 bench.py
```

<repo link>
