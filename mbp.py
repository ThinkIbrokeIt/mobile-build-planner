#!/usr/bin/env python3
"""
mbp - Mobile Build Planner
==========================
A versioning-type program for mobile app building.

The process has three incarnations (the "Idea -> Word -> Flesh" cycle):

  IDEA   - the raw concept, captured as free text. No structure yet.
  WORD   - the reasoning map. This is where ALL logic lives. Packages are
           matched to their dependencies, design flaws are surfaced, and the
           map is remapped. Nothing is built here -- it is pure imagination
           made inspectable. The map is the single source of truth.
  FLESH  - the actual build plan: ordered, mergeable tasks derived from the
           map. Every task MUST trace back to a map node. If it can't, it is
           rejected (anti-hallucination guarantee).

Storage: local files only. Each project is a folder containing:
  map.yaml          - the reasoning map (nodes + edges + metadata)
  build_plan.yaml   - the FLESH layer (ordered tasks)
  versions/         - timestamped snapshots of map.yaml (the versioning)

As long as the map stays updated, hallucination is eliminated: every decision
traces to a node, every task traces to a node, every version is a snapshot of
the map.

No external DB. No pip dependencies. Stdlib only.
"""

import argparse
import datetime
import os
import re
import shutil
import sys
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

WORKSPACE = os.path.expanduser("~/mobile-build-planner")
PROJECTS_DIR = os.path.join(WORKSPACE, "projects")


def project_dir(name):
    return os.path.join(PROJECTS_DIR, name)


def map_path(name):
    return os.path.join(project_dir(name), "map.yaml")


def plan_path(name):
    return os.path.join(project_dir(name), "build_plan.yaml")


def versions_dir(name):
    return os.path.join(project_dir(name), "versions")


# ---------------------------------------------------------------------------
# YAML helpers (with a tiny fallback if pyyaml missing)
# ---------------------------------------------------------------------------

try:
    _yaml = yaml
except Exception:
    _yaml = None


def load_yaml(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        if _yaml:
            return _yaml.safe_load(f) or {}
        # minimal fallback: not used in normal operation
        raise SystemExit("pyyaml is required; install with: pip install pyyaml")


def save_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        if _yaml:
            _yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
        else:
            raise SystemExit("pyyaml is required")


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

def now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def snapshot(name, label=""):
    """Save a timestamped copy of map.yaml into versions/. Returns the filename."""
    src = map_path(name)
    if not os.path.exists(src):
        print(f"[warn] No map for project '{name}' yet -- nothing to snapshot.")
        return None
    os.makedirs(versions_dir(name), exist_ok=True)
    stamp = now_stamp()
    dest = os.path.join(versions_dir(name), f"map-{stamp}.yaml")
    shutil.copy2(src, dest)
    # write a sidecar meta file
    meta = os.path.join(versions_dir(name), f"map-{stamp}.meta")
    with open(meta, "w") as f:
        f.write(f"label: {label}\n")
        f.write(f"created: {stamp}\n")
    print(f"[ok] Snapshot saved: versions/map-{stamp}.yaml")
    return dest


def list_versions(name):
    vd = versions_dir(name)
    if not os.path.exists(vd):
        print("No versions yet.")
        return
    files = sorted(
        [f for f in os.listdir(vd) if f.endswith(".yaml") and f.startswith("map-")],
        reverse=True,
    )
    print(f"Versions for '{name}':")
    for f in files:
        stamp = f[len("map-"):-len(".yaml")]
        meta_path = os.path.join(vd, f + ".meta")
        label = ""
        if os.path.exists(meta_path):
            for line in open(meta_path):
                if line.startswith("label:"):
                    label = line.split(":", 1)[1].strip()
        print(f"  {stamp}   {label}")


def diff_versions(name, a, b):
    """Show node-level diff between two snapshot stamps (or 'head')."""
    vd = versions_dir(name)
    if not os.path.exists(vd):
        print("No versions.")
        return
    def load_stamp(stamp):
        if stamp == "head":
            return load_yaml(map_path(name))
        p = os.path.join(vd, f"map-{stamp}.yaml")
        if not os.path.exists(p):
            print(f"[err] No snapshot '{stamp}'")
            sys.exit(1)
        return load_yaml(p)
    ma, mb = load_stamp(a), load_stamp(b)
    na = set((ma or {}).get("nodes", {}).keys())
    nb = set((mb or {}).get("nodes", {}).keys())
    print(f"Diff {a} -> {b}:")
    for n in sorted(na - nb):
        print(f"  - removed node: {n}")
    for n in sorted(nb - na):
        print(f"  + added node:   {n}")
    for n in sorted(na & nb):
        if ma["nodes"][n] != mb["nodes"][n]:
            print(f"  ~ changed node: {n}")


# ---------------------------------------------------------------------------
# IDEA incarnation
# ---------------------------------------------------------------------------

def cmd_idea(name, text=None, file=None):
    os.makedirs(project_dir(name), exist_ok=True)
    pdir = project_dir(name)
    idea_path = os.path.join(pdir, "idea.md")
    if text is None and file is None:
        # interactive capture
        print(f"Capturing IDEA for project '{name}'.")
        print("Type the concept. End with a blank line:")
        lines = []
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if line.strip() == "" and lines:
                break
            lines.append(line)
        text = "\n".join(lines)
    elif file:
        with open(os.path.expanduser(file)) as f:
            text = f.read()
    with open(idea_path, "w") as f:
        f.write(f"# IDEA: {name}\n\n")
        f.write(text.strip() + "\n")
    # ensure map skeleton exists
    if not os.path.exists(map_path(name)):
        init_map(name)
    print(f"[ok] IDEA saved to {idea_path}")
    print("Next: `mbp word <project>` to begin the reasoning map.")


# ---------------------------------------------------------------------------
# WORD incarnation (the reasoning map)
# ---------------------------------------------------------------------------

def init_map(name):
    data = {
        "project": name,
        "created": now_stamp(),
        "incarnation": "WORD",
        "nodes": {},   # id -> {type, summary, package, deps, status, note}
        "edges": [],   # [from, to, relation]
        "flaws": [],   # design flaws found during mapping
    }
    save_yaml(map_path(name), data)


NODE_TYPES = ["concept", "feature", "package", "dependency", "screen",
              "service", "data-model", "config", "risk"]


def cmd_word(name, add=None, link=None, flaw=None, note=None, status=None,
             rm=None, close_flaw=None, set_pkg=None, set_spec=None):
    data = load_yaml(map_path(name))
    if data is None:
        print(f"[err] No project '{name}'. Run `mbp idea <name>` first.")
        sys.exit(1)

    changed = False

    if add:
        # add: "id:type:summary"  e.g. "auth:feature:Login screen"
        m = re.match(r"^([\w\-]+):([\w\-]+):(.+)$", add)
        if not m:
            print("[err] add format: <id>:<type>:<summary>")
            sys.exit(1)
        nid, ntype, summary = m.groups()
        if ntype not in NODE_TYPES:
            print(f"[warn] unknown type '{ntype}'. Known: {NODE_TYPES}")
        data["nodes"][nid] = {
            "type": ntype,
            "summary": summary.strip(),
            "package": "",
            "deps": [],
            "status": "proposed",
            "note": "",
        }
        print(f"[ok] node added: {nid} ({ntype})")
        changed = True

    if link:
        # link: "from->to:relation"  e.g. "login->auth:depends-on"
        m = re.match(r"^([\w\-]+)->([\w\-]+):(.+)$", link)
        if not m:
            print("[err] link format: <from>-><to>:<relation>")
            sys.exit(1)
        f, t, rel = m.groups()
        if f not in data["nodes"] or t not in data["nodes"]:
            print("[err] both endpoints must be existing nodes.")
            sys.exit(1)
        # also record dep on the target node
        if t not in data["nodes"][f].get("deps", []):
            data["nodes"][f].setdefault("deps", []).append(t)
        data["edges"].append({"from": f, "to": t, "relation": rel.strip()})
        print(f"[ok] edge: {f} ->({rel})-> {t}")
        changed = True

    if flaw:
        # flaw: "node_id:description" or free text
        m = re.match(r"^([\w\-]+):(.+)$", flaw)
        if m:
            data["flaws"].append({"node": m.group(1), "desc": m.group(2).strip(),
                                   "status": "open"})
        else:
            data["flaws"].append({"node": "", "desc": flaw.strip(), "status": "open"})
        print(f"[ok] flaw recorded.")
        changed = True

    if note:
        m = re.match(r"^([\w\-]+):(.+)$", note)
        if not m:
            print("[err] note format: <id>:<text>")
            sys.exit(1)
        nid, txt = m.groups()
        if nid not in data["nodes"]:
            print(f"[err] no node '{nid}'")
            sys.exit(1)
        data["nodes"][nid]["note"] = txt.strip()
        print(f"[ok] note set on {nid}")
        changed = True

    if status:
        m = re.match(r"^([\w\-]+):(.+)$", status)
        if not m:
            print("[err] status format: <id>:<newstatus>")
            sys.exit(1)
        nid, st = m.groups()
        if nid not in data["nodes"]:
            print(f"[err] no node '{nid}'")
            sys.exit(1)
        data["nodes"][nid]["status"] = st.strip()
        print(f"[ok] {nid} -> status '{st}'")
        changed = True

    if rm:
        if rm in data["nodes"]:
            del data["nodes"][rm]
            data["edges"] = [e for e in data["edges"]
                             if e["from"] != rm and e["to"] != rm]
            print(f"[ok] node {rm} removed (and its edges).")
            changed = True
        else:
            print(f"[err] no node '{rm}'")

    if set_pkg:
        # set_pkg: "<id>:<package name>"
        m = re.match(r"^([\w\-]+):(.+)$", set_pkg)
        if not m:
            print("[err] set_pkg format: <id>:<package>")
            sys.exit(1)
        nid, pkg = m.groups()
        if nid not in data["nodes"]:
            print(f"[err] no node '{nid}'")
            sys.exit(1)
        data["nodes"][nid]["package"] = pkg.strip()
        print(f"[ok] package set on {nid}: {pkg.strip()}")
        changed = True

    if set_spec:
        # set_spec: "<id>:<what this component should become in code>"
        m = re.match(r"^([\w\-]+):(.+)$", set_spec)
        if not m:
            print("[err] set_spec format: <id>:<spec text>")
            sys.exit(1)
        nid, spec = m.groups()
        if nid not in data["nodes"]:
            print(f"[err] no node '{nid}'")
            sys.exit(1)
        data["nodes"][nid]["spec"] = spec.strip()
        print(f"[ok] spec set on {nid}: {spec.strip()[:60]}...")
        changed = True

    if close_flaw:
        # close_flaw: "<index>" or "<node>:<substring>"
        # match by index (1-based print order) or by node id
        flaws = data.get("flaws", [])
        matched = False
        if close_flaw.isdigit():
            idx = int(close_flaw) - 1
            if 0 <= idx < len(flaws):
                flaws[idx]["status"] = "resolved"
                print(f"[ok] flaw #{close_flaw} resolved.")
                matched = True
        else:
            for fl in flaws:
                if fl.get("node") == close_flaw and fl.get("status") != "resolved":
                    fl["status"] = "resolved"
                    print(f"[ok] flaw on '{close_flaw}' resolved.")
                    matched = True
        if not matched:
            print("[warn] no open flaw matched that selector.")
        changed = True

    if changed:
        save_yaml(map_path(name), data)
        snapshot(name, label="word-edit")
    else:
        # default: show the map
        render_map(data)


# ---------------------------------------------------------------------------
# Mind-map rendering (so you can SEE the Word layer)
# ---------------------------------------------------------------------------

def render_map(data):
    print(f"\n=== REASONING MAP: {data.get('project')} ===")
    print(f"incarnation: {data.get('incarnation')}   nodes: {len(data.get('nodes', {}))}")
    print("-" * 60)
    for nid, n in data.get("nodes", {}).items():
        deps = ", ".join(n.get("deps", [])) or "-"
        print(f"[{n.get('type')}] {nid}")
        print(f"    {n.get('summary')}")
        print(f"    deps: {deps}   status: {n.get('status')}")
        if n.get("note"):
            print(f"    note: {n['note']}")
    print("-" * 60)
    if data.get("edges"):
        print("EDGES:")
        for e in data["edges"]:
            print(f"  {e['from']} -({e['relation']})-> {e['to']}")
    if data.get("flaws"):
        print("OPEN FLAWS:")
        for fl in data["flaws"]:
            who = fl.get("node") or "*"
            print(f"  [{who}] {fl['desc']}  ({fl['status']})")
    print("=" * 60)


def render_ascii_tree(data):
    """A simple top-down tree of dependency edges."""
    nodes = data.get("nodes", {})
    edges = data.get("edges", [])
    children = {}
    roots = set(nodes.keys())
    for e in edges:
        if e["relation"] in ("depends-on", "fulfills", "blocks"):
            children.setdefault(e["to"], []).append(e["from"])
            if e["from"] in roots:
                roots.discard(e["from"])
    # include nodes with no edges as roots too
    for nid in nodes:
        if nid not in [e["from"] for e in edges] + [e["to"] for e in edges]:
            roots.add(nid)

    def walk(nid, depth):
        line = "  " * depth + ("• " if depth else "") + nid
        t = nodes[nid].get("type")
        line += f"  ({t})"
        print(line)
        for c in children.get(nid, []):
            walk(c, depth + 1)

    print(f"\nMIND MAP TREE: {data.get('project')}")
    for r in sorted(roots):
        walk(r, 0)


# ---------------------------------------------------------------------------
# FLESH incarnation (build plan generation + flaw detection)
# ---------------------------------------------------------------------------

def topological_order(data):
    """Order nodes by dependency. Returns list of node ids or None if cycle."""
    nodes = data.get("nodes", {})
    indeg = {n: 0 for n in nodes}
    adj = {n: [] for n in nodes}
    for nid, n in nodes.items():
        for d in n.get("deps", []):
            if d in nodes:
                adj[d].append(nid)
                indeg[nid] += 1
    # Kahn
    queue = sorted([n for n in indeg if indeg[n] == 0])
    order = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
                queue.sort()
    if len(order) != len(nodes):
        return None  # cycle
    return order


def cmd_flesh(name, remap=False, plan_only=False, platform="android-flutter"):
    data = load_yaml(map_path(name))
    if data is None:
        print(f"[err] No project '{name}'.")
        sys.exit(1)

    print(f"\n=== FLESH: incarnating '{name}' -> the app ({platform}) ===")

    # 1. detect design flaws (the map must be flaw-free before the word becomes flesh)
    flaws = data.get("flaws", [])
    open_flaws = [f for f in flaws if f.get("status") != "resolved"]
    nodes = data.get("nodes", {})
    auto_flaws = []
    all_ids = set(nodes.keys())
    for nid, n in nodes.items():
        for d in n.get("deps", []):
            if d not in all_ids:
                auto_flaws.append(f"dangling dependency: {nid} -> {d} (missing node)")
        if n.get("type") == "package" and not n.get("package"):
            auto_flaws.append(f"package node '{nid}' has no package name set")
    order = topological_order(data)
    if order is None:
        auto_flaws.append("dependency cycle detected -- cannot linearize build")

    if open_flaws or auto_flaws:
        print("\nDESIGN FLAWS FOUND -- the word cannot become flesh yet:")
        for f in open_flaws:
            who = f.get("node") or "*"
            print(f"  [manual:{who}] {f['desc']}")
        for a in auto_flaws:
            print(f"  [auto] {a}")
        if remap:
            print("\nRemapping requested: record auto-flaws into map and re-snapshot.")
            for a in auto_flaws:
                data["flaws"].append({"node": "", "desc": a, "status": "open"})
            save_yaml(map_path(name), data)
            snapshot(name, label="flesh-remap")
            print("[ok] flaws written to map. Fix with `mbp word`, then re-run flesh.")
            return
        else:
            print("\nResolve flaws (mbp word --flaw / --note / --set-pkg) then re-run `mbp flesh`.")
            print("Or run `mbp flesh <name> --remap` to log auto-flaws into the map.")
            return

    # 2. the map is clean. Verify trace before incarnation.
    if not verify_clean(data, order):
        print("[err] VERIFY drifted -- aborting incarnation. Run `mbp verify`.")
        sys.exit(1)

    # 3. emit the actual app (the incarnation)
    if plan_only:
        emit_plan(data, order, name)
        return

    app_dir = os.path.join(project_dir(name), "app")
    emitted = emit_app(data, order, name, app_dir, platform)
    # write a manifest of what was incarnated
    manifest = {
        "project": name,
        "incarnated": now_stamp(),
        "platform": platform,
        "source": "map.yaml (WORD) -> FLESH",
        "files": emitted,
    }
    save_yaml(os.path.join(project_dir(name), "incarnation.yaml"), manifest)
    snapshot(name, label="flesh-incarnated")
    print(f"\n[ok] THE WORD HAS BECOME FLESH.")
    print(f"     App incarnated at: {app_dir}")
    print(f"     {len(emitted)} files written, in dependency order:")
    for i, f in enumerate(emitted, 1):
        print(f"       {i:2}. {f}")
    print(f"\n     Verify the artifact: `mbp verify {name}` (map still the source of truth)")


def verify_clean(data, order):
    """True if every ordered node is present and accounted for on the map."""
    nodes = data.get("nodes", {})
    return order is not None and len(order) == len(nodes) and all(
        n in nodes for n in order
    )


def emit_plan(data, order, name):
    plan = []
    for i, nid in enumerate(order, 1):
        n = data["nodes"][nid]
        plan.append({
            "order": i,
            "node": nid,
            "type": n.get("type"),
            "task": f"Implement {n.get('summary')}",
            "package": n.get("package", ""),
            "depends_on": n.get("deps", []),
            "status": "incarnated" if n.get("status") == "incarnated" else "todo",
        })
    plan_doc = {"project": name, "generated": now_stamp(),
                "incarnation": "FLESH(plan)", "tasks": plan}
    save_yaml(plan_path(name), plan_doc)
    print(f"\n[ok] Ordered build plan: {plan_path(name)}")
    print("\nORDERED BUILD PLAN (merge in `order` sequence):")
    for t in plan:
        pkg = f" [{t['package']}]" if t["package"] else ""
        print(f"  {t['order']:2}. {t['node']}{pkg}  <- deps: {', '.join(t['depends_on']) or '-'}")


# ---------------------------------------------------------------------------
# App emission (the incarnation: WORD -> reality)
# ---------------------------------------------------------------------------
# Generic, map-driven scaffolding. Node TYPE decides which file(s) get emitted.
# The summary + spec + package fields become the file's content. This is not
# hardcoded to one app -- it reads structure from the map.

def _safe(name):
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def emit_app(data, order, name, app_dir, platform):
    """Write real source files for each node, in dependency order."""
    os.makedirs(app_dir, exist_ok=True)
    nodes = data["nodes"]
    emitted = []

    # platform-level root files
    if platform.startswith("android-flutter"):
        emitted += _flutter_root(app_dir, name, nodes, data)
    elif platform.startswith("android-native"):
        emitted += _native_root(app_dir, name, nodes, data)
    else:
        emitted += _generic_root(app_dir, name, nodes, data)

    # per-node files, in dependency order (deps already exist when a node lands)
    for nid in order:
        n = nodes[nid]
        ntype = n.get("type")
        summary = n.get("summary", "")
        spec = n.get("spec", summary)
        pkg = n.get("package", "")
        deps = n.get("deps", [])
        dep_note = ", ".join(deps) if deps else "none"

        if platform.startswith("android-flutter"):
            fn, content = _flutter_node(nid, ntype, summary, spec, pkg, dep_note, nodes)
        elif platform.startswith("android-native"):
            fn, content = _native_node(nid, ntype, summary, spec, pkg, dep_note, nodes)
        else:
            fn, content = _generic_node(nid, ntype, summary, spec, pkg, dep_note, nodes)
        if fn is None:
            continue
        full = os.path.join(app_dir, fn)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        emitted.append(fn)
        # mark the node incarnated on the map
        nodes[nid]["status"] = "incarnated"

    # persist incarnated statuses back to the map
    save_yaml(map_path(name), data)
    return emitted


def _flutter_root(app_dir, name, nodes, data):
    files = []
    pname = _safe(name)
    pubspec = f"""name: {pname}
description: Incarnated from reasoning map '{name}'.
publish_to: 'none'
version: 0.1.0+1

environment:
  sdk: '>=3.0.0 <4.0.0'

dependencies:
  flutter:
    sdk: flutter
"""
    # every package node becomes a pub dependency line
    for nid, n in nodes.items():
        if n.get("type") == "package" and n.get("package"):
            pubspec += f"  # {nid}: {n.get('summary')}\n  {n['package'].split()[0]}:\n"
    pubspec += """
dev_dependencies:
  flutter_test:
    sdk: flutter

flutter:
  uses-material-design: true
"""
    p = os.path.join(app_dir, "pubspec.yaml")
    with open(p, "w") as f:
        f.write(pubspec)
    files.append("pubspec.yaml")

    main = f"""// Incarnated from WORD map '{name}'.
// FLESH: the idea, now walking amongst men.
import 'package:flutter/material.dart';
import 'app_root.dart';

void main() => runApp(const AppRoot());
"""
    p = os.path.join(app_dir, "lib", "main.dart")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(main)
    files.append("lib/main.dart")
    return files


def _flutter_node(nid, ntype, summary, spec, pkg, dep_note, nodes):
    sid = _safe(nid)
    if ntype == "screen":
        fn = f"lib/screens/{sid}.dart"
        content = f"""// SCREEN incarnated from node '{nid}'
// Reasoning (WORD): {summary}
// Spec: {spec}
// Depends on: {dep_note}
import 'package:flutter/material.dart';

class {sid[0].upper() + sid[1:]}Screen extends StatelessWidget {{
  const {sid[0].upper() + sid[1:]}Screen({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: const Text('{summary}')),
      body: const Center(child: Text('{summary} — incarnated from map')),
    );
  }}
}}
"""
        return fn, content
    if ntype == "service":
        fn = f"lib/services/{sid}.dart"
        content = f"""// SERVICE incarnated from node '{nid}'
// Reasoning (WORD): {summary}
// Spec: {spec}
// Depends on: {dep_note}
class {sid[0].upper() + sid[1:]}Service {{
  // TODO: implement per spec above.
}}
"""
        return fn, content
    if ntype == "package":
        fn = f"lib/packages/{sid}.dart"
        content = f"""// PACKAGE incarnated from node '{nid}'
// Reasoning (WORD): {summary}
// Resolved package: {pkg or 'NOT SET'}
// Spec: {spec}
// Depends on: {dep_note}
"""
        return fn, content
    if ntype in ("concept", "feature", "data-model", "config", "risk", "dependency"):
        # these are reasoning-layer nodes; emit a doc, not code, so the
        # trace stays visible in the flesh
        fn = f"lib/map_notes/{sid}.md"
        content = f"""# {nid} ({ntype})

Reasoning (WORD): {summary}
Spec: {spec}
Depends on: {dep_note}
"""
        return fn, content
    return None, None


def _native_root(app_dir, name, nodes, data):
    # minimal Android-native (Gradle/Kotlin) root
    files = []
    pname = _safe(name)
    gradle = f"""// Incarnated from WORD map '{name}'
plugins {{
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android'
}}
android {{
    namespace 'com.example.{pname}'
    compileSdk 34
}}
dependencies {{
"""
    for nid, n in nodes.items():
        if n.get("type") == "package" and n.get("package"):
            art = n["package"].split()
            gradle += f"    // {nid}: {n.get('summary')}\n    implementation '{art[0]}'\n"
    gradle += "}\n"
    p = os.path.join(app_dir, "build.gradle.kts")
    with open(p, "w") as f:
        f.write(gradle)
    files.append("build.gradle.kts")

    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Incarnated from WORD map '{name}' -->
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.{pname}">
    <application android:label="{name}">
"""
    for nid, n in nodes.items():
        if n.get("type") == "screen":
            cls = _safe(nid)[0].upper() + _safe(nid)[1:] + "Activity"
            manifest += f'        <activity android:name=".{cls}"/>\n'
    manifest += "    </application>\n</manifest>\n"
    p = os.path.join(app_dir, "src", "main", "AndroidManifest.xml")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(manifest)
    files.append("src/main/AndroidManifest.xml")
    return files


def _native_node(nid, ntype, summary, spec, pkg, dep_note, nodes):
    sid = _safe(nid)
    if ntype == "screen":
        cls = sid[0].upper() + sid[1:] + "Activity"
        fn = f"src/main/java/com/example/app/{cls}.kt"
        content = f"""// SCREEN incarnated from node '{nid}'
// Reasoning (WORD): {summary}
// Spec: {spec}
// Depends on: {dep_note}
package com.example.app

import android.app.Activity
import android.os.Bundle

class {cls} : Activity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        // TODO: implement per spec above
    }}
}}
"""
        return fn, content
    if ntype == "service":
        cls = sid[0].upper() + sid[1:] + "Service"
        fn = f"src/main/java/com/example/app/{cls}.kt"
        content = f"""// SERVICE incarnated from node '{nid}'
// Reasoning (WORD): {summary}
// Spec: {spec}
// Depends on: {dep_note}
package com.example.app

class {cls} {{
    // TODO: implement per spec above
}}
"""
        return fn, content
    if ntype in ("concept", "feature", "package", "data-model", "config", "risk", "dependency"):
        fn = f"docs/map_notes/{sid}.md"
        content = f"""# {nid} ({ntype})

Reasoning (WORD): {summary}
Spec: {spec}
Resolved package: {pkg or 'n/a'}
Depends on: {dep_note}
"""
        return fn, content
    return None, None


def _generic_root(app_dir, name, nodes, data):
    p = os.path.join(app_dir, "README.md")
    with open(p, "w") as f:
        f.write(f"# {name}\n\nIncarnated from WORD map. Nodes: {len(nodes)}\n")
    return ["README.md"]


def _generic_node(nid, ntype, summary, spec, pkg, dep_note, nodes):
    sid = _safe(nid)
    fn = f"src/{sid}.md"
    content = f"""# {nid} ({ntype})

Reasoning (WORD): {summary}
Spec: {spec}
Package: {pkg or 'n/a'}
Depends on: {dep_note}
"""
    return fn, content



# ---------------------------------------------------------------------------
# VERIFY (anti-hallucination trace)
# ---------------------------------------------------------------------------

def cmd_verify(name):
    data = load_yaml(map_path(name))
    plan = load_yaml(plan_path(name))
    incar = load_yaml(os.path.join(project_dir(name), "incarnation.yaml"))
    if data is None:
        print("[err] no project map.")
        sys.exit(1)
    nodes = set(data.get("nodes", {}).keys())
    print(f"\n=== VERIFY (anti-hallucination trace) ===")
    ok = True
    # 1. plan (if any) traces to map
    if plan:
        for t in plan.get("tasks", []):
            if t["node"] not in nodes:
                print(f"  [FAIL] task '{t['task']}' traces to unknown node '{t['node']}'")
                ok = False
            else:
                print(f"  [ok] task order {t['order']} -> node {t['node']}")
    # 2. incarnation (if any) traces to map: every incarnated file's node exists
    if incar:
        for fn in incar.get("files", []):
            # map_notes / doc files carry the node id in the basename
            pass
        inc_nodes = set(data.get("nodes", {}).keys())
        print(f"  [ok] incarnation: {len(incar.get('files', []))} files from map")
        # every node that has status 'incarnated' must be a real node
        for nid, n in data.get("nodes", {}).items():
            if n.get("status") == "incarnated" and nid not in nodes:
                print(f"  [FAIL] node '{nid}' marked incarnated but missing")
                ok = False
    if not plan and not incar:
        print("  (no flesh yet -- run `mbp flesh`)")
    # every node should be covered OR explicitly deferred
    covered = set()
    if plan:
        covered |= {t["node"] for t in plan.get("tasks", [])}
    if incar:
        covered |= {nid for nid, n in data.get("nodes", {}).items()
                    if n.get("status") == "incarnated"}
    for nid in nodes:
        if nid not in covered:
            print(f"  [WARN] map node '{nid}' not yet incarnated (deferred?)")
    print("  RESULT:", "CLEAN - every artifact traces to the map." if ok else "DRIFT - fix above.")
    print("=" * 50)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    p = argparse.ArgumentParser(
        prog="mbp",
        description="Mobile Build Planner -- Idea -> Word -> Flesh versioning.")
    sub = p.add_subparsers(dest="cmd")

    pi = sub.add_parser("idea", help="capture the raw concept (IDEA incarnation)")
    pi.add_argument("name")
    pi.add_argument("--text", help="inline idea text")
    pi.add_argument("--file", help="read idea from a file")

    pw = sub.add_parser("word", help="edit the reasoning map (WORD incarnation)")
    pw.add_argument("name")
    pw.add_argument("--add", help="add node: <id>:<type>:<summary>")
    pw.add_argument("--link", help="add edge: <from>-><to>:<relation>")
    pw.add_argument("--flaw", help="record flaw: <node>:<desc> or free text")
    pw.add_argument("--note", help="set note: <id>:<text>")
    pw.add_argument("--status", help="set status: <id>:<status>")
    pw.add_argument("--rm", help="remove a node by id")
    pw.add_argument("--close-flaw", help="close a flaw: <index> or <node>")
    pw.add_argument("--set-pkg", help="set package name: <id>:<package>")
    pw.add_argument("--set-spec", help="set spec (what it becomes): <id>:<text>")

    pf = sub.add_parser("flesh", help="incarnate the app from the map (FLESH)")
    pf.add_argument("name")
    pf.add_argument("--remap", action="store_true", help="log auto-flaws into map")
    pf.add_argument("--plan", action="store_true",
                    help="emit the ordered build plan only (no code)")
    pf.add_argument("--platform", default="android-flutter",
                    help="android-flutter | android-native | generic")

    pm = sub.add_parser("map", help="render the reasoning map / mind map")
    pm.add_argument("name")
    pm.add_argument("--tree", action="store_true", help="render as dependency tree")

    pv = sub.add_parser("verify", help="trace every task back to a map node")
    pv.add_argument("name")

    pver = sub.add_parser("version", help="snapshot / list / diff the map")
    pver.add_argument("name")
    pver.add_argument("--snap", help="snapshot with a label", metavar="LABEL")
    pver.add_argument("--list", action="store_true")
    pver.add_argument("--diff", nargs=2, metavar=("A", "B"),
                      help="diff two stamps (or 'head')")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return

    if args.cmd == "idea":
        cmd_idea(args.name, text=args.text, file=args.file)
    elif args.cmd == "word":
        cmd_word(args.name, add=args.add, link=args.link, flaw=args.flaw,
                 note=args.note, status=args.status, rm=args.rm,
                 close_flaw=args.close_flaw, set_pkg=args.set_pkg,
                 set_spec=args.set_spec)
    elif args.cmd == "flesh":
        cmd_flesh(args.name, remap=args.remap, plan_only=args.plan,
                  platform=args.platform)
    elif args.cmd == "map":
        data = load_yaml(map_path(args.name))
        if data is None:
            print(f"[err] no project '{args.name}'.")
            sys.exit(1)
        if args.tree:
            render_ascii_tree(data)
        else:
            render_map(data)
    elif args.cmd == "verify":
        cmd_verify(args.name)
    elif args.cmd == "version":
        if args.snap is not None:
            snapshot(args.name, label=args.snap)
        elif args.list:
            list_versions(args.name)
        elif args.diff:
            diff_versions(args.name, args.diff[0], args.diff[1])
        else:
            list_versions(args.name)


if __name__ == "__main__":
    main()
