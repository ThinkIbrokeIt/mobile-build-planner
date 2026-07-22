#!/usr/bin/env python3
"""
physics.py — the field the silence moves through.
================================================

Layer 0 has operations (substrate.py). But operations alone are a graph editor.
Pre-linguistic thought has WEIGHT: some thoughts pull, some repel, some are
heavy and slow, some are near-collision. This module gives the substrate that
*physics* — without a schema and without hardcoded types.

Nothing here names a thought-type. Every force EMERGES from acts the agent
already performs:

  contradict a b   -> a and b gain opposite charge; a repulsion tether forms
                       (they push apart but are bound — that is tension).
  hold a <note>    -> a gains REST MASS: heavier, resists collapse/move.
  collapse a b     -> b's charge transfers to a; b's mass folds in.
  link a b <how>   -> the `how` string is a RELATION VECTOR. Identical `how`
                       across different pairs creates RESONANCE (attraction:
                       "these relate the same way").
  name a <type>    -> the type string seeds a KIND-FIELD. Later thoughts the
                       agent names with the SAME string feel proximity. The
                       AGENT'S OWN vocabulary becomes gravity — we never name
                       the types, we only let repeated words attract.

PROXIMITY (felt, not semantic): a cheap, embedding-free resonance between
thought texts — shared significant tokens — plus the relation/type resonance
above. This is approximate PULL, the right shape for pre-linguistic thought:
it does not need to be true, only felt.

TENSION DRIFT (self-correction from within): each turn the field applies small
automatic motion. A held tension left unresolved for N turns RIPENS — its mass
grows and it begins to lean the next op toward `resolve`/`collapse`. Two
contradicting thoughts that also sit in high proximity tend to collapse/resolve;
if the agent ignores that lean twice, the tension is auto-marked DORMANT — it
did not resolve, it merely stopped pulling. Honest, not forced.

The loop (agent.py) consults pull_vector() to *suggest* the next op. The
silence proposes; the agent disposes. No schema is ever imposed.

All functions are pure over the substrate dict. Storage stays in substrate.yaml.
"""

import re

STOP = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for",
    "with", "is", "it", "that", "this", "be", "are", "as", "at", "by", "from",
    "what", "which", "who", "how", "why", "when", "should", "must", "never",
    "not", "no", "its", "their", "they", "we", "i", "you", "he", "she",
}


def _tokens(text):
    toks = re.findall(r"[A-Za-z]+", (text or "").lower())
    return {t for t in toks if len(t) > 2 and t not in STOP}


def _ensure(thought):
    """Backfill physics fields onto a thought dict (idempotent)."""
    thought.setdefault("charge", 0.0)      # sign = valence, mag = strength
    thought.setdefault("mass", 1.0)         # rest mass; resists change
    thought.setdefault("ripen", 0)          # turns a tension has been held
    thought.setdefault("dormant", False)    # tension stopped pulling
    return thought


def recompute(data):
    """Recompute emergent physics from the agent's acts. Pure; mutates in place
    for convenience (caller saves). Returns the same data."""
    th = data.setdefault("thoughts", {})
    for t in th.values():
        _ensure(t)

    # --- charge from contradictions (opposite signs, tethered) ---
    for tid, t in th.items():
        for other in t.get("contradicts", []):
            if other in th:
                t["charge"] = -abs(t["charge"]) - 0.5 if t["charge"] >= 0 else t["charge"]
                th[other]["charge"] = abs(th[other]["charge"]) + 0.5 if th[other]["charge"] <= 0 else th[other]["charge"]

    # --- mass from holds (rest mass grows with each held note) ---
    for t in th.values():
        holds = t.get("holds", [])
        if holds:
            t["mass"] = 1.0 + 0.6 * len(holds)

    # --- charge/mass transfer on collapse already handled by substrate;
    #     here we just make sure absorbed charges folded. (substrate deletes
    #     the absorbed node, so nothing to do — its mass was added there.)
    return data


def proximity(a_text, b_text):
    """Felt proximity: shared significant tokens, Jaccard-ish, 0..1."""
    ta, tb = _tokens(a_text), _tokens(b_text)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def relation_resonance(data):
    """Pairs of thoughts sharing the SAME `how` link-string attract.
    Returns dict {(a,b): strength} over unordered pairs."""
    th = data.get("thoughts", {})
    by_how = {}
    for tid, t in th.items():
        for ln in t.get("links", []):
            if isinstance(ln, dict) and ln.get("how"):
                by_how.setdefault(ln["how"], set()).add(tid)
                by_how[ln["how"]].add(ln["to"])
    res = {}
    for how, members in by_how.items():
        ms = list(members)
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                a, b = ms[i], ms[j]
                if a in th and b in th:
                    key = tuple(sorted((a, b)))
                    res[key] = res.get(key, 0.0) + 0.4
    return res


def kind_resonance(data):
    """Thoughts the agent named with the SAME type string attract.
    The agent's own vocabulary becomes gravity. We never name the types."""
    th = data.get("thoughts", {})
    by_type = {}
    for tid, t in th.items():
        ty = t.get("type")
        if ty and ty != "?":
            by_type.setdefault(ty, []).append(tid)
    res = {}
    for ty, members in by_type.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                key = tuple(sorted((members[i], members[j])))
                res[key] = res.get(key, 0.0) + 0.5
    return res


def pull_vector(data):
    """The silence leans. Returns a dict describing forces the next op feels:
      tensions : list of (a, b, ripeness, prox) — contradictions, ranked
      proximities : list of (a, b, strength) — felt closeness (resonance+
                    lexical), ranked
      heavies : list of (id, mass) — thoughts too heavy to collapse easily
      leans : list of suggested ops the field proposes (agent may override)
    """
    recompute(data)
    th = data.get("thoughts", {})

    # tensions
    tensions = []
    seen = set()
    for tid, t in th.items():
        for other in t.get("contradicts", []):
            key = tuple(sorted((tid, other)))
            if key in seen:
                continue
            seen.add(key)
            if other not in th:
                continue
            prox = proximity(t.get("text", ""), th[other].get("text", ""))
            ripen = max(t.get("ripen", 0), th[other].get("ripen", 0))
            dormant = t.get("dormant", False) or th[other].get("dormant", False)
            tensions.append((tid, other, ripen, round(prox, 3), dormant))
    tensions.sort(key=lambda x: (x[4], x[2], x[3]), reverse=True)

    # proximities (resonance + lexical)
    prox = {}
    prox.update(relation_resonance(data))
    prox.update(kind_resonance(data))
    for tid, t in th.items():
        for other, _ in [(o, None) for o in th if o != tid]:
            key = tuple(sorted((tid, other)))
            p = proximity(t.get("text", ""), th[other].get("text", ""))
            if p > 0:
                prox[key] = prox.get(key, 0.0) + p
    proximities = [(a, b, round(s, 3)) for (a, b), s in prox.items() if s > 0.3]
    proximities.sort(key=lambda x: x[2], reverse=True)

    # heavies
    heavies = sorted(
        [(tid, round(t.get("mass", 1.0), 2)) for tid, t in th.items()
         if t.get("mass", 1.0) > 1.4],
        key=lambda x: x[1], reverse=True)

    # leans — what the field proposes the agent might do
    leans = []
    for (a, b, ripen, p, dormant) in tensions:
        if dormant:
            continue
        if ripen >= 2:
            leans.append(f"resolve {a} {b}   (tension ripened — silence leans to close it)")
        elif p > 0.4:
            leans.append(f"collapse {a} {b}   (high proximity + tension — silence leans to fuse)")
    for (a, b, s) in proximities[:3]:
        if not any(b in ln.get("to", "") for ln in th[a].get("links", []) if isinstance(ln, dict)):
            leans.append(f"link {a} {b} resonates   (felt proximity {s})")
    for (tid, m) in heavies[:2]:
        holds = th[tid].get("holds", [])
        if holds:
            # already protected — the lean is satisfied, don't re-hold forever
            continue
        leans.append(f"hold {tid}   (heavy: mass {m} — protect from collapse)")

    # release leans — the field SUGGESTS letting go; it never deletes.
    # Eligible: a thought nothing points at, that holds nothing, contradicts
    # nothing, isn't marked ready, AND has passed a grace window (so a just-
    # born flicker gets a turn to attach before the silence offers to release
    # it). Its own outbound branch-pointer to a parent does NOT count as
    # "attached" — a flicker born from t0 but never linked-back-to is still
    # a flicker.
    ready = set(data.get("ready", []))
    seed = data.get("seed")
    clock = len(data.get("trail", []))
    GRACE = 1
    for tid, t in th.items():
        if tid in ready or tid == seed:
            # the seed is sacred — never lean to release it.
            continue
        born = t.get("born")
        if born is not None and (clock - born) <= GRACE:
            continue  # too young to release — give it a turn to attach
        has_hold = bool(t.get("holds"))
        has_con = bool(t.get("contradicts"))
        # A thought is "attached" (kept alive) if something points AT it, OR
        # it points outward as a dependency (needs/depends-on/fulfills/branch)
        # — a child that needs its parent IS held in the structure.
        DEP_HOWS = ("needs", "depends-on", "fulfills", "branch")
        referenced = any(
            (ln.get("to") == tid if isinstance(ln, dict) else ln == tid)
            for o in th.values() for ln in o.get("links", []))
        outbound_dep = any(
            (ln.get("how") in DEP_HOWS) if isinstance(ln, dict) else False
            for ln in t.get("links", []))
        if not referenced and not outbound_dep and not has_hold and not has_con:
            leans.append(f"release {tid}   (flicker — nothing holds it; let it go)")
        elif t.get("dormant") and not referenced and not outbound_dep and t.get("ripen", 0) >= 3:
            leans.append(f"release {tid}   (long dormant, unreferenced — may release)")

    return {
        "tensions": tensions,
        "proximities": proximities,
        "heavies": heavies,
        "leans": leans,
    }


def echoes_released(data, text):
    """If `text` is proximate to a RELEASED thought, return that ledger entry.
    This is 'returns years later' — the THEME resurfaces, not the thought
    itself. The agent may choose to link the new thought back via `echoes`."""
    rel = data.get("released", [])
    if not rel:
        return None
    best, best_p = None, 0.35
    for r in rel:
        p = proximity(r.get("text", ""), text or "")
        if p > best_p:
            best, best_p = r, p
    return best


def drift(data):
    """Apply one turn of automatic field motion (self-correction from within).
    Ripens held tensions; marks ignored tensions dormant after 3 ripe turns.
    Pure-ish: mutates data, caller saves. Returns list of field events."""
    recompute(data)
    th = data.get("thoughts", {})
    events = []
    seen = set()
    for tid, t in th.items():
        for other in t.get("contradicts", []):
            key = tuple(sorted((tid, other)))
            if key in seen or other not in th:
                continue
            seen.add(key)
            if t.get("dormant") or th[other].get("dormant"):
                continue
            t["ripen"] += 1
            th[other]["ripen"] += 1
            if t["ripen"] >= 3:
                t["dormant"] = True
                th[other]["dormant"] = True
                events.append(f"dormant {tid} <> {other}  (tension stopped pulling; not resolved, set aside)")
    return events


def field_summary(data):
    """Human/agent-readable field state for the loop prompt."""
    pv = pull_vector(data)
    lines = ["=== FIELD (the silence's weight) ==="]
    if pv["tensions"]:
        lines.append("  tensions (contradictions, ranked):")
        for (a, b, ripen, p, dor) in pv["tensions"]:
            tag = "dormant" if dor else f"ripe={ripen}"
            lines.append(f"    {a} <> {b}  prox={p}  {tag}")
    else:
        lines.append("  tensions: none")
    if pv["proximities"]:
        lines.append("  proximities (felt closeness):")
        for (a, b, s) in pv["proximities"][:5]:
            lines.append(f"    {a} ~ {b}  {s}")
    if pv["heavies"]:
        lines.append("  heavies (resist collapse):")
        for (tid, m) in pv["heavies"]:
            lines.append(f"    {tid}  mass={m}")
    if pv["leans"]:
        lines.append("  the silence leans toward:")
        for lean in pv["leans"]:
            lines.append(f"    > {lean}")
    else:
        lines.append("  the silence leans toward: (nothing yet — open space)")
    return "\n".join(lines)
