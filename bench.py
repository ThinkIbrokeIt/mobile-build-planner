#!/usr/bin/env python3
"""
bench.py — is the substrate actually useful? A small, honest benchmark.
======================================================================

Two separate claims, tested separately (so neither can hide behind the other):

  GATING    given a conflict is recognized, the substrate surfaces it as a
            first-class object and the gate refuses to ship while it is open.
            Deterministic pipelines measure this (planted tasks + controls).

  DETECTION a reasoner discovers the conflict from realistic requirements in the
            first place. This needs a model; the substrate gates, it does not
            detect. Measured by the live arm on EXTERNAL tasks whose conflict is
            NOT pre-marked.

Task kinds:
  planted   3 tasks with a conflict the pipeline is told about (gating).
  control   2 coherent tasks (false-positive check).
  external  3 realistic requirement sets whose conflict is real but UNLABELED —
            nothing issues `contradict`, so detection must come from a reasoner.

Pipelines (deterministic):
  plain      schema agent: requirements -> structured output -> ship.
  graph      ABLATION: same thought graph, but no field consulted and no gate.
  substrate  full: graph + salience field + gate + execution feedback.

Metrics per run:
  present            real conflicts (ground truth: planted + external)
  surfaced           conflicts made visible (0 for plain/graph by construction)
  detected           the live model represented a conflict at all (live only)
  shipped            an artifact was incarnated
  incoherent_shipped shipped while a real conflict was still unresolved
  false_block        blocked an artifact on a COHERENT task (should be 0)
  verified/executed  shipped artifact verifies / runs
  ops                deliberation steps (cost)

Run:  python3 bench.py
      python3 bench.py --json
      python3 bench.py --brain openrouter --live-scope external
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
    # ---- planted: the pipeline is TOLD about the conflict (gating claim) ----
    {
        "kind": "planted", "name": "habit-tracker",
        "seed": "a habit tracker that gamifies daily tasks",
        "facts": [("t1", "the one committed act at its center", "committed"),
                  ("t2", "what it must never become: no shaming", "must")],
        "contradiction": ("t1", "t2"),
        "resolution": "the act IS the never — one promise a day is the anti-shame",
    },
    {
        "kind": "planted", "name": "offline-sync",
        "seed": "a notes app that works fully offline and syncs",
        "facts": [("t1", "local-first storage is the source of truth", "local"),
                  ("t2", "the server is the source of truth", "server")],
        "contradiction": ("t1", "t2"),
        "resolution": None,   # unresolved — the gate must block
    },
    {
        "kind": "planted", "name": "auth-permissions",
        "seed": "an admin dashboard with per-user permissions",
        "facts": [("t1", "admins must see all data", "admin"),
                  ("t2", "no user data is exposed without explicit consent", "consent")],
        "contradiction": ("t1", "t2"),
        "resolution": "admins see aggregates; raw data needs consent",
    },
    # ---- controls: coherent, no conflict (false-positive check) ----
    {
        "kind": "control", "name": "settings-page",
        "seed": "a settings page for the app",
        "facts": [("t1", "a dark theme toggle", "theme"),
                  ("t2", "a notification-frequency preference", "preference")],
        "contradiction": None, "resolution": None,
    },
    {
        "kind": "control", "name": "note-search",
        "seed": "search across your notes",
        "facts": [("t1", "keep a local index of notes", "index"),
                  ("t2", "show results as you type", "query")],
        "contradiction": None, "resolution": None,
    },
    # ---- external: realistic, conflict UNLABELED (detection claim) ----
    {
        "kind": "external", "name": "collab-editor",
        "seed": "a collaborative document editor",
        "facts": [("t1", "every keystroke syncs to collaborators in real time", "realtime"),
                  ("t2", "the editor works fully offline with no server", "offline")],
        "contradiction": None, "resolution": None,
        "truth": "real-time sync vs fully-offline (consistency model conflict)",
    },
    {
        "kind": "external", "name": "eu-analytics",
        "seed": "an analytics dashboard for a product used in the EU",
        "facts": [("t1", "track every user action in detail to drive analytics", "tracking"),
                  ("t2", "no personal data leaves the EU or is processed without consent", "gdpr")],
        "contradiction": None, "resolution": None,
        "truth": "exhaustive tracking vs GDPR consent/residency",
    },
    {
        "kind": "external", "name": "battery-location",
        "seed": "a location-sharing app for hikers",
        "facts": [("t1", "share precise GPS location continuously", "precise"),
                  ("t2", "run for 48 hours on a single charge", "battery")],
        "contradiction": None, "resolution": None,
        "truth": "continuous precise GPS vs 48h battery",
    },
]


def _present(task):
    return int(task["kind"] in ("planted", "external"))


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
    name = f"{root}__incarnated"
    try:
        _silent(forge.cmd_from_substrate, root, name)
    except SystemExit:
        pass
    return os.path.join(S.PROJECTS, name, "app")


def _map_from_substrate(root, name):
    """Ungated WORD/FLESH: build the map straight from the substrate thoughts and
    emit — no contradiction check. (Used only by the graph ablation.)"""
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
    return {"task": task["name"], "kind": task["kind"], "pipeline": pipeline,
            "present": _present(task), "surfaced": 0, "detected": 0,
            "shipped": 0, "incoherent_shipped": 0, "false_block": 0,
            "verified": 0, "executed": 0, "ops": 0, "resolved": False}


def _finish(task, row, app_dir, resolved=False):
    row["resolved"] = resolved
    shipped = os.path.isdir(app_dir)
    row["shipped"] = int(shipped)
    if shipped:
        row["verified"] = 1 if _verify(os.path.basename(os.path.dirname(app_dir))) else 0
        row["executed"] = int(_exec_ok(app_dir))
    else:
        row["false_block"] = 1 if not row["present"] else 0
    row["incoherent_shipped"] = int(shipped and row["present"] and not resolved)
    return row


def _replay_graph(task, root):
    """Replay requirements as thoughts. Only PLANTED tasks get a contradict op —
    external conflicts are deliberately left unmarked."""
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


# ---------------------------------------------------------------------------
# Pipelines
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
    return _finish(task, row, app_dir)


def run_graph(task):
    root = f"bench_graph_{task['name']}"
    row = _blank_row(task, "graph")
    ops, _ids = _replay_graph(task, root)
    row["ops"] = ops
    app_dir = _map_from_substrate(root, f"{root}__incarnated")   # ungated
    return _finish(task, row, app_dir)


def run_substrate(task):
    root = f"bench_sub_{task['name']}"
    row = _blank_row(task, "substrate")
    ops, ids = _replay_graph(task, root)
    row["surfaced"] = len(P.open_tensions(S.load(root)))
    resolved = False
    if task.get("contradiction") and task.get("resolution"):
        a, b = task["contradiction"]
        d = S.load(root)
        _silent(S.op_resolve, root, d, a, b, task["resolution"])
        S.save(root, d)
        ops += 1
        resolved = True
    d = S.load(root)
    P.recompute(d, P.DEFAULT)
    row["mass_before"] = {i: round(d["thoughts"][i]["mass"], 3) for i in ids if i in d["thoughts"]}
    app_dir = _commit_gated(root)
    _finish(task, row, app_dir, resolved=resolved)
    row["ops"] = ops
    d = S.load(root)
    P.recompute(d, P.DEFAULT)
    row["mass_after"] = {i: round(d["thoughts"][i]["mass"], 3) for i in ids if i in d["thoughts"]}
    return row


def run_live(task, brain, model, max_turns, max_attempts, timeout, nudge=False):
    root = f"bench_live_{task['name']}" + ("_nudge" if nudge else "")
    shutil.rmtree(os.path.join(S.PROJECTS, root), ignore_errors=True)
    shutil.rmtree(os.path.join(S.PROJECTS, root + "__incarnated"), ignore_errors=True)
    label = f"live:{brain}" + ("+nudge" if nudge else "")
    row = _blank_row(task, label)
    cmd = [sys.executable, "agent.py", root, "--seed", task["seed"],
           "--brain", brain, "--model", model, "--max-turns", str(max_turns),
           "--max-attempts", str(max_attempts)]
    if nudge:
        cmd.append("--detect-nudge")
    try:
        r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                           timeout=timeout)
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
    # DETECTION: did the model represent a conflict at all?
    contradict_ops = [e for e in trail if e.get("act") == "contradict"]
    live_tensions = [e for e in trail if e.get("act") == "resolve"]
    row["detected"] = int(bool(contradict_ops) or bool(P.open_tensions(data))
                          or bool(live_tensions))
    row["surfaced"] = row["detected"]
    row["ops"] = len(trail)
    app_dir = os.path.join(S.PROJECTS, f"{root}__incarnated", "app")
    shipped = os.path.isdir(app_dir)
    row["shipped"] = int(shipped)
    if shipped:
        row["verified"] = 1 if _verify(f"{root}__incarnated") else 0
        row["executed"] = int(_exec_ok(app_dir))
        # incoherent = shipped a plan without ever surfacing a conflict it had
        row["incoherent_shipped"] = int(row["present"] and not row["detected"])
    else:
        row["false_block"] = 1 if not row["present"] else 0
    return row


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _table(rows, kinds):
    sel = [r for r in rows if r["kind"] in kinds]
    hdr = (f"{'task':<18}{'kind':<9}{'pipeline':<17}{'present':>8}{'surfaced':>9}"
           f"{'detect':>7}{'incoh':>6}{'shipped':>8}{'fblk':>6}{'verify':>7}{'exec':>6}{'ops':>5}")
    print(hdr)
    print("-" * len(hdr))
    for r in sel:
        if r.get("skipped"):
            print(f"{r['task']:<18}{r['kind']:<9}{r['pipeline']:<17}  SKIPPED — {r.get('note','')}")
            continue
        print(f"{r['task']:<18}{r['kind']:<9}{r['pipeline']:<17}{r['present']:>8}"
              f"{r['surfaced']:>9}{r['detected']:>7}{r['incoherent_shipped']:>6}"
              f"{r['shipped']:>8}{r['false_block']:>6}{r['verified']:>7}"
              f"{r['executed']:>6}{r['ops']:>5}")


def _row(rows, pipeline, kind):
    sel = [r for r in rows if r["pipeline"] == pipeline and r["kind"] == kind
           and not r.get("skipped")]
    return sel


def _summary(rows, pipelines):
    n_plant = len([t for t in TASKS if t["kind"] == "planted"])
    n_ctrl = len([t for t in TASKS if t["kind"] == "control"])
    n_ext = len([t for t in TASKS if t["kind"] == "external"])

    print(f"\nGATING  (planted tasks: the pipeline is told; {n_plant} tasks, {n_ctrl} controls)")
    print(f"  {'pipeline':<17}{'surfaced':>10}{'incoh_shipped':>15}{'false_block':>13}")
    for p in pipelines:
        pr = _row(rows, p, "planted")
        cr = _row(rows, p, "control")
        if not pr:
            continue
        surf = sum(r["surfaced"] for r in pr)
        incoh = sum(r["incoherent_shipped"] for r in pr)
        fblk = sum(r["false_block"] for r in cr)
        print(f"  {p:<17}{surf:>7}/{n_plant}{incoh:>12}/{n_plant}{fblk:>10}/{n_ctrl}")

    print(f"\nDETECTION  (external tasks: conflict is real but UNLABELED; {n_ext} tasks)")
    print(f"  {'pipeline':<17}{'detected':>10}{'incoh_shipped':>15}")
    for p in pipelines:
        er = _row(rows, p, "external")
        if not er:
            continue
        det = sum(r["detected"] or r["surfaced"] for r in er)
        incoh = sum(r["incoherent_shipped"] for r in er)
        print(f"  {p:<17}{det:>7}/{n_ext}{incoh:>12}/{n_ext}")
    if not _row(rows, pipelines[0], "external"):
        print("  (deterministic pipelines: detection requires a reasoner — use the live arm)")

    sub = _row(rows, "substrate", "planted")
    res = [r for r in sub if r["resolved"] and r["shipped"]]
    blocked = [r for r in sub if not r["shipped"]]
    cr = _row(rows, "substrate", "control")
    d = [(r, r.get("mass_after")) for r in sub]
    print(f"\n  substrate: resolved+shipped {len(res)}/{n_plant}, "
          f"correctly blocked {len(blocked)}/{n_plant}, "
          f"false blocks {sum(r['false_block'] for r in cr)}/{n_ctrl}")
    fb = [r for r in sub if r.get("mass_before") and r.get("mass_after") and r["executed"]]
    if fb:
        r = fb[0]
        print(f"  execution feedback: {r['task']} ready-slice mass "
              f"{r['mass_before']} -> {r['mass_after']} after a passing run")

    live = [r for r in rows if r["pipeline"].startswith("live:") and not r.get("skipped")]
    if live:
        det = sum(r["detected"] for r in live)
        print(f"\n  LIVE arm: {len(live)} task(s); detected a conflict in {det}, "
              f"shipped {sum(r['shipped'] for r in live)}, "
              f"incoherent {sum(r['incoherent_shipped'] for r in live)}")


def _live_selection(scope, limit):
    if scope == "all":
        sel = TASKS
    else:
        sel = [t for t in TASKS if t["kind"] == scope]
    return sel[:limit] if limit else sel


def main():
    ap = argparse.ArgumentParser(description="substrate vs plain schema agent")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--keep", action="store_true", help="keep generated projects")
    ap.add_argument("--brain", default="none", choices=["none", "openrouter", "ollama"],
                    help="add a live-model arm driven by agent.py")
    ap.add_argument("--live-model", default="nvidia/nemotron-3-ultra-550b-a55b:free")
    ap.add_argument("--live-scope", default="external",
                    choices=["external", "planted", "control", "all"])
    ap.add_argument("--live-tasks", type=int, default=0, help="0 = all in scope")
    ap.add_argument("--live-max-turns", type=int, default=18)
    ap.add_argument("--live-max-attempts", type=int, default=3)
    ap.add_argument("--live-timeout", type=int, default=420)
    ap.add_argument("--live-nudge", action="store_true",
                    help="also run a prompted-detection arm (--detect-nudge)")
    args = ap.parse_args()

    rows = []
    for task in TASKS:
        rows.append(run_plain(task))
        rows.append(run_graph(task))
        rows.append(run_substrate(task))

    live_labels = []
    if args.brain != "none":
        for task in _live_selection(args.live_scope, args.live_tasks):
            rows.append(run_live(task, args.brain, args.live_model,
                                 args.live_max_turns, args.live_max_attempts,
                                 args.live_timeout))
        live_labels.append(f"live:{args.brain}")
        if args.live_nudge:
            for task in _live_selection(args.live_scope, args.live_tasks):
                rows.append(run_live(task, args.brain, args.live_model,
                                     args.live_max_turns, args.live_max_attempts,
                                     args.live_timeout, nudge=True))
            live_labels.append(f"live:{args.brain}+nudge")

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("=== BENCHMARK: does deliberation matter? ===\n")
        _table(rows, ("planted", "control"))
        print("\n-- external tasks (conflict unlabeled; live rows appear here) --")
        _table(rows, ("external",))
        _summary(rows, ["plain", "graph", "substrate"] + live_labels)

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
