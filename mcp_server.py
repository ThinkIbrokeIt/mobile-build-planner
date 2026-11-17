#!/usr/bin/env python3
"""
mcp_server.py — the substrate as MCP tools (the framing, made real).
====================================================================

The README used to say MCP was "an analogy, not an implementation". This is the
implementation: a dependency-free MCP server (JSON-RPC 2.0 over stdio, stdlib
only — same spirit as the rest of the project: pyyaml is the only library) that
exposes the silent layer's operations as tools.

The shape this enables:

    a schema-bound agent (any MCP host: Claude, an IDE, another agent)
        -> drives DELIBERATION through substrate_* tools
        -> reads the salience field / open contradictions (substrate_snapshot)
        -> commits a coherent slice (substrate_commit)
        -> gets real WORD->FLESH output + verification back

So the substrate is not a rival to schema-based agents; it is the deliberation
layer underneath them. Layer 2 (mbp/forge) is the execution layer, exposed here
as substrate_commit.

Transport: MCP stdio — one JSON-RPC message per line on stdin/stdout. stderr is
for logs only. Nothing here imports the `mcp` package.

Configuration:
    MBP_ROOT   which substrate project this session drives (default: "mcp-session")

Run (as an MCP stdio server):
    python3 mcp_server.py

Self-test (no MCP host needed):
    python3 mcp_server.py --selftest
"""

import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import substrate as S          # noqa: E402
import physics as P            # noqa: E402

ROOT = os.environ.get("MBP_ROOT", "mcp-session")
SERVER_INFO = {"name": "mobile-build-planner-substrate", "version": "0.3.0"}
PROTOCOL_VERSION = "2025-06-18"


# ---------------------------------------------------------------------------
# Tool definitions (structured input schemas — this is what a schema-bound
# agent consumes; the substrate never imposes its own schema downward).
# ---------------------------------------------------------------------------

def _obj(props, required):
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


_S = {"type": "string"}
_IDS = {"type": "array", "items": _S}

TOOLS = [
    ("substrate_seed", "Plant the first thought (the one human act).",
     _obj({"text": dict(_S, description="the seed thought")}, ["text"])),
    ("substrate_branch", "Grow a new thought from an existing thought id.",
     _obj({"from": _S, "text": _S}, ["from", "text"])),
    ("substrate_link", "Connect two thoughts; YOU name the relation (how).",
     _obj({"a": _S, "b": _S, "how": _S}, ["a", "b", "how"])),
    ("substrate_unlink", "Retract a connection between two thoughts.",
     _obj({"a": _S, "b": _S, "how": _S}, ["a", "b"])),
    ("substrate_contradict", "Mark two thoughts in tension (unresolved).",
     _obj({"a": _S, "b": _S}, ["a", "b"])),
    ("substrate_resolve", "Dissolve a held tension; say HOW they reconcile.",
     _obj({"a": _S, "b": _S, "how": _S}, ["a", "b"])),
    ("substrate_hold", "Sit with a thought without resolving it (adds mass).",
     _obj({"id": _S, "note": _S}, ["id", "note"])),
    ("substrate_collapse", "One thought absorbs another.",
     _obj({"a": _S, "b": _S}, ["a", "b"])),
    ("substrate_name", "Declare what KIND of thing a thought is (invent types).",
     _obj({"id": _S, "type": _S}, ["id", "type"])),
    ("substrate_ready", "Mark a slice of thoughts as coherent enough for WORD/FLESH.",
     _obj({"ids": _IDS}, ["ids"])),
    ("substrate_release", "Let a thought go (the silence decides; never automatic).",
     _obj({"id": _S, "note": _S}, ["id"])),
    ("substrate_journal_write", "Write what to remember; share=1 makes it outward.",
     _obj({"ref": _S, "text": _S, "share": {"type": "boolean"}}, ["ref", "text"])),
    ("substrate_journal_flip", "Change your mind about sharing a journal entry.",
     _obj({"id": _S}, ["id"])),
    ("substrate_drift", "Advance the field one turn (ripens/dormants tensions).",
     _obj({}, [])),
    ("substrate_trail", "Read the thought-trail so far.", _obj({}, [])),
    ("substrate_field", "Read the salience field (open contradictions, leans).", _obj({}, [])),
    ("substrate_types", "Read the agent's own kind vocabulary (the KIND-FIELD).", _obj({}, [])),
    ("substrate_snapshot", "One-call state: trail + field + kinds + gate + ready.",
     _obj({}, [])),
    ("substrate_commit",
     "Commit the READY slice to WORD/FLESH. Refused while an active contradiction is open.",
     _obj({"name": _S}, [])),
]

TOOLS_BY_NAME = {name: (desc, schema) for name, desc, schema in TOOLS}


# ---------------------------------------------------------------------------
# Bridge to the substrate ops (capture their prints, persist the mutation)
# ---------------------------------------------------------------------------

def _capture(fn, *args, save=True):
    buf = io.StringIO()
    data = S.load(ROOT)
    with contextlib.redirect_stdout(buf):
        fn(ROOT, data, *args)
    if save:
        S.save(ROOT, data)
    return buf.getvalue().strip()


def _snapshot():
    data = S.load(ROOT)
    parts = []
    parts.append(_capture(S.op_trail, save=False))
    parts.append(P.field_summary(data))
    parts.append(P.types_summary(data))
    ready = data.get("ready", [])
    open_t = P.open_tensions(data)
    parts.append("=== GATE ===")
    parts.append(f"  ready: {', '.join(ready) if ready else '(none)'}")
    if open_t:
        parts.append("  BLOCKED: open contradiction — resolve or release it before commit:")
        for t in open_t:
            parts.append(f"    {t['a']} <> {t['b']}  ripen={t['ripen']}")
        parts.append('  (use substrate_commit to try anyway, or substrate_release)')
    else:
        parts.append("  gate open: a coherent ready slice may be committed")
    return "\n".join(parts)


def _commit(name=None):
    name = name or f"{ROOT}__incarnated"
    try:
        import forge
    except Exception as e:  # pragma: no cover
        return f"[err] forge unavailable: {e}", True
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            forge.cmd_from_substrate(ROOT, name)
    except SystemExit:
        pass
    text = buf.getvalue().strip()
    app = os.path.join(S.PROJECTS, name, "app")
    if os.path.isdir(app):
        text += f"\n[artifact] {app}"
    return text, False


def dispatch_tool(name, args):
    """Return (text, is_error)."""
    args = args or {}
    try:
        if name == "substrate_seed":
            return _capture(S.op_seed, _txt(args, "text")), False
        if name == "substrate_branch":
            return _capture(S.op_branch, _txt(args, "from"), _txt(args, "text")), False
        if name == "substrate_link":
            return _capture(S.op_link, _txt(args, "a"), _txt(args, "b"), _txt(args, "how")), False
        if name == "substrate_unlink":
            how = _txt(args, "how") or None
            return _capture(S.op_unlink, _txt(args, "a"), _txt(args, "b"), how), False
        if name == "substrate_contradict":
            return _capture(S.op_contradict, _txt(args, "a"), _txt(args, "b")), False
        if name == "substrate_resolve":
            how = _txt(args, "how") or "reconciled"
            return _capture(S.op_resolve, _txt(args, "a"), _txt(args, "b"), how), False
        if name == "substrate_hold":
            return _capture(S.op_hold, _txt(args, "id"), _txt(args, "note")), False
        if name == "substrate_collapse":
            return _capture(S.op_collapse, _txt(args, "a"), _txt(args, "b")), False
        if name == "substrate_name":
            return _capture(S.op_name, _txt(args, "id"), _txt(args, "type")), False
        if name == "substrate_ready":
            ids = args.get("ids") or []
            if not isinstance(ids, list):
                ids = [ids]
            return _capture(S.op_ready, [str(i) for i in ids]), False
        if name == "substrate_release":
            return _capture(S.op_release, _txt(args, "id"), _txt(args, "note", "")), False
        if name == "substrate_journal_write":
            return _capture(S.op_journal_write, _txt(args, "ref"),
                            _txt(args, "text"), bool(args.get("share"))), False
        if name == "substrate_journal_flip":
            return _capture(S.op_journal_flip, _txt(args, "id")), False
        if name == "substrate_drift":
            return _capture(S.op_drift), False
        if name == "substrate_trail":
            return _capture(S.op_trail, save=False), False
        if name == "substrate_field":
            return _capture(S.op_field, save=False), False
        if name == "substrate_types":
            return _capture(S.op_types, save=False), False
        if name == "substrate_snapshot":
            return _snapshot(), False
        if name == "substrate_commit":
            return _commit(_txt(args, "name") or None)
        return f"[err] unknown tool '{name}'", True
    except SystemExit as e:
        return f"[err] operation exited: {e}", True
    except Exception as e:  # pragma: no cover - defensive
        return f"[err] {type(e).__name__}: {e}", True


def _txt(args, key, default=None):
    v = args.get(key, default)
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return "" if v is None else str(v)


# ---------------------------------------------------------------------------
# JSON-RPC / MCP protocol
# ---------------------------------------------------------------------------

def _result(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle(msg):
    """Handle one JSON-RPC message. Returns a response dict, or None for
    notifications."""
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        # echo the client's requested protocol version when it gives one
        pv = params.get("protocolVersion") or PROTOCOL_VERSION
        return _result(mid, {
            "protocolVersion": pv,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": ("Drive the silent layer: reason with substrate_* "
                             "tools, watch substrate_snapshot for open "
                             "contradictions and salience, then substrate_commit "
                             "the ready slice."),
        })
    if method == "ping":
        return _result(mid, {})
    if method == "tools/list":
        return _result(mid, {"tools": [
            {"name": n, "description": d, "inputSchema": s}
            for (n, d, s) in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        text, is_err = dispatch_tool(name, args)
        return _result(mid, {"content": [{"type": "text", "text": text}],
                             "isError": is_err})
    if method in ("resources/list",):
        return _result(mid, {"resources": []})
    if method in ("prompts/list",):
        return _result(mid, {"prompts": []})
    if method and method.startswith("notifications/"):
        return None
    if mid is None:
        return None
    return _error(mid, -32601, f"method not found: {method}")


def serve():
    sys.stderr.write(f"[mbp-mcp] serving root={ROOT!r} (stdio)\n")
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            sys.stdout.write(json.dumps(_error(None, -32700, f"parse error: {e}")) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


# ---------------------------------------------------------------------------
# Self-test — drives the handlers directly (no MCP host required)
# ---------------------------------------------------------------------------

def selftest():
    global ROOT
    ROOT = "mcp-selftest"
    import shutil
    shutil.rmtree(os.path.join(S.PROJECTS, ROOT), ignore_errors=True)
    shutil.rmtree(os.path.join(S.PROJECTS, ROOT + "__incarnated"), ignore_errors=True)

    print("== initialize ==")
    print(json.dumps(handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                             "params": {"protocolVersion": "2025-06-18"}}),
                     indent=2)[:400])
    print("\n== tools/list ==")
    tl = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    print(f"  {len(tl['result']['tools'])} tools:",
          ", ".join(t["name"] for t in tl["result"]["tools"]))

    print("\n== deliberation (tool calls) ==")
    for name, args in [
        ("substrate_seed", {"text": "build a simple todo app"}),
        ("substrate_branch", {"from": "t0", "text": "the one committed act at its center"}),
        ("substrate_branch", {"from": "t0", "text": "what it must never become"}),
        ("substrate_link", {"a": "t1", "b": "t0", "how": "needs"}),
        ("substrate_link", {"a": "t2", "b": "t0", "how": "needs"}),
        ("substrate_name", {"id": "t1", "type": "Committed"}),
        ("substrate_name", {"id": "t2", "type": "musts"}),
        ("substrate_hold", {"id": "t2", "note": "guard: never shame the user"}),
        ("substrate_contradict", {"a": "t1", "b": "t2"}),
    ]:
        text, _ = dispatch_tool(name, args)
        print(f"  {name}: {text.splitlines()[0] if text else '(ok)'}")

    print("\n== snapshot BEFORE resolve (gate should block) ==")
    print(dispatch_tool("substrate_snapshot", {})[0])

    print("\n== resolve the tension, then commit ==")
    print("  " + dispatch_tool("substrate_resolve",
          {"a": "t1", "b": "t2", "how": "the act IS the never"})[0])
    for name, args in [
        ("substrate_ready", {"ids": ["t0", "t1", "t2"]}),
        ("substrate_commit", {}),
    ]:
        text, err = dispatch_tool(name, args)
        print(f"  {name}:")
        for ln in text.splitlines():
            print(f"     {ln}")
    print("\n== kinds (deduped) ==")
    print(dispatch_tool("substrate_types", {})[0])

    shutil.rmtree(os.path.join(S.PROJECTS, ROOT), ignore_errors=True)
    shutil.rmtree(os.path.join(S.PROJECTS, ROOT + "__incarnated"), ignore_errors=True)
    print("\n[selftest] done")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        serve()
