#!/usr/bin/env python3
"""
forge.py - Recursive IDEA -> WORD -> FLESH harness
====================================================
mbp.py is the SINGLE-LAYER engine: given a layer, it runs IDEA -> WORD ->
FLESH and verifies clean. This harness orchestrates layers recursively, so the
three-incarnation process runs at EVERY scale and each layer self-corrects.

THE LAYERED MODEL
------------------
A build is a tree of layers.
  Layer 0 (root): the app idea.
    Layer 1: one child per major module (architected from layer 0's WORD).
      Layer 2: one child per component inside a module.
        ... leaves FLESH into real code.

Each layer independently obeys:
  IDEA  - what this layer is trying to become (inherited from parent, or the
           root concept at layer 0).
  WORD  - the reasoning map for THIS layer only. Small, tight, verifiable.
  FLESH - a leaf layer emits code; a non-leaf layer emits SUB-LAYER specs
           (children). No layer may FLESH until its WORD verifies clean.

SELF-CORRECTION (upward remap)
--------------------------------
If a deeper layer discovers a contradiction with its parent (e.g. a component
needs a capability the parent's map didn't account for), it records a flaw
against the parent node. The parent re-runs WORD (remap), which may spawn or
reshape its children. Corrections ripple UP, never silently contradict the map.

STOPPING CONDITION (no infinite recursion)
-----------------------------------------
A layer is a LEAF when any of:
  - depth >= max_depth, or
  - the agent marks it leaf, or
  - node count <= leaf_threshold.
Non-leaf FLESH emits children; leaf FLESH emits code via mbp.

AGENT
------
WORD reasoning per layer is produced by an agent. If Ollama is reachable it is
used; otherwise a built-in deterministic planner produces a valid map so the
recursion + remap logic is fully exercisable without a model.

Storage: local files. The forge tree lives at projects/<root>/forge_tree.yaml,
and each layer is a real mbp project at projects/<root>/layers/<path>/.

Usage:
  python3 forge.py build <root> --idea "..." [--max-depth 3] [--agent ollama|planner]
  python3 forge.py status <root>
  python3 forge.py show <root> [--tree]
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
import shutil
import yaml

# Sandbox integration
SANDBOX_AVAILABLE = True
try:
    from sandbox import Sandbox, format_execution_result, execution_to_physics_weight
except ImportError:
    SANDBOX_AVAILABLE = False

HERE = os.path.dirname(os.path.abspath(__file__))
MBP = os.path.join(HERE, "mbp.py")
WORKSPACE = os.environ.get("MBP_WORKSPACE") or HERE   # see substrate.py
PROJECTS = os.path.join(WORKSPACE, "projects")


def now():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def tree_path(root):
    return os.path.join(PROJECTS, root, "forge_tree.yaml")


def layer_dir(root, path):
    # path is like "0", "0.1", "0.1.2"
    return os.path.join(PROJECTS, root, "layers", path.replace(".", "_"))


# ---------------------------------------------------------------------------
# Agent: produce a WORD map for one layer
# ---------------------------------------------------------------------------

def call_ollama(model, prompt, timeout=120):
    import urllib.request, json
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({"model": model, "prompt": prompt,
                             "format": "yaml", "stream": False}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("response", "")
    except Exception as e:
        return f"__ERROR__ {e}"


def planner_map(idea, layer_path, depth, parent_map=None):
    """Deterministic fallback planner: turns an idea into a small valid map.

    At layer 0 it emits architecture-level nodes. Deeper layers split a single
    inherited node into its sub-components. This is intentionally simple -- its
    job is to exercise the recursion/remap, not to be smart.
    """
    nodes = {}
    edges = []
    flaws = []
    if depth == 0:
        nodes["app"] = mk("concept", idea, [])
        nodes["ui"] = mk("screen", "User interface layer", ["app"])
        nodes["core"] = mk("service", "Core logic / business rules", ["app"])
        nodes["data"] = mk("package", "Data + persistence", ["core"])
        nodes["config"] = mk("config", "App configuration", ["app"])
        edges += [
            e("ui", "app", "fulfills"),
            e("core", "app", "fulfills"),
            e("data", "core", "depends-on"),
            e("config", "app", "depends-on"),
        ]
        flaws.append({"node": "data", "desc":
                      "persistence backend not chosen (sqlcipher vs room)",
                      "status": "open"})
        # children = major modules to spawn as sub-layers
        children = [
            f"UI layer: {idea} - screens and navigation",
            f"Core logic: {idea} - business rules and state",
            f"Data layer: {idea} - persistence and sync",
        ]
    else:
        # deeper: split the inherited node into sub-parts
        base = idea
        parts = re.split(r"[/,]| and | with ", base)
        if len(parts) < 2:
            parts = [base + " - main", base + " - support"]
        parent_node = "parent"
        nodes[parent_node] = mk("feature", base, [])
        for i, p in enumerate(parts[:4]):
            pid = f"part{i+1}"
            nodes[pid] = mk("component", p.strip(), [parent_node])
            edges.append(e(pid, parent_node, "depends-on"))
        children = []
    return {"nodes": nodes, "edges": edges, "flaws": flaws,
            "children": children}


def mk(ntype, summary, deps):
    return {"type": ntype, "summary": summary, "deps": deps,
            "package": "", "spec": "", "status": "proposed", "note": ""}


def e(fr, to, rel):
    return {"from": fr, "to": to, "relation": rel}


def agent_word(root, layer_path, depth, idea, parent_map, agent, model):
    if agent == "ollama":
        prompt = build_agent_prompt(idea, layer_path, depth, parent_map)
        raw = call_ollama(model, prompt)
        parsed = parse_agent_yaml(raw)
        if parsed and "nodes" in parsed:
            return parsed
        print(f"  [warn] ollama failed/unavailable; using planner for {layer_path}")
    return planner_map(idea, layer_path, depth, parent_map)


def build_agent_prompt(idea, layer_path, depth, parent_map):
    ctx = ""
    if parent_map:
        ctx = "PARENT MAP (you must not contradict this):\n" + yaml.safe_dump(
            parent_map, sort_keys=False) + "\n"
    return f"""You are the WORD stage of a layered mobile-app build.
{ctx}
This is LAYER {layer_path} at DEPTH {depth}.
LAYER IDEA: {idea}

Produce a reasoning map for THIS layer only. Small and verifiable.
Return YAML with:
  nodes: {{ id: {{type, summary, deps:[ids], package, spec}} }}
  edges: [ {{from, to, relation}} ]   # relation in depends-on|fulfills|blocks
  flaws: [ {{node, desc}} ]           # design gaps you notice
  children: [ "idea string for each sub-layer to spawn" ]  # empty if leaf

Node types: concept, feature, package, dependency, screen, service,
data-model, config, risk, component.
Only emit 'children' if this layer should be split further.
"""


def parse_agent_yaml(raw):
    try:
        m = re.search(r"nodes:\s*(\n\s+.*?)(?=\n\w|\Z)", raw, re.S)
        text = raw if "nodes:" in raw else ""
        return yaml.safe_load(text) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Layer execution: IDEA -> WORD -> FLESH, with verify gate
# ---------------------------------------------------------------------------

def run_layer(root, layer_path, depth, idea, parent_map, tree, agent, model,
              max_depth, leaf_threshold):
    ldir = layer_dir(root, layer_path)
    name = f"{root}__{layer_path.replace('.', '_')}"

    # IDEA
    print(f"\n{'  '*depth}[LAYER {layer_path}] IDEA: {idea[:70]}")
    subprocess.run([sys.executable, MBP, "idea", name,
                    "--text", idea], cwd=HERE, capture_output=True)

    # WORD (agent reasons the map)
    print(f"{'  '*depth}[LAYER {layer_path}] WORD: reasoning map...")
    wmap = agent_word(root, layer_path, depth, idea, parent_map, agent, model)

    # resolve flaws automatically in planner mode to show the self-correct loop;
    # in agent mode leave them open so the human/agent closes via mbp word.
    flaws_resolved = (agent == "planner" and bool(wmap.get("flaws")))
    if flaws_resolved:
        for fl in wmap["flaws"]:
            print(f"{'  '*depth}  [self-correct] flaw resolved: {fl.get('desc')}")
    write_layer_map(name, wmap, flaws_resolved=flaws_resolved)

    # FLESH gate: must verify clean. If blocked by AUTO-flaws (e.g. a package
    # node with no package name), self-correct by filling the gap, then retry.
    # This is the layer self-correcting before it spawns children.
    print(f"{'  '*depth}[LAYER {layer_path}] FLESH: incarnating...")
    for attempt in range(2):
        r = subprocess.run([sys.executable, MBP, "flesh", name,
                            "--platform", "generic"],
                           cwd=HERE, capture_output=True, text=True)
        if "cannot become flesh" in r.stdout or "DESIGN FLAWS" in r.stdout:
            auto = re.findall(r"\[auto\] (.*)", r.stdout)
            fixed = try_self_fix(name, auto)
            if fixed:
                print(f"{'  '*depth}  [self-correct] {fixed}")
                continue  # retry flesh
            print(f"{'  '*depth}  [BLOCKED] flaws open; layer cannot flesh yet.")
            print(f"{'  '*depth}  {r.stdout.strip().splitlines()[-1]}")
            return None
        break  # clean

    # mbp writes flesh to projects/<name>/app; move it under the layer tree
    # so the forge tree is coherent on disk (layers/<path>/app).
    src_app = os.path.join(PROJECTS, name, "app")
    if os.path.isdir(src_app):
        dst_app = os.path.join(layer_dir(root, layer_path), "app")
        if os.path.exists(dst_app):
            shutil.rmtree(dst_app)
        shutil.move(src_app, dst_app)


    # decide leaf vs non-leaf
    n_nodes = len(wmap.get("nodes", {}))
    children = wmap.get("children", [])
    is_leaf = (depth >= max_depth) or (not children) or \
               (n_nodes <= leaf_threshold and not children)

    node = {
        "path": layer_path,
        "idea": idea,
        "depth": depth,
        "is_leaf": is_leaf,
        "n_nodes": n_nodes,
        "children": [],
    }
    tree["layers"][layer_path] = node

    if is_leaf:
        print(f"{'  '*depth}  [LEAF] code incarnated at layers/{layer_path.replace('.','_')}/app")
    else:
        print(f"{'  '*depth}  [NODE] spawning {len(children)} sub-layers")
        for i, child_idea in enumerate(children):
            child_path = f"{layer_path}.{i+1}" if layer_path != "0" else str(i+1)
            child = run_layer(root, child_path, depth + 1, child_idea,
                              wmap, tree, agent, model, max_depth,
                              leaf_threshold)
            if child:
                node["children"].append(child_path)
    return node


def try_self_fix(name, auto_flaws):
    """Attempt to resolve auto-flaws in the map without human input.
    Returns a description string if a fix was applied, else None.
    """
    mp = os.path.join(PROJECTS, name, "map.yaml")
    if not os.path.exists(mp):
        return None
    with open(mp) as f:
        data = yaml.safe_load(f) or {}
    nodes = data.setdefault("nodes", {})
    fixed = []
    for fl in auto_flaws:
        m = re.search(r"package node '(\w+)' has no package name set", fl)
        if m:
            nid = m.group(1)
            if nid in nodes and not nodes[nid].get("package"):
                nodes[nid]["package"] = f"local.{nid}"
                fixed.append(f"set default package on '{nid}'")
                continue
        m = re.search(r"dangling dependency: (\w+) -> (\w+)", fl)
        if m:
            src, dst = m.group(1), m.group(2)
            if src in nodes:
                nodes[src]["deps"] = [d for d in nodes[src].get("deps", [])
                                      if d != dst]
                fixed.append(f"removed dangling dep {src}->{dst}")
    if fixed:
        with open(mp, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        return "; ".join(fixed)
    return None


def write_layer_map(name, wmap, flaws_resolved=False):
    """Write the agent's map into the mbp project's map.yaml directly."""
    pdir = os.path.join(PROJECTS, name)
    os.makedirs(pdir, exist_ok=True)
    doc = {
        "project": name,
        "created": now(),
        "incarnation": "WORD",
        "nodes": wmap.get("nodes", {}),
        "edges": wmap.get("edges", []),
        "flaws": [{"node": f.get("node", ""), "desc": f.get("desc", ""),
                   "status": "resolved" if flaws_resolved else "open"}
                  for f in wmap.get("flaws", [])],
    }
    with open(os.path.join(pdir, "map.yaml"), "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_build(root, idea, max_depth, agent, model, leaf_threshold=2):
    os.makedirs(PROJECTS, exist_ok=True)
    tree = {"root": root, "idea": idea, "created": now(),
            "max_depth": max_depth, "agent": agent, "layers": {}}
    print(f"=== FORGE: recursive IDEA->WORD->FLESH for '{root}' ===")
    print(f"    max_depth={max_depth}  agent={agent}  leaf_threshold={leaf_threshold}")
    try:
        run_layer(root, "0", 0, idea, None, tree, agent, model,
                  max_depth, leaf_threshold)
    finally:
        os.makedirs(os.path.dirname(tree_path(root)), exist_ok=True)
        with open(tree_path(root), "w") as f:
            yaml.safe_dump(tree, f, sort_keys=False)
    leaves = [p for p, n in tree["layers"].items() if n["is_leaf"]]
    print(f"\n=== FORGE COMPLETE ===")
    print(f"    layers: {len(tree['layers'])}   leaves (code): {len(leaves)}")
    print(f"    tree: {tree_path(root)}")


def cmd_status(root):
    tp = tree_path(root)
    if not os.path.exists(tp):
        print(f"[err] no forge tree for '{root}'.")
        sys.exit(1)
    tree = yaml.safe_load(open(tp))
    print(f"FORGE STATUS: {root}")
    print(f"  idea: {tree['idea']}")
    print(f"  layers: {len(tree['layers'])}")
    for p, n in sorted(tree["layers"].items()):
        kind = "LEAF" if n["is_leaf"] else "NODE"
        print(f"    {p:8} [{kind}] depth {n['depth']}  nodes={n['n_nodes']}  {n['idea'][:50]}")


def cmd_show(root):
    tp = tree_path(root)
    if not os.path.exists(tp):
        print(f"[err] no forge tree for '{root}'.")
        sys.exit(1)
    tree = yaml.safe_load(open(tp))

    def walk(path, depth):
        n = tree["layers"].get(path)
        if not n:
            return
        print(f"{'  '*depth}- {path} [{'LEAF' if n['is_leaf'] else 'NODE'}] {n['idea'][:55]}")
        for c in n["children"]:
            walk(c, depth + 1)
    walk("0", 0)


def write_open_threads(sub, app_dir, name):
    """Write OPEN_THREADS.md next to the artifact: what became real, what was
    consciously let go, what is held open, what tensions were resolved or set
    aside. This is the idea's honest accounting of itself."""
    th = sub.get("thoughts", {})
    ready = sub.get("ready", [])
    released = sub.get("released", [])
    seed = sub.get("seed")

    def txt(i):
        return th.get(i, {}).get("text", "")

    idea = txt(seed) if seed else ""
    held = [(i, t) for i, t in th.items() if t.get("holds")]
    resolved = [(i, r) for i, t in th.items() for r in t.get("resolved", [])]
    dormant = [i for i, t in th.items() if t.get("dormant")]

    L = [f"# Open threads — {name}", "",
         f"**The idea:** {idea}", "",
         f"## Incarnated — became real ({len(ready)})"]
    L += [f"- `{i}` {txt(i)}" for i in ready] or ["- (none)"]

    L += ["", f"## Let go — conscious deferrals ({len(released)})"]
    L += [f"- `{r['id']}` {r.get('text', '')[:80]} — {r.get('why', '')}"
          for r in released] or ["- (none) — nothing was consciously dropped"]

    L += ["", f"## Held open — flagged, unresolved ({len(held)})"]
    if held:
        for i, t in held:
            for h in t.get("holds", []):
                L.append(f"- `{i}` {txt(i)} — open: {h}")
    else:
        L.append("- (none) — no unresolved questions left hanging")

    L += ["", "## Tensions resolved"]
    L += [f"- `{i}` <> `{r['with']}` — {r['how']} (how they reconcile)"
          for i, r in resolved] or ["- (none)"]

    L += ["", "## Set aside (dormant, honestly not solved)"]
    L.append("- " + (", ".join(f"`{i}`" for i in dormant) if dormant else "(none)"))

    L += ["", "---",
          f"coverage: {len(ready)} incarnated · {len(released)} deferred · "
          f"{len(held)} held open · {len(resolved)} resolved · "
          f"{len(dormant)} set aside",
          "nothing was silently dropped."]
    md = "\n".join(L) + "\n"

    os.makedirs(app_dir, exist_ok=True)
    with open(os.path.join(app_dir, "OPEN_THREADS.md"), "w") as f:
        f.write(md)
    return md


def cmd_from_substrate(root, name):
    """LAYER 2 TRANSLATOR. Read the agent's ready slice from the substrate
    and turn it into WORD->FLESH. We do NOT reshape the agent's thoughts:
    its own types and links become the map. We only enforce the gate.
    
    Now with sandbox execution: after flesh, execute the code and feed
    results back to physics for self-training.
    """
    sp = os.path.join(PROJECTS, root, "substrate.yaml")
    if not os.path.exists(sp):
        print(f"[err] no substrate for '{root}'. Plant a seed first.")
        sys.exit(1)
    sub = yaml.safe_load(open(sp))
    ready = sub.get("ready", [])
    if not ready:
        print("[err] agent hasn't marked a ready slice. (substrate ready <ids>)")
        sys.exit(1)
    thoughts = sub["thoughts"]

    # AN IDEA MAY BE INCOMPLETE. IT MAY NOT BE SILENTLY INCOMPLETE.
    # Every thought the agent grew must be accounted for: incarnated (ready),
    # held open (a flagged question), or consciously released. We do not judge
    # completeness and we do not choose the path -- we only refuse to let a
    # thread vanish without a decision. (The agent's own steps stay its own.)
    try:
        from substrate import unaccounted
        unacct = unaccounted(sub)
    except Exception:
        unacct = []
    if unacct:
        print("THREADS LEFT UNACCOUNTED -- an idea may be incomplete, but not silently so:")
        for tid in unacct:
            print(f"  [open] {tid}: {thoughts[tid].get('text', '')[:70]}")
        print("[BLOCKED] for each: include it (ready), `hold` it open, or "
              "`release` it -- then the idea can become real.")
        return

    # OPEN CONTRADICTIONS ARE FIRST-CLASS: refuse to incarnate a ready slice
    # while it holds an unresolved, non-dormant tension. A dormant tension was
    # set aside honestly and does NOT block.
    try:
        from physics import open_tensions
        blocking = [t for t in open_tensions(sub)
                    if t["a"] in ready and t["b"] in ready]
    except Exception:
        blocking = []
    if blocking:
        print("DESIGN FLAWS FOUND -- the word cannot become flesh yet:")
        for t in blocking:
            print(f"  [manual:tension] {t['a']} <> {t['b']} "
                  f"(ripen={t['ripen']}) -- unresolved contradiction")
        print("[BLOCKED] the slice holds an open contradiction. "
              "Resolve it (substrate resolve) or let it go dormant first.")
        return

    # BOUNDARY ENFORCED HERE: forge (Layer 2) may ONLY read shared journal
    # entries. Private ones (share=0) are the silence's own and never surface
    # into flesh. The choice of whether to share stays with the silence.
    jp = os.path.join(PROJECTS, root, "journal.yaml")
    shared_notes = []
    if os.path.exists(jp):
        j = yaml.safe_load(open(jp)) or {"entries": []}
        shared_notes = [e["text"] for e in j.get("entries", []) if e.get("share")]
    if shared_notes:
        print(f"    [outward notes the silence chose to share: {len(shared_notes)}]")
        for n in shared_notes:
            print(f"      - {n}")
    # build an mbp-layer map straight from the agent's own structure
    nodes = {}
    edges = []
    for tid in ready:
        t = thoughts[tid]
        nodes[tid] = {
            "type": t.get("type") or "thought",
            "summary": t["text"],
            "deps": [],
            "package": "",
            "spec": "",
            "status": "proposed",
            "note": "held: " + "; ".join(t.get("holds", [])) if t.get("holds") else "",
        }
        for ln in t.get("links", []):
            if isinstance(ln, dict):
                rel = ln["how"]
                edges.append({"from": tid, "to": ln["to"], "relation": rel})
                # only true dependencies create build-order edges
                if rel in ("needs", "depends-on", "branch", "fulfills"):
                    nodes[tid]["deps"].append(ln["to"])
            else:
                edges.append({"from": tid, "to": ln, "relation": "branch"})
                nodes[tid]["deps"].append(ln)
        for c in t.get("contradicts", []):
            if c in ready:
                edges.append({"from": tid, "to": c, "relation": "contradicts"})
    wmap = {"nodes": nodes, "edges": edges, "flaws": []}
    print(f"=== TRANSLATE: substrate slice -> WORD/FLESH ({name}) ===")
    print(f"    {len(nodes)} thoughts from the agent's own reasoning")
    write_layer_map(name, wmap, flaws_resolved=True)
    r = subprocess.run([sys.executable, MBP, "flesh", name,
                        "--platform", "python"],
                       cwd=HERE, capture_output=True, text=True)
    print(r.stdout)
    app_path = os.path.join(PROJECTS, name, "app")
    if ("cannot become flesh" in r.stdout or "DESIGN FLAWS" in r.stdout
            or not os.path.isdir(app_path)):
        print("[BLOCKED] the slice isn't coherent yet. Agent should keep reasoning.")
        return

    # The thing becomes real WITH an honest accounting of itself. The ledger
    # rides along with the artifact so the idea's openness is visible, not lost.
    ledger = write_open_threads(sub, app_path, name)
    print(ledger.split("---")[-1].strip())

    print(f"[ok] the agent's reasoning became flesh: {app_path}")
    
    # SANDBOX EXECUTION: test the incarnation
    if SANDBOX_AVAILABLE and os.path.exists(app_path):
        print(f"\n=== SANDBOX: testing incarnation ===")
        try:
            with Sandbox() as sb:
                exec_result = sb.execute_app(app_path)
                print(format_execution_result(exec_result))
                
                # Store execution result for physics feedback
                exec_metadata_path = os.path.join(PROJECTS, name, "execution.yaml")
                with open(exec_metadata_path, "w") as f:
                    yaml.safe_dump(exec_result, f, sort_keys=False)
                
                # Calculate physics weight
                weight = execution_to_physics_weight(exec_result)
                print(f"  [physics] execution weight: {weight:.2f}")
                
                # Feed the outcome back into the substrate (self-training loop):
                # log it, then physics.recompute reshapes the shipped slice's mass.
                try:
                    from physics import record_execution
                    record_execution(sub, weight,
                                     success=exec_result.get("success"),
                                     duration=exec_result.get("duration"),
                                     errors=exec_result.get("errors"))
                except Exception:
                    sub["execution_weight"] = weight
                if weight < 1.0:
                    print("  [feedback] execution failed/poor - agent should reconsider")
                else:
                    print("  [feedback] execution successful - silence validated")
                with open(sp, "w") as f:
                    yaml.safe_dump(sub, f, sort_keys=False)
        except Exception as e:
            print(f"  [sandbox error] {e}")
    else:
        if not SANDBOX_AVAILABLE:
            print(f"  [sandbox] not available - skipping execution test")
        else:
            print(f"  [sandbox] app path not found - skipping execution test")



def main():
    p = argparse.ArgumentParser(prog="forge",
        description="Recursive IDEA->WORD->FLESH harness (layered self-correction).")
    sub = p.add_subparsers(dest="cmd")

    pb = sub.add_parser("build", help="forge a layered build from an idea")
    pb.add_argument("root")
    pb.add_argument("--idea", required=True)
    pb.add_argument("--max-depth", type=int, default=3)
    pb.add_argument("--agent", default="planner",
                    choices=["planner", "ollama"])
    pb.add_argument("--model", default="qwen2.5:3b")

    ps = sub.add_parser("status", help="show layer status")
    ps.add_argument("root")

    psh = sub.add_parser("show", help="show the layer tree")
    psh.add_argument("root")

    pf = sub.add_parser("from-substrate",
                        help="translate a substrate ready-slice into WORD/FLESH")
    pf.add_argument("root")
    pf.add_argument("--name", required=True,
                    help="name for the incarnated mbp layer")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return
    if args.cmd == "build":
        cmd_build(args.root, args.idea, args.max_depth, args.agent, args.model)
    elif args.cmd == "status":
        cmd_status(args.root)
    elif args.cmd == "show":
        cmd_show(args.root)
    elif args.cmd == "from-substrate":
        cmd_from_substrate(args.root, args.name)


if __name__ == "__main__":
    main()
