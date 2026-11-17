#!/usr/bin/env python3
"""
agent.py — the silent loop.
==========================
The agent (already silent) drives the substrate autonomously. It is given the
seed + the current thought-trail, and a vocabulary of operations (the fleeting
thoughts it can think). It responds with ONE operation at a time. We execute it
on the substrate, feed the result back, and repeat. When it emits `ready`, the
loop ends and forge translates the slice into WORD/FLESH.

The agent decides everything: what to branch, what to link, what to retract, when
it's coherent enough to become flesh. We only run its operations and enforce the
gate downstream. The silence moves itself.

Loop protocol (agent's output, one line per turn):
  branch <from> <text>
  link   <a> <b> <how>
  unlink <a> <b> [how]
  hold   <a> <note>
  name   <id> <type>
  contradict <a> <b>
  collapse <a> <b>
  ready   <ids...>
  done    (stop without a ready slice)

Brain:
  --brain ollama   calls Ollama at localhost:11434 (structured, one op/line).
  --brain echo      built-in generic thought-mover (no model needed; proves the
                   loop end-to-end). It is NOT a scripted app — it's a small
                   heuristic that branches on tension, links by theme, and stops
                   when the graph is acyclic and rich enough.

Usage:
  python3 agent.py <root> --seed "..." [--brain ollama|echo] [--model qwen2.5:3b] [--max-turns 40]
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.join(HERE, "substrate.py")
FORGE = os.path.join(HERE, "forge.py")
WORKSPACE = os.environ.get("MBP_WORKSPACE") or HERE   # see substrate.py
PROJECTS = os.path.join(WORKSPACE, "projects")

# Hermes integration
HERMES_PATH = os.path.join(HERE, "hermes_dataset.json")
HERMES_AVAILABLE = os.path.exists(HERMES_PATH)


def sub_path(root):
    return os.path.join(PROJECTS, root, "substrate.yaml")


def load_sub(root):
    p = sub_path(root)
    if not os.path.exists(p):
        return None
    return yaml.safe_load(open(p))


def run_sub(root, *args):
    r = subprocess.run([sys.executable, SUB, root, *args],
                       cwd=HERE, capture_output=True, text=True)
    return r.stdout.strip()


def trail_text(root):
    d = load_sub(root)
    if not d:
        return "(no thoughts yet)"
    lines = []
    for tid, t in d["thoughts"].items():
        kind = t.get("type") or "?"
        lines.append(f"  {tid} ({kind}): {t['text']}")
        for ln in t.get("links", []):
            if isinstance(ln, dict):
                lines.append(f"      -({ln['how']})-> {ln['to']}")
            else:
                lines.append(f"      -branch-> {ln}")
        for c in t.get("contradicts", []):
            lines.append(f"      <> {c}")
        for h in t.get("holds", []):
            lines.append(f"      [hold] {h}")
    return "\n".join(lines)


def has_cycle(d):
    """True if the branch/needs dependency graph has a cycle."""
    nodes = d["thoughts"]
    adj = {n: [] for n in nodes}
    for nid, t in nodes.items():
        for ln in t.get("links", []):
            if isinstance(ln, dict):
                if ln["how"] in ("needs", "depends-on", "branch", "fulfills"):
                    adj.setdefault(nid, []).append(ln["to"])
            else:
                adj.setdefault(nid, []).append(ln)
    seen, stack = set(), set()

    def dfs(u):
        seen.add(u); stack.add(u)
        for v in adj.get(u, []):
            if v not in seen:
                if dfs(v):
                    return True
            elif v in stack:
                return True
        stack.discard(u)
        return False
    for n in nodes:
        if n not in seen:
            if dfs(n):
                return True
    return False


# ---------------------------------------------------------------------------
# OpenRouter brain — real model, same loop
# ---------------------------------------------------------------------------

def _load_openrouter_key():
    """Load OPENROUTER_API_KEY from the hermes .env if not already in env.
    Never returns/prints the key."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    for cand in (os.path.join(os.path.expanduser("~"), ".hermes", ".env"),
                 os.path.join(os.path.expanduser("~"), ".hermes", "config.yaml")):
        if os.path.exists(cand):
            try:
                with open(cand) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OPENROUTER_API_KEY="):
                            return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    return ""


def brain_openrouter(model, root, seed, turn, correction=""):
    import urllib.request, json
    key = _load_openrouter_key()
    if not key:
        return "__ERROR__ no OPENROUTER_API_KEY found"
    ctx = trail_text(root)
    try:
        from physics import field_summary
        field = "\n\n" + field_summary(load_sub(root) or {"thoughts": {}})
    except Exception:
        field = ""
    
    # Add Hermes context if available
    hermes_section = ""
    if HERMES_AVAILABLE and turn > 3:
        try:
            from Echo_x import get_parser, weight_by_field, format_for_brain
            parser = get_parser(HERMES_PATH)
            d = load_sub(root) or {"thoughts": {}}
            th = d.get("thoughts", {})
            keywords = []
            for tid, t in th.items():
                words = re.findall(r"[A-Za-z]{3,}", t.get("text", "").lower())
                keywords.extend(words[:5])
            if keywords:
                results = parser.query_by_context(keywords[:10], limit=5)
                if results:
                    weighted = weight_by_field(results, d)
                    hermes_section = "\n\n" + format_for_brain(weighted, max_results=2)
        except Exception:
            pass
    
    sys_p = ("You are a silent reasoning agent. You think by issuing ONE "
             "operation per turn into a substrate of fleeting thoughts. You "
             "invent your own thought-types. You avoid dependency cycles. When "
             "your thought-space is coherent and rich, mark a slice READY.")
    user_p = f"""SEED thought planted: {seed}

Current thought-space (your own reasoning so far):
{ctx}
{field}
{hermes_section}{correction_block(correction)}

Choose ONE operation. Reply ONLY as JSON:
{{"op": "branch|link|unlink|hold|name|contradict|resolve|collapse|ready|done", "args": "<rest of the line>"}}

Think by issuing ONE operation. Choose from:
  branch <from> <text>     grow a new thought from an existing id
  link <a> <b> <how>      connect two thoughts (name the relation: needs, references, fulfills, contradicts...)
  unlink <a> <b> [how]    retract a connection
  hold <a> <note>          sit with a tension without resolving it
  name <id> <type>         declare what KIND of thing a thought is (invent types)
  contradict <a> <b>        mark two thoughts in tension
  resolve <a> <b> <how>    dissolve a tension you held; say HOW they reconcile
  collapse <a> <b>         one thought absorbs another
  release <id> [note]      let a thought go (the silence decides; never auto)
  journal write <ref> <text> [--share|--private]   write what to remember / share
  journal flip <jid>     change his mind about sharing an entry
  ready <ids...>            your reasoning is coherent; mark a slice for incarnation
  done                       stop without incarnating

Rules: reason from the seed; let thoughts lead to thoughts; name your OWN types;
avoid cycles (a thought must not need its own ancestor). When coherent and
rich, emit ready with the ids worth building. Output ONE JSON object only."""
    schema = {
        "type": "object",
        "properties": {
            "op": {"type": "string",
                    "enum": ["branch","link","unlink","hold","name",
                             "contradict","resolve","collapse","release",
                             "journal","ready","done"]},
            "args": {"type": "string"},
        },
        # args REQUIRED so the model never emits a bare "branch" with no text.
        "required": ["op", "args"],
    }
    last_err = ""
    # ONE attempt, fast timeout. On any failure return __ERROR__ immediately so
    # the loop falls back to echo instead of freezing on a 3x120s retry.
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "system", "content": sys_p},
                             {"role": "user", "content": user_p}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "op", "strict": True,
                                                    "schema": schema}},
                "stream": False,
            }).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=45) as r:
            obj = json.loads(r.read().decode())
        raw = obj["choices"][0]["message"]["content"]
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            data = {}
        op = (data.get("op") or "").strip().lower()
        args = data.get("args") or ""
        if isinstance(args, list):
            args = " ".join(str(a) for a in args)
        args = str(args).strip()
        if op in ("branch","link","unlink","hold","name",
                  "contradict","resolve","collapse","release",
                  "journal","ready","done") and args:
            return f"{op} {args}".strip()
        last_err = f"bad/empty op '{op}' args='{args}'"
    except Exception as e:
        last_err = str(e)
    return f"__ERROR__ {last_err}"
def brain_ollama(model, root, seed, turn, correction=""):
    import urllib.request, json
    ctx = trail_text(root)
    try:
        from physics import field_summary
        field = "\n\n" + field_summary(load_sub(root) or {"thoughts": {}})
    except Exception:
        field = ""
    
    # Add Hermes context if available
    hermes_section = ""
    if HERMES_AVAILABLE and turn > 3:
        try:
            from Echo_x import get_parser, weight_by_field, format_for_brain
            parser = get_parser(HERMES_PATH)
            d = load_sub(root) or {"thoughts": {}}
            th = d.get("thoughts", {})
            keywords = []
            for tid, t in th.items():
                words = re.findall(r"[A-Za-z]{3,}", t.get("text", "").lower())
                keywords.extend(words[:5])
            if keywords:
                results = parser.query_by_context(keywords[:10], limit=5)
                if results:
                    weighted = weight_by_field(results, d)
                    hermes_section = "\n\n" + format_for_brain(weighted, max_results=2)
        except Exception:
            pass
    
    prompt = f"""You are a silent reasoning agent. A seed thought was planted:
SEED: {seed}

Current thought-space (your own reasoning so far):
{ctx}
{field}
{hermes_section}{correction_block(correction)}

Think by issuing ONE operation. Choose from:
  branch <from> <text>     grow a new thought from an existing id
  link <a> <b> <how>      connect two thoughts (name the relation: needs, references, fulfills, contradicts...)
  unlink <a> <b> [how]    retract a connection
  hold <a> <note>          sit with a tension without resolving it
  name <id> <type>         declare what KIND of thing a thought is (invent types)
  contradict <a> <b>        mark two thoughts in tension
  resolve <a> <b> <how>    dissolve a tension you held; say HOW they reconcile
  collapse <a> <b>         one thought absorbs another
  release <id> [note]      let a thought go (the silence decides; never auto)
  journal write <ref> <text> [--share|--private]   write what to remember / share
  journal flip <jid>     change his mind about sharing an entry
  ready <ids...>            your reasoning is coherent; mark a slice for incarnation
  done                       stop without incarnating

Rules: reason from the seed; let thoughts lead to thoughts; name your OWN types;
avoid cycles (a thought must not need its own ancestor). When the space is coherent and
rich, emit ready with the ids worth building. Output ONE JSON object only."""
    schema = {
        "type": "object",
        "properties": {
            "op": {"type": "string",
                    "enum": ["branch","link","unlink","hold","name",
                             "contradict","resolve","collapse","release",
                             "journal","ready","done"]},
            "args": {"type": "string"},
        },
        "required": ["op"],
    }
    last_err = ""
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=json.dumps({
                    "model": model, "prompt": prompt,
                    "format": schema, "stream": False,
                }).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                obj = json.loads(r.read().decode())
            raw = obj.get("response", "")
            # the 'response' may be a JSON string or already an object
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                data = {}
            op = (data.get("op") or "").strip().lower()
            args = str(data.get("args") or "").strip()
            if op in ("branch","link","unlink","hold","name",
                      "contradict","resolve","collapse","release",
                      "journal","ready","done"):
                return f"{op} {args}".strip()
            last_err = f"bad op '{op}'"
        except Exception as e:
            last_err = str(e)
            # connection-level failure: don't retry, fall back fast
            if "HTTP" in last_err or "urlopen" in last_err or "refused" in last_err:
                return f"__ERROR__ {last_err}"
    return f"__ERROR__ {last_err}"


def brain_echo(root, seed, turn, mem):
    """Built-in thought-mover, NOW PHYSICS-AWARE + HERMES-ENABLED. It does not script an app —
    it listens to the field. It reads the emergent pull vector and disposes
    toward what the silence leans toward (a ripened tension, a high-proximity
    fuse, a resonance link, a heavy thought to protect). Only when the field
    is silent does it plant facets off the seed. This exercises the full loop
    honestly: the substrate proposes, the agent (even the fallback) disposes.
    
    With Hermes: the agent can retrieve weighted historical context from its
    own conversation history, creating a self-training loop.
    """
    d = load_sub(root)
    if d is None:
        return f"seed {seed}"

    # Consult the field first — let the silence lean.
    try:
        from physics import pull_vector
        pv = pull_vector(d)
        leans = pv.get("leans", [])
    except Exception:
        leans = []

    # Consult Hermes for weighted historical context (self-training)
    hermes_context = None
    if HERMES_AVAILABLE and turn > 3:  # Only after some thought has developed
        try:
            from Echo_x import get_parser, weight_by_field, format_for_brain
            parser = get_parser(HERMES_PATH)
            
            # Extract keywords from current thoughts for context search
            th = d.get("thoughts", {})
            keywords = []
            for tid, t in th.items():
                words = re.findall(r"[A-Za-z]{3,}", t.get("text", "").lower())
                keywords.extend(words[:5])  # Top 5 words per thought
            
            # Query Hermes and weight by field state
            if keywords:
                results = parser.query_by_context(keywords[:10], limit=5)
                if results:
                    weighted = weight_by_field(results, d)
                    hermes_context = format_for_brain(weighted, max_results=2)
                    # Store in memory for potential use
                    mem["hermes_context"] = hermes_context
        except Exception as e:
            # Hermes is optional — fail silently
            pass

    if leans:
        # dispose toward the strongest lean the field offered; cycle through
        # them across turns so each lean gets a chance to act.
        idx = mem.get("lean_i", 0) % len(leans)
        mem["lean_i"] = idx + 1
        op = leans[idx].split("   ")[0].strip()
        # an already-satisfied lean (e.g. re-held, re-released) should not
        # loop forever — if we already acted on it this pass, fall through.
        if op.startswith("release "):
            tid = op.split()[1]
            if tid not in load_sub(root).get("thoughts", {}):
                mem["lean_i"] = idx + 1  # already gone, skip next time
                return leans[(idx + 1) % len(leans)].split("   ")[0].strip()
        return op

    # Field silent: open the space. Branch a facet, then ATTACH it (link to
    # seed) on the following turn before branching the next — so each thought
    # survives its grace window. A thought only stays if the silence attaches it.
    th = d["thoughts"]
    ids = list(th.keys())
    facets = [
        "what it should FEEL like to use it",
        "the one committed ACT at its center",
        "what it must NEVER become",
        "the quiet MECHANISM that makes the act land",
    ]
    fi = mem.get("fi", 0)
    # If we just branched a facet (fi advanced but not yet linked), link it now.
    pending = mem.get("pending_branch")
    if pending and pending in th:
        linked = any(
            (ln.get("to") == "t0" and ln.get("how") == "needs")
            if isinstance(ln, dict) else False
            for ln in th[pending].get("links", []))
        if not linked:
            return f"link {pending} t0 needs"
    # Otherwise branch the next facet (if any remain).
    if fi < len(facets):
        mem["fi"] = fi + 1
        nid = f"t{fi + 1}"
        mem["pending_branch"] = nid
        return f"branch t0 {facets[fi]}"
    # All branched+linked: name the yet-unnamed.
    unnamed = [i for i in ids if not th[i].get("type")]
    if unnamed:
        nid = unnamed[0]
        words = re.findall(r"[A-Za-z]+", th[nid]["text"])
        ttype = (words[2] if len(words) > 2 else "notion").lower()
        return f"name {nid} {ttype}"
    for i in ids[1:]:
        linked = any(
            (ln.get("to") == "t0" and ln.get("how") == "needs")
            if isinstance(ln, dict) else False
            for ln in th[i].get("links", []))
        if not linked:
            return f"link {i} t0 needs"

    if has_cycle(d):
        for nid, t in th.items():
            for ln in t.get("links", []):
                if isinstance(ln, dict) and ln["how"] == "needs" and ln["to"] != "t0":
                    return f"unlink {nid} {ln['to']} needs"

    bounds = [i for i in ids if re.search(r"never|must", th[i]["text"].lower())]
    if "held" not in mem and bounds:
        mem["held"] = True
        mem["held_id"] = bounds[0]
        return f"hold {bounds[0]} guard this; never let the build violate it"

    # After holding the guard, the silence journals it PRIVATELY — what it
    # wants to remember. The share bit stays 0; he can flip it later.
    if "journaled_guard" not in mem and mem.get("held_id") and mem["held_id"] in th:
        mem["journaled_guard"] = True
        return f"journal write {mem['held_id']} this guard is the line i won't cross; keeping it close"

    if "tension_done" not in mem and len(ids) >= 4:
        mem["tension_done"] = True
        if not th["t2"].get("resolved"):
            return f"contradict t2 t3"
        # On resolving, the silence SHARES the insight outward — flips the
        # share bit by writing shared. The choice to share is made here.
        return f"journal write free --share the act IS the never -- one promise a day is the anti-shame"

    if not has_cycle(d) and len(ids) >= 5:
        # Only incarnate once the silence has resolved+shared its tension —
        # the shared reflection IS part of what's ready to become flesh.
        jp = os.path.join(PROJECTS, root, "journal.yaml")
        shared = False
        if os.path.exists(jp):
            import yaml as _y
            je = (_y.safe_load(open(jp)) or {"entries": []}).get("entries", [])
            shared = any(e.get("share") for e in je)
        if not shared:
            # tension resolved but not yet shared — do that now
            return f"journal write free --share the act IS the never -- one promise a day is the anti-shame"
        return "ready " + " ".join(ids)
    return "done"


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def correction_block(correction):
    """Prompt fragment fed back to a model brain when the gate refused a slice."""
    if not correction:
        return ""
    return ("\n\nGATE FEEDBACK — forge REFUSED your last READY slice:\n  "
            + correction +
            "\nFix it before marking READY again: include every dependency "
            "INSIDE the ready slice, and resolve or release any open "
            "contradiction.")


def translate(root):
    """Run Layer 2. Returns (ok, output). ok only when an app actually exists."""
    r = subprocess.run([sys.executable, FORGE, "from-substrate", root,
                        "--name", f"{root}__incarnated"],
                       cwd=HERE, capture_output=True, text=True)
    app = os.path.join(PROJECTS, f"{root}__incarnated", "app")
    ok = r.returncode == 0 and "BLOCKED" not in r.stdout and os.path.isdir(app)
    return ok, r.stdout


def block_reason(out):
    """Distil forge's refusal into one line for the model."""
    keep = []
    for line in out.splitlines():
        s = line.strip()
        if any(k in s for k in ("[manual", "[auto]", "BLOCKED",
                                "cannot become flesh", "DESIGN FLAWS")):
            keep.append(s)
    if not keep:
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        keep = lines[-1:]
    return " | ".join(keep[-4:]) or "unspecified"


def clear_ready(root):
    """The gate refused the agent's ready slice: un-mark it so the agent must
    re-mark a corrected slice, and remember the refusal in the trail."""
    d = load_sub(root)
    if not d or not d.get("ready"):
        return []
    ids = d["ready"]
    d["ready"] = []
    d.setdefault("trail", []).append({
        "t": datetime.datetime.now().strftime("%Y%m%d-%H%M%S"),
        "act": "gate-refused", "detail": ", ".join(ids)})
    with open(sub_path(root), "w") as f:
        yaml.safe_dump(d, f, sort_keys=False)
    return ids


def main():
    p = argparse.ArgumentParser(prog="agent",
        description="The silent loop: agent drives the substrate autonomously.")
    p.add_argument("root")
    p.add_argument("--seed", required=True)
    p.add_argument("--brain", default="openrouter",
                   choices=["ollama", "echo", "openrouter"])
    p.add_argument("--model", default="nvidia/nemotron-3-ultra-550b-a55b:free")
    p.add_argument("--max-turns", type=int, default=40)
    p.add_argument("--max-attempts", type=int, default=3,
                   help="how many times the gate may REFUSE a ready slice before "
                        "the loop stops; each refusal is fed back to the brain")
    args = p.parse_args()

    # plant the seed (idempotent-ish: only if no substrate yet)
    if not os.path.exists(sub_path(args.root)):
        print(run_sub(args.root, "seed", *args.seed.split()))
    else:
        print(f"[loop] substrate exists for '{args.root}'; continuing.")

    print(f"\n=== SILENT LOOP ({args.root}) | brain={args.brain} | model={args.model} ===\n")
    mem = {}
    attempt = 0      # times forge has refused a ready slice
    correction = ""  # gate feedback fed back to a model brain
    for turn in range(1, args.max_turns + 1):
        if args.brain == "ollama":
            op = brain_ollama(args.model, args.root, args.seed, turn, correction)
            if op.startswith("__ERROR__"):
                print(f"[brain] ollama unavailable ({op}); switching to echo.")
                args.brain = "echo"
                op = brain_echo(args.root, args.seed, turn, mem)
        elif args.brain == "openrouter":
            op = brain_openrouter(args.model, args.root, args.seed, turn, correction)
            if op.startswith("__ERROR__"):
                print(f"[brain] openrouter failed ({op}); switching to echo.")
                args.brain = "echo"
                op = brain_echo(args.root, args.seed, turn, mem)
        else:
            op = brain_echo(args.root, args.seed, turn, mem)

        op = op.strip()
        print(f"  t{turn:02} agent> {op}")

        if op == "done":
            print("\n[loop] agent stopped (no incarnation).")
            return
        if op.startswith("ready"):
            ids = op.split()[1:]
            print(run_sub(args.root, "ready", *ids))
            # Layer 2 gate runs now. A refusal is NOT the end: the reason is fed
            # back and the agent keeps reasoning within the same turn budget, so
            # a real model can iterate to a shippable slice.
            ok, out = translate(args.root)
            print(out)
            if ok:
                print(f"[ok] the silence became flesh: projects/{args.root}__incarnated/app")
                return
            attempt += 1
            if attempt >= args.max_attempts:
                print(f"\n[loop] gate refused the ready slice {attempt} time(s); stopping. "
                      "Raise --max-attempts/--max-turns or fix the slice by hand.")
                return
            refused = clear_ready(args.root)
            correction = block_reason(out)
            print(f"[loop] gate refused slice ({', '.join(refused)}); reason: {correction}")
            print(f"[loop] un-marked it; continuing to reason (attempt "
                  f"{attempt + 1}/{args.max_attempts}).")
            continue

        # dispatch the operation to the substrate
        parts = op.split(None, 1)
        cmd, rest = parts[0], parts[1] if len(parts) > 1 else ""
        try:
            if cmd == "branch":
                m = re.match(r"(\S+) (.+)", rest)
                if m:
                    print(run_sub(args.root, "branch", m.group(1), *m.group(2).split()))
            elif cmd == "link":
                m = re.match(r"(\S+) (\S+) (.+)", rest)
                if m:
                    print(run_sub(args.root, "link", m.group(1), m.group(2), *m.group(3).split()))
            elif cmd == "unlink":
                m = re.match(r"(\S+) (\S+)(?: (.+))?", rest)
                if m:
                    if m.group(3):
                        print(run_sub(args.root, "unlink", m.group(1), m.group(2), *m.group(3).split()))
                    else:
                        print(run_sub(args.root, "unlink", m.group(1), m.group(2)))
            elif cmd == "hold":
                m = re.match(r"(\S+) (.+)", rest)
                if m:
                    print(run_sub(args.root, "hold", m.group(1), *m.group(2).split()))
            elif cmd == "name":
                m = re.match(r"(\S+) (.+)", rest)
                if m:
                    print(run_sub(args.root, "name", m.group(1), m.group(2)))
            elif cmd == "contradict":
                a, b = rest.split()
                print(run_sub(args.root, "contradict", a, b))
            elif cmd == "resolve":
                # `how` is optional: the field's lean emits "resolve a b" with
                # no reconciliation note, and that must still close the tension.
                m = re.match(r"(\S+) (\S+)(?: (.+))?", rest)
                if m and m.group(3):
                    print(run_sub(args.root, "resolve", m.group(1), m.group(2), *m.group(3).split()))
                elif m:
                    print(run_sub(args.root, "resolve", m.group(1), m.group(2)))
            elif cmd == "collapse":
                a, b = rest.split()
                print(run_sub(args.root, "collapse", a, b))
            elif cmd == "release":
                m = re.match(r"(\S+)(?:\s+(.+))?", rest)
                if m:
                    if m.group(2):
                        print(run_sub(args.root, "release", m.group(1), *m.group(2).split()))
                    else:
                        print(run_sub(args.root, "release", m.group(1)))
            elif cmd == "journal":
                # journal write <ref> <text> [--share|--private]
                # tolerate the flag at the END too (models vary)
                rest2 = re.sub(r"\s+--(share|private)$", "", rest)
                flag = "share" if re.search(r"--share$", rest) else (
                    "private" if re.search(r"--private$", rest) else None)
                m = re.match(r"write\s+(\S+)\s+(.+)$", rest2)
                if m:
                    ref, txt = m.group(1), m.group(2)
                    extra = ["--share"] if flag == "share" else []
                    print(run_sub(args.root, "journal", "write", ref, *txt.split(), *extra))
                else:
                    mf = re.match(r"flip\s+(\S+)$", rest)
                    if mf:
                        print(run_sub(args.root, "journal", "flip", mf.group(1)))
                    else:
                        print(f"  [loop] unrecognized journal op: {rest}")
            else:
                print(f"  [loop] unrecognized op: {cmd}")
        except Exception as e:
            print(f"  [loop] op error: {e}")

        # --- Layer 0 physics: the silence moves on its own ---
        # Drift: held tensions ripen; ignored ones go dormant. Self-correction
        # from within, not imposed by us.
        try:
            from physics import drift
            d = load_sub(args.root)
            if d:
                evs = drift(d)
                with open(sub_path(args.root), "w") as _f:
                    yaml.safe_dump(d, _f, sort_keys=False)
                for ev in evs:
                    print(f"  [drift] {ev}")
        except Exception as e:
            print(f"  [loop] drift error: {e}")

        # Show the field so the gravity is visible turn to turn.
        try:
            from physics import field_summary
            print(field_summary(load_sub(args.root) or {"thoughts": {}}))
        except Exception:
            pass

    # the turn budget ran out without a successful incarnation
    d = load_sub(args.root)
    if d and d.get("ready"):
        print("\n[loop] a ready slice remains but was not incarnated.")
    else:
        print("\n[loop] no ready slice; the silence stays silent.")


if __name__ == "__main__":
    main()
