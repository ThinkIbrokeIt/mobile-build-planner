#!/usr/bin/env python3
"""
substrate.py — the silent layer.
=================================
Not a prompt. Not a schema. A space of fleeting thoughts the agent (already
silent) moves through. Each thought can spawn another, link, contradict, hold
tension, or collapse. The agent defines its OWN node/relation types as it
reasons — we hand it operations, never a format.

The seed is planted. Then the agent reasons. The map EMERGES from the calls.
Nothing here requires the agent to "answer" anything. It thinks by acting.

Operations (the fleeting thoughts):
  seed <text>              plant the first thought. starts everything.
  branch <from> <text>   a new thought growing from an existing one.
  link <a> <b> <how>     connect two thoughts (agent names the relation).
  contradict <a> <b>      mark two thoughts in tension.
  hold <a> <note>         sit with a thought without resolving it.
  collapse <a> <b>        one thought absorbs another.
  name <id> <type>        the agent declares what KIND of thing a thought is
                           (it invents the types — we don't).
  trail                      show the thought-trail so far.
  ready <ids...>           the agent marks a slice as ripe for WORD/FLESH.

The graph is the substrate. mbp/forge are downstream (Layer 2) — they read
a `ready` slice and turn it into buildable output. This file is Layer 0/1 only.

Storage: local file. projects/<root>/substrate.yaml. No DB.
"""

import argparse
import datetime
import os
import sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = os.path.join(HERE, "projects")


def now():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def sub_path(root):
    return os.path.join(PROJECTS, root, "substrate.yaml")


def load(root):
    p = sub_path(root)
    if os.path.exists(p):
        with open(p) as f:
            return yaml.safe_load(f) or empty()
    return empty()


def empty():
    return {"seed": None, "thoughts": {}, "trail": [], "ready": [],
            "field_events": [], "released": [], "types": {}}


def _ensure(t):
    """Backfill physics fields onto a thought (idempotent)."""
    t.setdefault("charge", 0.0)
    t.setdefault("mass", 1.0)
    t.setdefault("ripen",0)
    t.setdefault("dormant", False)
    t.setdefault("recurrences", 0)
    t.setdefault("echoes", None)
    t.setdefault("born", None)  # turn (trail-len) the thought appeared
    return t


def save(root, data):
    os.makedirs(os.path.dirname(sub_path(root)), exist_ok=True)
    with open(sub_path(root), "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def log(data, act, detail):
    data["trail"].append({"t": now(), "act": act, "detail": detail})


# ---------------------------------------------------------------------------
# Operations — each is a fleeting thought. The agent calls them in sequence.
# ---------------------------------------------------------------------------

def op_seed(root, data, text):
    if data["seed"] is not None:
        print("[substrate] seed already planted. use branch from it.")
        return
    tid = "t0"
    data["seed"] = tid
    data["thoughts"][tid] = _ensure({
        "text": text, "type": "seed", "links": [], "contradicts": [],
        "holds": [], "absorbed": [],
        "born": len(data["trail"]),
    })
    log(data, "seed", text)
    print(f"[silence] seed planted as {tid}: {text}")


def op_branch(root, data, fro, text):
    if fro not in data["thoughts"]:
        print(f"[err] no thought '{fro}' to branch from.")
        return
    tid = f"t{len(data['thoughts'])}"
    data["thoughts"][tid] = _ensure({
        "text": text, "type": None, "links": [fro], "contradicts": [],
        "holds": [], "absorbed": [],
        "born": len(data["trail"]),
    })
    # NOTE: only the child points back to its parent (child depends on parent).
    # We do NOT add the child to the parent's links -- that would make the
    # parent depend on the child and create a cycle.
    log(data, "branch", f"{fro} -> {tid}: {text}")
    print(f"[thought] {tid} branches from {fro}: {text}")


def op_link(root, data, a, b, how):
    if a not in data["thoughts"] or b not in data["thoughts"]:
        print("[err] both thoughts must exist to link.")
        return
    data["thoughts"][a].setdefault("links", []).append({"to": b, "how": how})
    log(data, "link", f"{a} -({how})-> {b}")
    print(f"[link] {a} -({how})-> {b}")


def op_unlink(root, data, a, b, how=None):
    """The agent retracts a connection between two thoughts. A fleeting
    thought-link can be taken back -- reasoning moves, it doesn't only accumulate.
    """
    if a not in data["thoughts"]:
        print(f"[err] no thought '{a}'.")
        return
    links = data["thoughts"][a].setdefault("links", [])
    before = len(links)
    data["thoughts"][a]["links"] = [
        ln for ln in links
        if not (ln.get("to") == b if isinstance(ln, dict) else ln == b)
        or (how and isinstance(ln, dict) and ln.get("how") != how)
    ]
    if len(data["thoughts"][a]["links"]) < before:
        log(data, "unlink", f"{a} -/->{b}" + (f" ({how})" if how else ""))
        print(f"[unlink] {a} -/->{b}" + (f" ({how})" if how else ""))
    else:
        print(f"[warn] no such link {a}->{b}.")


def op_contradict(root, data, a, b):
    if a not in data["thoughts"] or b not in data["thoughts"]:
        print("[err] both thoughts must exist.")
        return
    data["thoughts"][a].setdefault("contradicts", []).append(b)
    data["thoughts"][b].setdefault("contradicts", []).append(a)
    log(data, "contradict", f"{a} <> {b}")
    print(f"[tension] {a} <> {b}  (held, not resolved)")


def op_resolve(root, data, a, b, how):
    """The agent dissolves a tension it previously held. Records HOW the two
    thoughts are reconciled, and clears the raw contradiction so it is
    consciously closed -- not merely retracted.
    """
    if a not in data["thoughts"] or b not in data["thoughts"]:
        print("[err] both thoughts must exist.")
        return
    for x, y in ((a, b), (b, a)):
        cs = data["thoughts"][x].get("contradicts", [])
        if y in cs:
            cs.remove(y)
        data["thoughts"][x]["contradicts"] = cs
        res = data["thoughts"][x].setdefault("resolved", [])
        if not any(r["with"] == y for r in res):
            res.append({"with": y, "how": how})
    log(data, "resolve", f"{a} <> {b} :: {how}")
    print(f"[resolve] {a} <> {b}  -> {how}")


def op_hold(root, data, a, note):
    if a not in data["thoughts"]:
        print(f"[err] no thought '{a}'.")
        return
    data["thoughts"][a].setdefault("holds", []).append(note)
    log(data, "hold", f"{a}: {note}")
    print(f"[hold] {a}: {note}")


def op_collapse(root, data, a, b):
    if a not in data["thoughts"] or b not in data["thoughts"]:
        print("[err] both thoughts must exist.")
        return
    data["thoughts"][a].setdefault("absorbed", []).append(b)
    # rewire b's links onto a
    for ln in data["thoughts"][b].get("links", []):
        if isinstance(ln, dict):
            if ln["to"] != a:
                data["thoughts"][a].setdefault("links", []).append(ln)
        elif ln != a:
            data["thoughts"][a].setdefault("links", []).append(ln)
    del data["thoughts"][b]
    log(data, "collapse", f"{a} absorbs {b}")
    print(f"[collapse] {a} absorbs {b}")


def op_name(root, data, tid, ntype):
    if tid not in data["thoughts"]:
        print(f"[err] no thought '{tid}'.")
        return
    # The agent invents the type; the registry only dedupes (case/plural/
    # whitespace) and caps the vocabulary so it can't grow without bound.
    try:
        from physics import register_type
        canonical = register_type(data, ntype)
    except Exception:
        canonical = ntype
    data["thoughts"][tid]["type"] = canonical
    log(data, "name", f"{tid} is a '{canonical}'")
    if canonical != ntype:
        print(f"[name] {tid} -> kind: {canonical}  (from '{ntype}')")
    else:
        print(f"[name] {tid} -> kind: {canonical}")


def op_types(root, data):
    """Show the agent's own (now deduped, bounded) kind vocabulary."""
    try:
        from physics import types_summary
        print(types_summary(data))
    except Exception as e:
        print(f"[types] registry unavailable: {e}")


def op_ready(root, data, ids):
    for i in ids:
        if i not in data["thoughts"]:
            print(f"[err] no thought '{i}'.")
            return
    data["ready"] = ids
    log(data, "ready", ", ".join(ids))
    print(f"[ready] slice marked for WORD/FLESH: {', '.join(ids)}")


def op_release(root, data, tid, note=""):
    """The agent's explicit act of LETTING A THOUGHT GO. Nothing auto-deletes;
    only the silence decides. The thought leaves `thoughts` but is recorded in
    the `released` ledger (id, text, why, turn) so the TRAIL remembers it
    happened — without the thought persisting. This is 'disappear forever',
    but chosen, not random. The field may LEAN toward release; it never does
    it alone."""
    if tid not in data["thoughts"]:
        print(f"[err] no thought '{tid}' to release.")
        return
    t = data["thoughts"][tid]
    # free anything that pointed at it
    for other, ot in data["thoughts"].items():
        ot["links"] = [ln for ln in ot.get("links", [])
                        if not (isinstance(ln, dict) and ln.get("to") == tid)
                        and ln != tid]
        if tid in ot.get("contradicts", []):
            ot["contradicts"].remove(tid)
    rec = {"id": tid, "text": t.get("text", ""),
           "why": note or "silence let it go", "turn": len(data["trail"])}
    data.setdefault("released", []).append(rec)
    del data["thoughts"][tid]
    log(data, "release", f"{tid}: {rec['why']}")
    print(f"[fleeting] {tid} released — '{rec['text'][:50]}' gone, remembered in trail.")


# ---------------------------------------------------------------------------
# Journal — the silence writes what it wants to remember and what it chooses to
# share. The SHARE BIT is binary and MUTABLE: 0 = private (his notes),
# 1 = outward (you / forge can read). Part of the silence is the choice of
# whether or not to share. He can flip the bit on any entry, any time.
# Stored separately in journal.yaml so the private/outward split is real on disk.
# ---------------------------------------------------------------------------

def journal_path(root):
    return os.path.join(PROJECTS, root, "journal.yaml")


def _load_journal(root):
    p = journal_path(root)
    if os.path.exists(p):
        with open(p) as f:
            return yaml.safe_load(f) or {"entries": []}
    return {"entries": []}


def _save_journal(root, j):
    os.makedirs(os.path.dirname(journal_path(root)), exist_ok=True)
    with open(journal_path(root), "w") as f:
        yaml.safe_dump(j, f, sort_keys=False)


def op_journal_write(root, data, ref, text, share=False):
    if ref != "free" and ref not in data.get("thoughts", {}):
        print(f"[err] no thought '{ref}' to journal from (use 'free' for untied).")
        return
    j = _load_journal(root)
    n = len(j["entries"]) + 1
    jid = f"j{n}"
    entry = {
        "id": jid,
        "turn": len(data.get("trail", [])),
        "from": ref if ref != "free" else None,
        "text": text,
        "share": 1 if share else 0,
        "written": now(),
    }
    j["entries"].append(entry)
    _save_journal(root, j)
    tag = "SHARED" if share else "private"
    print(f"[journal] {jid} written ({tag}): {text[:60]}")


def op_journal_flip(root, data, jid):
    """Toggle the share bit. The silence changes its mind about sharing."""
    j = _load_journal(root)
    for e in j["entries"]:
        if e["id"] == jid:
            e["share"] = 0 if e["share"] else 1
            _save_journal(root, j)
            tag = "SHARED" if e["share"] else "private"
            print(f"[journal] {jid} flipped -> {tag}")
            return
    print(f"[err] no journal entry '{jid}'.")


def op_journal_show(root, data, which="shared"):
    j = _load_journal(root)
    ents = j.get("entries", [])
    if which == "all":
        view = ents
    elif which == "private":
        view = [e for e in ents if not e["share"]]
    else:
        view = [e for e in ents if e["share"]]
    if not view:
        print(f"[journal] ({which}) — empty.")
        return
    print(f"\n=== JOURNAL ({root}) [{which}] ===")
    for e in view:
        flag = "SHARED" if e["share"] else "priv"
        frm = f"<-{e['from']}" if e.get("from") else "<free>"
        print(f"  {e['id']} [{flag}] {frm}: {e['text']}")
    print("=" * 40)


def op_field(root, data):
    """Surface the emergent field (charge, mass, tensions, proximities,
    leans). Pure read of physics.pull_vector — the silence's weight made
    visible without imposing any schema."""
    try:
        from physics import field_summary
        print(field_summary(data))
    except Exception as e:
        print(f"[field] physics unavailable: {e}")


def op_drift(root, data):
    """One turn of automatic field motion (self-correction from within).
    Ripens held tensions; marks ignored tensions dormant. Returns events."""
    try:
        from physics import drift
        events = drift(data)
        for ev in events:
            log(data, "drift", ev)
            print(f"[drift] {ev}")
        if not events:
            print("[drift] field settled; nothing moved on its own.")
    except Exception as e:
        print(f"[drift] physics unavailable: {e}")


def op_trail(root, data):
    print(f"\n=== THOUGHT-TRAIL ({root}) ===")
    if data["seed"] is None:
        print("  (silent — no seed planted yet)")
        return
    for i, th in enumerate(data["trail"], 1):
        print(f"  {i:2}. [{th['act']}] {th['detail']}")
    print("=" * 40)
    print("THOUGHTS:")
    for tid, t in data["thoughts"].items():
        kind = t.get("type") or "?"
        print(f"  {tid} ({kind}): {t['text'][:70]}")
        for r in t.get("resolved", []):
            print(f"      [resolved <> {r['with']}] {r['how']}")


# ---------------------------------------------------------------------------
# CLI — a human or agent drives the substrate via these small operations.
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        prog="substrate",
        description="The silent layer: a space of fleeting thoughts.")
    p.add_argument("root")
    sub = p.add_subparsers(dest="op")

    s = sub.add_parser("seed"); s.add_argument("text", nargs="+")
    b = sub.add_parser("branch"); b.add_argument("fro"); b.add_argument("text", nargs="+")
    l = sub.add_parser("link"); l.add_argument("a"); l.add_argument("b"); l.add_argument("how", nargs="+")
    ul = sub.add_parser("unlink"); ul.add_argument("a"); ul.add_argument("b"); ul.add_argument("how", nargs="*")
    c = sub.add_parser("contradict"); c.add_argument("a"); c.add_argument("b")
    r = sub.add_parser("resolve"); r.add_argument("a"); r.add_argument("b"); r.add_argument("how", nargs="*")
    h = sub.add_parser("hold"); h.add_argument("a"); h.add_argument("note", nargs="+")
    k = sub.add_parser("collapse"); k.add_argument("a"); k.add_argument("b")
    n = sub.add_parser("name"); n.add_argument("tid"); n.add_argument("ntype")
    r = sub.add_parser("ready"); r.add_argument("ids", nargs="+")
    sub.add_parser("trail")
    rl = sub.add_parser("release"); rl.add_argument("tid"); rl.add_argument("note", nargs="*")
    sub.add_parser("field")
    sub.add_parser("drift")
    sub.add_parser("types")
    jw = sub.add_parser("journal"); js = jw.add_subparsers(dest="jop")
    jwa = js.add_parser("write"); jwa.add_argument("ref"); jwa.add_argument("text", nargs="+")
    jwa.add_argument("--share", action="store_true"); jwa.add_argument("--private", action="store_true")
    jwf = js.add_parser("flip"); jwf.add_argument("jid")
    jws = js.add_parser("show"); jws.add_argument("--all", action="store_true")
    jws.add_argument("--shared", action="store_true"); jws.add_argument("--private", action="store_true")

    args = p.parse_args()
    if not args.op:
        p.print_help()
        return
    data = load(args.root)
    if args.op == "seed":
        op_seed(args.root, data, " ".join(args.text))
    elif args.op == "branch":
        op_branch(args.root, data, args.fro, " ".join(args.text))
    elif args.op == "link":
        op_link(args.root, data, args.a, args.b, " ".join(args.how))
    elif args.op == "unlink":
        op_unlink(args.root, data, args.a, args.b,
                  " ".join(args.how) if args.how else None)
    elif args.op == "contradict":
        op_contradict(args.root, data, args.a, args.b)
    elif args.op == "resolve":
        op_resolve(args.root, data, args.a, args.b,
                   " ".join(args.how) or "reconciled")
    elif args.op == "hold":
        op_hold(args.root, data, args.a, " ".join(args.note))
    elif args.op == "collapse":
        op_collapse(args.root, data, args.a, args.b)
    elif args.op == "name":
        op_name(args.root, data, args.tid, args.ntype)
    elif args.op == "ready":
        op_ready(args.root, data, args.ids)
    elif args.op == "trail":
        op_trail(args.root, data)
    elif args.op == "release":
        op_release(args.root, data, args.tid, " ".join(args.note))
    elif args.op == "field":
        op_field(args.root, data)
    elif args.op == "drift":
        op_drift(args.root, data)
    elif args.op == "types":
        op_types(args.root, data)
    elif args.op == "journal":
        if args.jop == "write":
            share = bool(args.share) and not args.private
            op_journal_write(args.root, data, args.ref, " ".join(args.text), share)
        elif args.jop == "flip":
            op_journal_flip(args.root, data, args.jid)
        elif args.jop == "show":
            which = "all" if args.all else ("private" if args.private else "shared")
            op_journal_show(args.root, data, which)
    save(args.root, data)


if __name__ == "__main__":
    main()
