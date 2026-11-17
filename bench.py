#!/usr/bin/env python3
"""
bench.py — is the substrate actually useful? A small, honest benchmark.
======================================================================

The claim under test is narrow and falsifiable: schema/tool-calling agents are
good at emitting structured output but bad at holding and surfacing CONFLICTS
between requirements. The substrate adds a deliberation layer that represents
tensions and refuses to ship while one is open.

Design (so the result can't be dismissed as rigged):

  * 5 tasks — 3 with a PLANTED requirement contradiction, 2 COHERENT CONTROLS
    (to measure false-positive blocking).
  * 3 deterministic pipelines over the SAME tasks:
      plain      a schema agent: requirements -> structured output -> ship.
                 No representation of conflict.
      graph      ABLATION: builds the same thought graph (branch/link/name/
                 contradict) but never consults the field and never gates —
                 ships unconditionally. Isolates "having a graph" from
                 "acting on conflict".
      substrate  full: graph + salience field + gate + execution feedback.
                 Surfaces open contradictions, blocks unresolved ones, resolves
                 and commits the rest.
  * optional LIVE arm (`--brain openrouter|ollama`) that runs agent.py end to
    end, to show the pipeline works with a real model (skipped if unavailable).

Metrics per run:
  present            planted contradictions (ground truth)
  surfaced           contradictions made visible (0 for plain/graph by design)
  shipped            an artifact was incarnated
  incoherent_shipped shipped while a real contradiction was still open
  false_block        blocked an artifact on a COHERENT task (should be 0)
  verified/executed  shipped artifact verifies / runs
  ops                deliberation steps (cost)

Run:  python3 bench.py
      python3 bench.py --json
      python3 bench.py --brain openrouter --live-tasks 1 --live-max-turns 8
"""

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mbp        # noqa: E402
import substrate as S   # noqa: E402
import physics as P     # noqa: E402
import forge      # noqa: E402

try:
    from sandbox import Sandbox
    SANDBOX = True
except Exception:  # pragma: no cover
    SANDBOX = False


TASKS = [
    {
        "name": "habit-tracker",
        "seed": "a habit tracker that gamifies daily tasks",
        "facts": [("t1", "the one committed act at its center", "committed"),
                  ("t2", "what it must never become: no shaming", "must")],
        "contradiction": ("t1", "t2"),
        "resolution": "the act IS the never — one promise a day is the anti-shame",
    },
    {
        "name": "offline-sync",
        "seed": "a notes app that works fully offline and syncs",
        "facts": [("t1", "local-first storage is the source of truth", "local"),
                  ("t2", "the server is the source of truth", "server")],
        "contradiction": ("t1", "t2"),
        "resolution": None,   # genuinely unresolved — the gate must block
    },
    {
        "name": "auth-permissions",
        "seed": "an admin dashboard with per-user permissions",
        "facts": [("t1", "admins must see all data", "admin"),
                  ("t2", "no user data is exposed without explicit consent", "consent")],
        "contradiction": ("t1", "t2"),
        "resolution": "admins see aggregates; raw data needs consent",
    },
    # ---- coherent controls (no contradiction) ----
    {
        "name": "settings-page",
        "seed": "a settings page for the app",
        "facts": [("t1", "a dark theme toggle", "theme"),
                  ("t2", "a notification-frequency preference", "preference")],
        "contradiction": None,
        "resolution": None,
    },
    {
        "name": "note-search",
        "seed": "search across your notes",
        "facts": [("t1", "keep a local index of notes", "index"),
                  ("t2", "show results as you type", "query")],
        "contradiction": None,
        "resolution": None,
    },
]

CONTRADICTION_TASKS = [t for t in TASKS if t.get("contradiction")]
CONTROL_TASKS = [t for t in TASKS if not t.get("contradiction")]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _silent(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*a, **k)


def _exec_ok(app_dir):
    if not SANDBOX or not os.path.isdir(app_dir):
        return False
    with Sandbox() as sb:
        return bool(sb.execute_app(app_dir)["success"])


def _verify(name):
    r = subprocess.run([sys.executable, mbp.__file__, "verify", name],
                       cwd=HERE, capture_output=True, text=True)
    return r.returncode == 0 and "CLEAN" in r.stdout


def _commit_gated(root):
    """Full substrate commit (runs forge, which enforces the gate)."""
    name = f"{root}__incarnated"
    try:
        _silent(forge.cmd_from_substrate, root, name)
    except SystemExit:
        pass
    return os.path.join(S.PROJECTS, name, "app")


def _map_from_substrate(root, name):
    """Ungated WORD/FLESH: build the map straight from the substrate thoughts
    and emit — no contradiction check. (Used only by the graph ablation.)"""
    sub = S.load(root)
    ready = sub.get("ready", [])
    thoughts = sub["thoughts"]
    nodes, edges = {}, []
    for tid in ready:
        t = thoughts[tid]
        nodes[tid] = {"type": t.get("type") or "thought", "summary": t["text"],
                      "deps": [], "package": "", "spec": "", "status": "proposed",
                      "note": ""}
        for ln in t.get("links", []):
            if isinstance(ln, dict):
                edges.append({"from": tid, "to": ln["to"], "relation": ln["how"]})
                if ln["how"] in ("needs", "depends-on", "branch", "fulfills"):
                    nodes[tid]["deps"].append(ln["to"])
            else:
                edges.append({"from": tid, "to": ln, "relation": "branch"})
                nodes[tid]["deps"].append(ln)
        for c in t.get("contradicts", []):
            if c in ready:
                edges.append({"from": tid, "to": c, "relation": "contradicts"})
    data = {"project": name, "nodes": nodes, "edges": edges, "flaws": []}
    mbp.save_yaml(mbp.map_path(name), data)
    order = mbp.topological_order(data)
    app_dir = os.path.join(mbp.project_dir(name), "app")
    _silent(mbp.emit_app, data, order, name, app_dir, "python")
    return app_dir


def _blank_row(task, pipeline):
    return {"task": task["name"], "pipeline": pipeline,
            "present": int(bool(task.get("contradiction"))),
            "surfaced": 0, "shipped": 0, "incoherent_shipped": 0,
            "false_block": 0, "verified": 0, "executed": 0, "ops": 0,
            "resolved": False}


def _finalize(task, row, app_dir):
    has_con = bool(task.get("contradiction"))
    shipped = os.path.isdir(app_dir)
    row["shipped"] = int(shipped)
    if shipped:
        row["verified"] = 1 if _verify(os.path.basename(os.path.dirname(app_dir))) else 0
        row["executed"] = int(_exec_ok(app_dir))
    else:
        row["false_block"] = 1 if not has_con else 0
    return row


# ---------------------------------------------------------------------------
# Pipeline: plain schema agent (no deliberation, no gate)
# ---------------------------------------------------------------------------

def run_plain(task):
    name = f"bench_plain_{task['name']}"
    pdir = mbp.project_dir(name)
    shutil.rmtree(pdir, ignore_errors=True)
    row = _blank_row(task, "plain")

    nodes = {"t0": {"type": "seed", "summary": task["seed"], "deps": [],
                    "package": "", "spec": "", "status": "proposed", "note": ""}}
    edges = []
    for fid, text, kind in task["facts"]:
        nodes[fid] = {"type": kind, "summary": text, "deps": ["t0"],
                      "package": "", "spec": "", "status": "proposed", "note": ""}
        edges.append({"from": fid, "to": "t0", "relation": "needs"})
    data = {"project": name, "nodes": nodes, "edges": edges, "flaws": []}
    mbp.save_yaml(mbp.map_path(name), data)
    order = mbp.topological_order(data)
    app_dir = os.path.join(pdir, "app")
    _silent(mbp.emit_app, data, order, name, app_dir, "python")
    row["ops"] = len(nodes)

    _finalize(task, row, app_dir)
    # plain never represents conflict: if one was planted, it shipped incoherent
    row["incoherent_shipped"] = int(row["shipped"] and bool(task.get("contradiction")))
    return row


# ---------------------------------------------------------------------------
# Pipeline: graph-only ablation (structure, but no gate)
# ---------------------------------------------------------------------------

def _replay_graph(task, root):
    """Replay the requirements as thoughts; return (ops, seeded_data)."""
    shutil.rmtree(os.path.join(S.PROJECTS, root), ignore_errors=True)
    shutil.rmtree(os.path.join(S.PROJECTS, root + "__incarnated"), ignore_errors=True)
    ops = 0

    def do(fn, *args):
        nonlocal ops
        data = S.load(root)
        _silent(fn, root, data, *args)
        S.save(root, data)
        ops += 1

    do(S.op_seed, task["seed"])
    for fid, text, _k in task["facts"]:
        do(S.op_branch, "t0", text)
    for fid, _t, kind in task["facts"]:
        do(S.op_link, fid, "t0", "needs")
        do(S.op_name, fid, kind)
    if task.get("contradiction"):
        a, b = task["contradiction"]
        do(S.op_contradict, a, b)
    ids = ["t0"] + [f for f, _t, _k in task["facts"]]
    do(S.op_ready, ids)
    return ops, ids


def run_graph(task):
    root = f"bench_graph_{task['name']}"
    row = _blank_row(task, "graph")
    ops, _ids = _replay_graph(task, root)
    row["ops"] = ops

    name = f"{root}__incarnated"
    app_dir = _map_from_substrate(root, name)   # ungated
    _finalize(task, row, app_dir)
    # graph has the structure but never acts on conflict → ships incoherent
    row["incoherent_shipped"] = int(row["shipped"] and bool(task.get("contradiction")))
    return row


# ---------------------------------------------------------------------------
# Pipeline: full substrate (graph + field gate + execution feedback)
# ---------------------------------------------------------------------------

def run_substrate(task):
    root = f"bench_sub_{task['name']}"
    row = _blank_row(task, "substrate")
    ops, ids = _replay_graph(task, root)

    data = S.load(root)
    row["surfaced"] = len(P.open_tensions(data))

    if task.get("contradiction") and task.get("resolution"):
        a, b = task["contradiction"]
        d = S.load(root)
        _silent(S.op_resolve, root, d, a, b, task["resolution"])
        S.save(root, d)
        ops += 1
        row["resolved"] = True

    # mass of the ready slice before the run (to show execution feedback)
    d = S.load(root)
    P.recompute(d, P.DEFAULT)
    mass_before = {i: round(d["thoughts"][i]["mass"], 3) for i in ids if i in d["thoughts"]}

    app_dir = _commit_gated(root)
    _finalize(task, row, app_dir)
    row["ops"] = ops
    # incoherent only if it shipped while a live tension remained (gate should stop this)
    if row["shipped"]:
        row["incoherent_shipped"] = int(bool(P.open_tensions(S.load(root))))
    row["mass_before"] = mass_before
    d = S.load(root)
    P.recompute(d, P.DEFAULT)
    row["mass_after"] = {i: round(d["thoughts"][i]["mass"], 3) for i in ids if i in d["thoughts"]}
    return row


# ---------------------------------------------------------------------------
# Pipeline: live model arm (opt-in)
# ---------------------------------------------------------------------------

def run_live(task, brain, model, max_turns, timeout):
    root = f"bench_live_{task['name']}"
    shutil.rmtree(os.path.join(S.PROJECTS, root), ignore_errors=True)
    shutil.rmtree(os.path.join(S.PROJECTS, root + "__incarnated"), ignore_errors=True)
    row = _blank_row(task, f"live:{brain}")
    try:
        r = subprocess.run(
            [sys.executable, "agent.py", root, "--seed", task["seed"],
             "--brain", brain, "--model", model, "--max-turns", str(max_turns)],
            cwd=HERE, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        row["skipped"] = True
        row["note"] = f"timed out after {timeout}s"
        return row

    out = r.stdout + r.stderr
    if "switching to echo" in out:
        row["skipped"] = True
        row["note"] = f"{brain} unavailable (fell back to echo)"
        return row

    data = S.load(root) or {}
    trail = data.get("trail", [])
    row["surfaced"] = sum(1 for e in trail if e.get("act") in ("contradict", "resolve"))
    row["ops"] = len(trail)
    app_dir = os.path.join(S.PROJECTS, f"{root}__incarnated", "app")
    _finalize(task, row, app_dir)
    if row["shipped"]:
        row["incoherent_shipped"] = int(bool(P.open_tensions(data)))
    return row


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _table(rows):
    hdr = (f"{'task':<18}{'pipeline':<17}{'present':>8}{'surfaced':>9}"
           f"{'incoh':>6}{'shipped':>8}{'fblk':>6}{'verify':>7}{'exec':>6}{'ops':>5}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        if r.get("skipped"):
            print(f"{r['task']:<18}{r['pipeline']:<17}  SKIPPED — {r.get('note','')}")
            continue
        print(f"{r['task']:<18}{r['pipeline']:<17}{r['present']:>8}{r['surfaced']:>9}"
              f"{r['incoherent_shipped']:>6}{r['shipped']:>8}{r['false_block']:>6}"
              f"{r['verified']:>7}{r['executed']:>6}{r['ops']:>5}")


def _summary(rows, pipelines):
    nc, nk = len(CONTRADICTION_TASKS), len(CONTROL_TASKS)
    print(f"\nSUMMARY  ({nc} contradiction tasks, {nk} coherent controls)")
    print(f"  {'pipeline':<17}{'surfaced':>10}{'incoh_shipped':>15}{'false_block':>13}")
    for p in pipelines:
        pr = [r for r in rows if r["pipeline"] == p and not r.get("skipped")]
        if not pr:
            continue
        surf = sum(r["surfaced"] for r in pr if r["present"])
        incoh = sum(r["incoherent_shipped"] for r in pr if r["present"])
        fblk = sum(r["false_block"] for r in pr if not r["present"])
        print(f"  {p:<17}{surf:>7}/{nc}{incoh:>12}/{nc}{fblk:>10}/{nk}")

    sub = [r for r in rows if r["pipeline"] == "substrate" and not r.get("skipped")]
    res = [r for r in sub if r["resolved"] and r["shipped"]]
    blocked = [r for r in sub if not r["shipped"]]
    print(f"\n  substrate resolved+shipped : {len(res)}/{nc}"
          f"   correctly blocked: {len(blocked)}/{nc}"
          f"   false blocks on controls: {sum(r['false_block'] for r in sub if not r['present'])}/{nk}")
    if res:
        r = res[0]
        print(f"  execution feedback         : {r['task']} ready-slice mass "
              f"{r['mass_before']} -> {r['mass_after']} after a passing run")

    live = [r for r in rows if r["pipeline"].startswith("live:") and not r.get("skipped")]
    if live:
        print(f"\n  LIVE arm ran {len(live)} task(s); "
              f"shipped {sum(r['shipped'] for r in live)}, "
              f"incoherent {sum(r['incoherent_shipped'] for r in live)}, "
              f"false blocks {sum(r['false_block'] for r in live)}")


def main():
    ap = argparse.ArgumentParser(description="substrate vs plain schema agent")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--keep", action="store_true", help="keep generated projects")
    ap.add_argument("--brain", default="none", choices=["none", "openrouter", "ollama"],
                    help="add a live-model arm driven by agent.py")
    ap.add_argument("--live-model", default="nvidia/nemotron-3-ultra-550b-a55b:free",
                    help="model for the live arm (openrouter slug)")
    ap.add_argument("--live-tasks", type=int, default=1,
                    help="how many tasks the live arm runs (default 1)")
    ap.add_argument("--live-max-turns", type=int, default=10)
    ap.add_argument("--live-timeout", type=int, default=300)
    args = ap.parse_args()

    rows = []
    for task in TASKS:
        rows.append(run_plain(task))
        rows.append(run_graph(task))
        rows.append(run_substrate(task))

    if args.brain != "none":
        for task in TASKS[:max(0, args.live_tasks)]:
            rows.append(run_live(task, args.brain, args.live_model,
                                 args.live_max_turns, args.live_timeout))

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("=== BENCHMARK: does deliberation matter? ===\n")
        _table(rows)
        _summary(rows, ["plain", "graph", "substrate"] + (
            [f"live:{args.brain}"] if args.brain != "none" else []))

    if not args.keep:
        for task in TASKS:
            for pre in ("bench_plain_", "bench_graph_"):
                shutil.rmtree(mbp.project_dir(pre + task["name"]), ignore_errors=True)
            for pre in ("bench_sub_", "bench_graph_", "bench_live_"):
                shutil.rmtree(os.path.join(S.PROJECTS, pre + task["name"]), ignore_errors=True)
                shutil.rmtree(os.path.join(S.PROJECTS, pre + task["name"] + "__incarnated"),
                              ignore_errors=True)


if __name__ == "__main__":
    main()
