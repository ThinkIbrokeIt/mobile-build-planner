# Mobile Build Planner — the silent layer
=========================================

The thing being built is the SILENT PART. Not the scaffold, not the tooling.
The pre-word thought — how a mind holds a problem before language exists,
and the reasoning that moves inside it. That is what nobody has replicated,
and that is what this is for.

**This is the full engine release.** The conceptual foundation was released
as art under the name [Noema](https://github.com/ThinkIbrokeIt/noema).

## The three layers (as defined)
  Layer 0 — THE SILENT PART. The seed is planted ("when a thought enters
            my head"). The agent, already silent, reasons inside a substrate of
            fleeting thoughts that lead to thoughts. It invents its OWN types.
            No prompt format, no schema. It thinks by acting.
  Layer 1 — THE THOUGHTS PUT THROUGH REASONING. The agent's silent map,
            held and reworked (branch, link, contradict, hold, collapse,
            retract) until it is coherent. The structure itself refuses to
            linearize if it is circular — self-correction, from within.
  Layer 2 — THE OUTPUT. Only here do WORD (structured map) and FLESH
            (incarnated thing) appear. mbp/forge are DEMOTED to this layer:
            they translate a slice the agent marked READY into buildable output.
            They enforce the gate. They author nothing.

## The pieces
  substrate.py  Layer 0/1. A space of operations, not a file we wrote for
               the agent. Operations (the fleeting thoughts):
                 seed <text>            plant the first thought.
                 branch <from> <text>    a thought grows from another.
                 link <a> <b> <how>      connect (agent NAMES the relation).
                 unlink <a> <b> [how]    retract a connection (reasoning moves).
                 contradict <a> <b>        mark two thoughts in tension.
                 resolve <a> <b> <how>    dissolve a held tension; declare HOW
                                           they reconcile. the raw contradiction
                                           clears -- consciously closed, not retracted.
                 hold <a> <note>          sit with a thought, unresolved.
                 collapse <a> <b>          one thought absorbs another.
                 name <id> <type>         agent declares the KIND (invents types).
                 ready <ids...>           agent marks a coherent slice.
                 trail                   show the thought-trail.
                 field                   show the SALIENCE FIELD (see below).
                 drift                   one turn of automatic field motion.
                 types                   show the agent's own kind vocabulary.
               Storage: projects/<root>/substrate.yaml.

  physics.py    Layer 0 FIELD. The silence has WEIGHT, not just edits. Every
               force EMERGES from acts the agent already performs — no schema,
               no hardcoded types:
                 contradict -> opposite charge + repulsion tether (tension)
                 hold       -> rest mass; heavy thoughts resist collapse
                 collapse   -> charge/mass transfer to the absorber
                 link <how> -> same `how` across pairs = RESONANCE (attraction)
                 name <type>-> same (canonical) type across thoughts = KIND-FIELD
                               (the agent's OWN vocabulary becomes gravity)
               SALIENCE is a single, auditable score per thought built from
               named signals — conflict, reference, recency, proximity, mass —
               with every weight in one loggable SalienceConfig (no scattered
               magic numbers). salience_report() shows the component breakdown.
               OPEN CONTRADICTIONS ARE FIRST-CLASS: open_tensions() returns the
               unresolved ones, the field surfaces them, and forge refuses to
               incarnate a ready slice while an active tension is open. Dormant
               tensions (set aside honestly) do NOT block. Proximity is felt,
               not semantic. Tension DRIFT: a held contradiction RIPENS each
               turn; if the agent never resolves it, it goes DORMANT.
               pull_vector() suggests what the silence leans toward; the agent
               still disposes.

  agent.py     The silent LOOP. Drives the substrate autonomously. Given the
               seed, it decides (one operation per turn) what to branch, link,
               retract, hold, name — and when the space is coherent, marks it
               READY. Brains:
                 --brain openrouter  the model (default slug tencent/hy3:free)
                                     reasons; falls back to echo on API error.
                 --brain ollama     the model at localhost:11434 reasons;
                                     falls back to echo if unavailable.
                 --brain echo        built-in thought-mover (no model; proves
                                     loop). NOW PHYSICS-AWARE: it disposes
                                     toward the field's leans, only branching
                                     facets when the field is silent.
               Each turn the loop runs drift() (self-correction from within)
               and prints the field so the gravity is visible. When it says
               READY, the loop calls forge to translate.

  forge.py    Layer 2 translator. `from-substrate <root> --name X` reads the
               agent's READY slice and turns it into WORD->FLESH. It HONORS
               the agent's own relation vocabulary (needs = dep; references =
               not a dep; etc.) and enforces the gate. Also keeps the older
               recursive `build` harness for non-agent use.

  mbp.py      The single-layer engine. IDEA->WORD->FLESH with a verify gate.
               Pure Layer 2 now — the output stage.

  mcp_server.py  The substrate AS MCP TOOLS. A dependency-free MCP server
               (JSON-RPC 2.0 over stdio, stdlib only) so a schema-bound agent
               can drive deliberation through substrate_* tools, watch the
               salience field / open contradictions via substrate_snapshot, and
               commit a coherent slice with substrate_commit (which runs forge
               and returns the verified artifact). The deliberation layer
               underneath normal tool-calling agents.

## Installation
  # Requirements: Python 3.8+, pyyaml
  pip install pyyaml

  # Clone and run
  git clone <repository-url>
  cd mobile-build-planner

## Quick Start (No API Key Required)
  # Test with the built-in echo brain (physics-aware, no external service)
  python3 agent.py demo --seed "build a simple todo app" --brain echo --max-turns 25

  # The agent will reason autonomously. When coherent, it marks READY and
  # translates the thought-space into WORD->FLESH. Inspect the reasoning:
  python3 substrate.py demo trail
  python3 substrate.py demo field
  python3 mbp.py verify demo__incarnated

## Usage (the real path)
  # 1. plant the seed (the one human act: a thought enters the head)
  python3 agent.py <root> --seed "..." --brain openrouter

  # 2. the agent reasons on its own; the FIELD moves underneath (drift runs each
  # turn, the silence leans toward ripened tensions / resonances). when coherent
  # it marks READY and the loop translates the slice into flesh. inspect:
  python3 substrate.py <root> trail
  python3 substrate.py <root> field
  python3 mbp.py verify <root>__incarnated

## Using Real Models
  # With Ollama (requires ollama running at localhost:11434)
  python3 agent.py demo --seed "..." --brain ollama --model qwen2.5:3b

  # With OpenRouter (requires OPENROUTER_API_KEY environment variable)
  export OPENROUTER_API_KEY=your_key
  python3 agent.py demo --seed "..." --brain openrouter --model tencent/hy3:free

## Anti-hallucination
The map (the agent's reasoning) is the source of truth. mbp verify traces
every incarnated file back to a thought. If a slice is circular or incoherent,
the substrate refuses to flesh it — the silence corrects itself before the word.

## MCP — the framing, implemented
The README once said MCP was an ANALOGY. It is now real: `mcp_server.py` is a
dependency-free MCP server (JSON-RPC 2.0 over stdio) that exposes the substrate
as tools. A schema-bound agent (Claude, an IDE, another agent) drives
DELIBERATION through `substrate_*` tools, reads the salience field and open
contradictions via `substrate_snapshot`, then commits with `substrate_commit`
(Layer 2: forge → real artifact + verification). The substrate is not a rival
to schema-based agents; it is the deliberation layer underneath them.

  # run as an MCP stdio server (point your host at this command)
  MBP_ROOT=my-session python3 mcp_server.py

  # or prove it works with no host at all
  python3 mcp_server.py --selftest

Tools: seed, branch, link, unlink, contradict, resolve, hold, collapse, name,
ready, release, journal_write, journal_flip, drift, trail, field, types,
snapshot, commit. Each has a JSON input schema; the substrate still imposes no
schema on the agent's own thought-types.
