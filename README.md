

---

The engine runs on three operational layers:

1. The Seed & The Act (silent reasoning)
   One human plants a thought. The agent doesn't parse prompts—it acts to think: branching, linking, holding tension, inventing its own type names on the fly. No schema. No template. Thinking is the operation.
2. The Weave (self-correcting map)
   Those acts crystallize into a living graph. It holds contradictions, collapses redundancies, and refuses to linearize until the structure is genuinely coherent. Circular logic gets resolved from within—no external forcing.
3. The Translation (structured output)
   Only the "ready" slice gets passed down. Forge/mbp become dumb translators—they render that map into code and docs, but they author nothing. They're just the gatekeeper

---


---

Installation

```bash
pip install pyyaml
git clone <repo-url>
cd mobile-build-planner
```

---

Quick Start (No API Key)

```bash
# Auto-reason with the built-in physics-aware echo brain
python3 agent.py demo --seed "build a simple todo app" --brain echo --max-turns 20

# See what it thought (and how the field moved)
python3 substrate.py demo trail
python3 substrate.py demo field

# Verify the output maps back to its reasoning
python3 mbp.py verify demo__incarnated
```

---

Real Models

```bash
# Ollama (local, port 11434)
python3 agent.py demo --seed "..." --brain ollama --model qwen2.5:3b

# OpenRouter (requires env var)
export OPENROUTER_API_KEY=your_key
python3 agent.py demo --seed "..." --brain openrouter --model tencent/hy3:free
```

---

Anti-Hallucination (The Guard)

Every output file traces back to a thought in the map. If the agent's slice is incoherent or circular, forge refuses to translate. The silence corrects itself before the word appears—no blind generation.

---

MCP Framing (Just an Analogy)

Think of it as a shared shape: a space of small moves the agent makes, thought leading to thought. Not a server—just a substrate.

---

That's the entire manual, gutted and sharpened. Want the full combined doc, or shall I tweak any specific section further?