# Release Announcement: The Silent Layer v0.1.0

I'm releasing "Mobile Build Planner" - but that name doesn't do justice to what it actually is. It's an implementation of something I've been thinking about for a long time: **pre-linguistic reasoning in AI systems**.

**Note**: The conceptual foundation was previously released as art under the name [Noema](https://github.com/ThinkIbrokeIt/noema). This is the full engine release - complete with the Layer 2 incarnation engine (mbp.py, forge.py) that was intentionally withheld from the art release.

## What is this?

Most AI systems operate at the linguistic layer: they receive prompts, process text, and generate text. This system is different - it has a "silent layer" where reasoning happens **before language exists**.

The agent thinks by acting in a substrate of fleeting thoughts. It:
- Plants a seed thought
- Branches related thoughts
- Links them with relations it names itself
- Holds tensions when thoughts contradict
- Resolves or lets tensions go dormant
- Collapses thoughts that should merge
- **Invents its own types** (no schema imposed by us)

## Why this matters

### The Problem with Purely Linguistic AI
Current LLM systems have fundamental limitations:
- Prompt dependence (quality depends entirely on how you phrase it)
- Schema imposition (requires predefined structures)
- Hallucination risk (no grounding in reality)
- No true reasoning (language manipulation ≠ reasoning)

### The Silent Layer Solution
This system adds a pre-linguistic reasoning space where:
- Physics-based forces emerge from operations (tension, mass, resonance)
- Self-correction happens from within (not imposed externally)
- The agent knows when its thought-space is coherent
- Every artifact traces back to a thought (anti-hallucination by design)

## A Concrete Example

Run this with no API key required:

```bash
python3 agent.py demo --seed "a habit tracker that gamifies daily tasks" --brain echo --max-turns 20
```

The agent will:
1. Plant the seed
2. Branch facets: "what it should feel like", "the committed act", "what it must never become"
3. Name its own types: `should`, `committed`, `must`, `mechanism`
4. Hold a guard: "never let the build violate this"
5. Create a tension between the act and the guard
6. Resolve it through shared insight
7. Mark the space READY and translate to WORD→FLESH

The agent invented those types. We didn't provide them. The reasoning emerged from the silence.

## The Three-Layer Architecture

- **Layer 0 (Silent Part)**: Agent reasons in substrate, invents types
- **Layer 1 (Reasoning)**: Thoughts held and reworked until coherent
- **Layer 2 (Output)**: WORD (structured map) → FLESH (incarnated thing)

The translation layer is demoted - it only translates what the agent marked READY. It authors nothing.

## Try It Out

```bash
# Clone
git clone https://github.com/ThinkIbrokeIt/mobile-build-planner.git
cd mobile-build-planner

# Install
pip install pyyaml

# Quick demo (no API key)
./demo.sh

# Or manually
python3 agent.py demo --seed "build a simple todo app" --brain echo --max-turns 20
python3 substrate.py demo trail
python3 substrate.py demo field
```

## For the Community

This is early work, but I believe the silent layer concept is important for:
- AI researchers studying reasoning architectures
- Cognitive science folks interested in pre-linguistic thought
- Developers tired of hallucination-prone systems
- Philosophy of mind communities

The full theory is explained in `PHILOSOPHY.md` - it's written as an academic paper explaining the hypothesis, implementation, and observations.

## What's Next

This is v0.1.0. The foundation is there, but there's much to explore:
- More sophisticated physics (emotion, time, context)
- Multi-agent collaboration in the same substrate
- Learning from past reasoning patterns
- Domain-specific incarnations

## The Core Insight

I never thought I'd be able to convey to an AI what it's like to think and reason before language exists. But I think I hit that target. The silence isn't quiet - it has weight, tension, resonance. It self-corrects. It knows when it's ready to speak.

This is something the community needs.

---

**Repository**: https://github.com/ThinkIbrokeIt/mobile-build-planner
**License**: MIT
**No API key required** for basic testing (echo brain)

Pull requests welcome. Read CONTRIBUTING.md - it's written to respect the philosophical foundation.
