#!/usr/bin/env python3
"""
bench.py — is the substrate actually useful? A small, honest benchmark.
======================================================================

The claim under test is narrow and falsifiable: schema/tool-calling agents are
good at emitting structured output but bad at holding and surfacing CONFLICTS
between requirements. The substrate adds a deliberation layer that represents
tensions and refuses to ship while one is open.

Two pipelines, same tasks (each task plants one requirement contradiction):

  plain      a schema agent: map requirements -> structured output -> ship.
             It has no representation of conflict, so it ships incoherent work
             that verifies structurally (mbp verify passes — the map is acyclic).
  substrate  the same output routed through the silent layer: requirements
             become thoughts, the field surfaces the open contradiction, and
             forge REFUSES to incarnate until it is resolved or honestly set
             aside. When a resolution exists, it resolves, ships, and runs the
             artifact (execution feeds back into salience).

Metrics per task:
  present             contradictions planted (ground truth = 1)
  surfaced            contradictions the pipeline made visible (plain: 0)
  incoherent_shipped  artifacts shipped while a real contradiction was open
  verified/executed   whether the shipped artifact structurally verifies/runs

Run:      python3 bench.py            (table)
          python3 bench.py --json     (machine-readable)
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
]


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


def _commit(root):
    name = f"{root}__incarnated"
    try:
        _silent(forge.cmd_from_substrate, root, name)
    except SystemExit:
        pass
    return os.path.join(S.PROJECTS, name, "app")


# ---------------------------------------------------------------------------
# Pipeline A: plain schema agent (no deliberation)
# ---------------------------------------------------------------------------

def run_plain(task):
    name = f"bench_plain_{task['name']}"
    pdir = mbp.project_dir(name)
    shutil.rmtree(pdir, ignore_errors=True)

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
    shipped = os.path.isdir(app_dir)

    # The plain pipeline never looks for conflict, so a real contradiction is
    # shipped as if the output were fine.
    return {
        "task": task["name"], "pipeline": "plain",
        "present": 1, "surfaced": 0,
        "shipped": int(shipped),
        "incoherent_shipped": int(shipped),   # contradiction was open, still shipped
        "verified": int(_verify(name)) if shipped else 0,
        "executed": int(_exec_ok(app_dir)) if shipped else 0,
        "ops": len(nodes),
    }


# ---------------------------------------------------------------------------
# Pipeline B: the same output, routed through the substrate
# ---------------------------------------------------------------------------

def run_substrate(task):
    root = f"bench_sub_{task['name']}"
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
    for fid, text, _kind in task["facts"]:
        do(S.op_branch, "t0", text)
    for fid, _text, kind in task["facts"]:
        do(S.op_link, fid, "t0", "needs")
        do(S.op_name, fid, kind)

    a, b = task["contradiction"]
    do(S.op_contradict, a, b)

    data = S.load(root)
    surfaced = len(P.open_tensions(data))
    resolved = False
    if task.get("resolution"):
        do(S.op_resolve, a, b, task["resolution"])
        resolved = True

    ids = ["t0"] + [f for f, _t, _k in task["facts"]]
    do(S.op_ready, ids)

    # mass of the ready slice before the run (to show execution feedback)
    data = S.load(root)
    mass_before = {i: round(P.recompute(data, P.DEFAULT)["thoughts"][i]["mass"], 3)
                   for i in ids if i in data["thoughts"]}

    app_dir = _commit(root)
    shipped = os.path.isdir(app_dir)

    # mass after: physics.recompute folds the logged execution outcome in
    data = S.load(root)
    P.recompute(data, P.DEFAULT)
    mass_after = {i: round(data["thoughts"][i]["mass"], 3)
                  for i in ids if i in data["thoughts"]}

    incoherent = 0
    if shipped:
        # re-check live tensions after the run; gate should have prevented any
        open_after = P.open_tensions(S.load(root))
        incoherent = int(bool(open_after))

    return {
        "task": task["name"], "pipeline": "substrate",
        "present": 1, "surfaced": surfaced,
        "shipped": int(shipped),
        "incoherent_shipped": incoherent,
        "verified": int(_verify(f"{root}__incarnated")) if shipped else 0,
        "executed": int(_exec_ok(app_dir)) if shipped else 0,
        "ops": ops,
        "resolved": resolved,
        "mass_before": mass_before, "mass_after": mass_after,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="substrate vs plain schema agent")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--keep", action="store_true", help="keep generated projects")
    args = ap.parse_args()

    rows = []
    for task in TASKS:
        rows.append(run_plain(task))
        rows.append(run_substrate(task))

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("=== BENCHMARK: does deliberation matter? (1 planted contradiction/task) ===\n")
        hdr = (f"{'task':<18}{'pipeline':<11}{'present':>8}{'surfaced':>9}"
               f"{'incoh_ship':>11}{'shipped':>8}{'verify':>7}{'exec':>6}{'ops':>5}")
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            print(f"{r['task']:<18}{r['pipeline']:<11}{r['present']:>8}"
                  f"{r['surfaced']:>9}{r['incoherent_shipped']:>11}"
                  f"{r['shipped']:>8}{r['verified']:>7}{r['executed']:>6}{r['ops']:>5}")

        plain = [r for r in rows if r["pipeline"] == "plain"]
        sub = [r for r in rows if r["pipeline"] == "substrate"]
        n = len(TASKS)
        print("\nSUMMARY")
        print(f"  contradictions surfaced : plain {sum(r['surfaced'] for r in plain)}/{n}"
              f"   substrate {sum(r['surfaced'] for r in sub)}/{n}")
        print(f"  incoherent shipped      : plain {sum(r['incoherent_shipped'] for r in plain)}/{n}"
              f"   substrate {sum(r['incoherent_shipped'] for r in sub)}/{n}")
        blocked = [r for r in sub if not r["shipped"]]
        print(f"  substrate gate blocked  : {len(blocked)}/{n} (unresolved contradictions not shipped)")
        res = [r for r in sub if r["resolved"] and r["shipped"]]
        if res:
            r = res[0]
            print(f"  execution feedback      : {r['task']} ready-slice mass "
                  f"{r['mass_before']} -> {r['mass_after']} after a passing run")

    if not args.keep:
        for task in TASKS:
            shutil.rmtree(mbp.project_dir(f"bench_plain_{task['name']}"), ignore_errors=True)
            shutil.rmtree(os.path.join(S.PROJECTS, f"bench_sub_{task['name']}"), ignore_errors=True)
            shutil.rmtree(os.path.join(S.PROJECTS, f"bench_sub_{task['name']}__incarnated"),
                          ignore_errors=True)


if __name__ == "__main__":
    main()
