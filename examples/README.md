# Quickstart: drive the deliberation layer over MCP

This is a worked example. No host required — `python3 mcp_server.py --selftest`
runs the same calls below and prints the results.

## 1. Configure your MCP host

Copy [`mcp-config.json`](mcp-config.json) into your host's config, replacing the
two paths:

- the absolute path to `mcp_server.py`
- a writable `MBP_WORKSPACE` (where `projects/` is created; defaults to the repo)

`MBP_ROOT` names the session (the substrate project the tools operate on).

## 2. The tools

19 tools, each with a JSON input schema: `substrate_seed`, `_branch`, `_link`,
`_unlink`, `_contradict`, `_resolve`, `_hold`, `_collapse`, `_name`, `_ready`,
`_release`, `_journal_write`, `_journal_flip`, `_drift`, `_trail`, `_field`,
`_types`, `_snapshot`, `_commit`.

## 3. A worked conversation

You are a schema-bound agent with a feature to design. You use the substrate to
hold the problem, then commit a coherent slice.

```
substrate_seed     { text: "a habit tracker that gamifies daily tasks" }
substrate_branch   { from: "t0", text: "the one committed act at its center" }
substrate_branch   { from: "t0", text: "what it must never become: no shaming" }
substrate_link     { a: "t1", b: "t0", how: "needs" }
substrate_link     { a: "t2", b: "t0", how: "needs" }
substrate_name     { id: "t1", type: "Committed" }     # -> committed
substrate_name     { id: "t2", type: "musts" }         # -> must (deduped)
substrate_hold     { id: "t2", note: "guard: never shame the user" }
substrate_contradict { a: "t1", b: "t2" }              # gamify/streak pressure vs no shaming
```

Now read the state:

```
substrate_snapshot {}
```

```
=== FIELD (salience; config ...) ===
  OPEN CONTRADICTIONS (unresolved — these block incarnation):
    t1 <> t2  ripen=0  prox=0.0
=== SALIENCE (auditable; weights in SalienceConfig) ===
    t2  1.85  [conflict 1.00  ref 0.00  recency 0.55  prox 1.00  mass 0.30]
    t1  1.65  [conflict 1.00  ref 0.00  recency 0.50  prox 1.00  mass 0.00]
    t0  1.33  [conflict 0.00  ref 1.00  recency 0.46  prox 1.00  mass 0.00]
...
=== GATE ===
  ready: (none)
  BLOCKED: open contradiction — resolve or release it before commit
```

If you call `substrate_commit` now, `forge` **refuses** — no artifact is written.

Resolve it honestly, then commit:

```
substrate_resolve { a: "t1", b: "t2", how: "the act IS the never — one promise a day is the anti-shame" }
substrate_ready   { ids: ["t0", "t1", "t2"] }
substrate_commit  {}
```

```
=== FLESH: incarnating 'my-session__incarnated' -> the app (python) ===
[ok] THE WORD HAS BECOME FLESH.
     App incarnated at: /.../projects/my-session__incarnated/app
=== SANDBOX: testing incarnation ===
  Success: True
  [physics] execution weight: 2.00
```

The commit returns the artifact path, and the run's outcome is written back into
the substrate (`executions` ledger) where it reshapes the field's mass.

## 4. Why not just ask the model to "check for contradictions"?

You can — and it helps. The difference here is that the conflict is **a
first-class object with a gate**: it persists in the substrate, shows up in the
field, blocks incarnation until it is resolved *or honestly set aside* (dormant),
and the artifact traces back to the thoughts that produced it. The
[benchmark](../bench.py) is the evidence.
