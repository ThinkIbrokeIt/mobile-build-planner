#!/usr/bin/env python3
"""
physics.py — the salience field the silence moves through.
==========================================================

Layer 0 has operations (substrate.py). But operations alone are a graph editor.
Pre-linguistic thought has WEIGHT: some thoughts pull, some repel, some are
heavy and slow, some are near-collision. This module gives the substrate that
*field* — without a schema and without hardcoded thought types.

Nothing here names a thought-type. Every force EMERGES from acts the agent
already performs:

  contradict a b   -> a and b gain opposite charge; a repulsion tether forms
                       (they push apart but are bound — that is tension).
  hold a <note>    -> a gains REST MASS: heavier, resists collapse/move.
  collapse a b     -> b's charge transfers to a; b's mass folds in.
  link a b <how>   -> the `how` string is a RELATION VECTOR. Identical `how`
                       across different pairs creates RESONANCE (attraction).
  name a <type>    -> the type string seeds a KIND-FIELD (see the registry
                       below). The AGENT'S OWN vocabulary becomes gravity.

THE SALIENCE FIELD
------------------
Earlier this file scattered magic numbers (0.3, 0.4, "3 turns", …) through the
logic. Now every tunable lives in one place — SalienceConfig — and the field is
a single, inspectable score per thought, built from named signals:

  conflict   the thought sits in an ACTIVE (non-dormant) contradiction
  reference  how many other thoughts point at it (it is load-bearing)
  recency    how recently it was born (decays with the trail clock)
  proximity  felt closeness to the rest of the field (lexical + relation +
             kind resonance) — the "retrieval relevance" of this moment
  mass       rest mass (held thoughts are heavier and resist change)

  salience(t) = w_conflict*conflict + w_reference*reference
              + w_recency*recency + w_proximity*proximity + w_mass*mass

Each component is normalised to 0..1 first, so the weights are directly
comparable and the score is auditable. salience_report() exposes the
component breakdown; field_summary() prints it. A run is reproducible because
CONFIG_SIGNATURE pins the config.

OPEN CONTRADICTIONS ARE FIRST-CLASS
-----------------------------------
open_tensions() returns the active, unresolved contradictions directly; the
field summary surfaces them; and forge refuses to incarnate a ready slice
while an active tension is still open. Dormant tensions (deliberately set
aside) do NOT block — "honestly not solved" is allowed, silently unsolved is
not.

PROXIMITY (felt, not semantic): a cheap, embedding-free resonance between
thought texts — shared significant tokens — plus the relation/type resonance
above. This is approximate PULL, the right shape for pre-linguistic thought:
it does not need to be true, only felt.

TENSION DRIFT (self-correction from within): each turn the field applies small
automatic motion. A held tension left unresolved ripens; if the agent ignores
it past the dormancy threshold it goes DORMANT — it did not resolve, it merely
stopped pulling. Honest, not forced.

The loop (agent.py) consults pull_vector() to *suggest* the next op. The
silence proposes; the agent disposes. No schema is ever imposed.

All functions are pure over the substrate dict. Storage stays in substrate.yaml.
"""

import re
from dataclasses import asdict, dataclass


# ---------------------------------------------------------------------------
# Configuration — the ONLY place weights and thresholds live.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SalienceConfig:
    """Every tunable weight and threshold, in one loggable object.

    Reshape the field by changing these values; the logic stays the same.
    """
    # --- salience signal weights ---
    w_conflict: float = 1.0
    w_reference: float = 0.7
    w_recency: float = 0.5
    w_proximity: float = 0.4
    w_mass: float = 0.6

    # --- normalisation ---
    ref_saturate: int = 3          # inbound refs at which reference saturates
    recency_halflife: float = 8.0  # turns for recency to halve
    mass_saturate: float = 2.0     # mass above 1.0 that counts as fully heavy

    # --- emergent force constants ---
    contradict_charge: float = 0.5
    hold_mass_per_note: float = 0.6
    relation_resonance: float = 0.4
    kind_resonance: float = 0.5

    # --- execution feedback: how strongly a real run's outcome reshapes mass ---
    execution_mass_gain: float = 0.3   # success multiplier = 1 + (w-1)*gain
    execution_fail_floor: float = 0.1  # mass never drops below this on failure

    # --- thresholds / dynamics ---
    proximity_report: float = 0.3      # pairs above this are "felt"
    proximity_collapse: float = 0.4    # tension + this => lean to fuse
    tension_resolve_ripen: int = 2     # ripened this far => lean to resolve
    tension_dormant_after: int = 3     # ignored this long => dormant (set aside)
    heavy_mass: float = 1.4            # "heavy" thoughts resist collapse
    release_grace: int = 1             # turns a fresh flicker gets to attach
    release_dormant_ripen: int = 3     # dormant + unreferenced at this ripen => release lean

    # --- type registry (bounded, mergeable vocabulary) ---
    type_cap: int = 32
    type_merge_similarity: float = 0.8


DEFAULT = SalienceConfig()

# stable, human-readable fingerprint of the active config (for logs)
CONFIG_SIGNATURE = ";".join(f"{k}={v}" for k, v in sorted(asdict(DEFAULT).items()))

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


# ---------------------------------------------------------------------------
# Type registry — bounded, mergeable. The agent still invents types; we only
# dedupe (case/plural/whitespace) and cap the vocabulary so it cannot become
# unbounded string soup. The canonical type is what feeds kind_resonance.
# ---------------------------------------------------------------------------

def normalize_type(s):
    """Canonicalise an agent-authored type string."""
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").strip().lower())
    words = s.split()
    if words:
        w = words[-1]
        # naive singularisation (should -> should, mechanisms -> mechanism)
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            words[-1] = w[:-1]
    return " ".join(words)


def _type_tokens(s):
    """Alphanumeric tokens for type names (keeps digits, so 'kind0' != 'kind1'
    even though prose tokenisation would strip those digits)."""
    return set(re.findall(r"[a-z0-9]+", s or ""))


def type_similarity(a, b):
    ta, tb = _type_tokens(a), _type_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def register_type(data, raw, cfg=DEFAULT):
    """Return the canonical kind for `raw`, recording it in data['types'].

    Merges near-duplicates (token overlap >= cfg.type_merge_similarity) and, at
    the vocabulary cap, folds new strings into the most similar existing kind
    (falling back to 'misc') instead of growing without bound.
    """
    reg = data.setdefault("types", {})
    n = normalize_type(raw) or "unspecified"

    if n in reg:
        reg[n]["count"] = reg[n].get("count", 0) + 1
        return n

    best, best_sim = None, 0.0
    for canon in reg:
        sim = type_similarity(n, canon)
        if sim > best_sim:
            best, best_sim = canon, sim

    if best and best_sim >= cfg.type_merge_similarity:
        reg[best].setdefault("aliases", []).append(raw)
        reg[best]["count"] = reg[best].get("count", 0) + 1
        return best

    if len(reg) >= cfg.type_cap:
        if best:
            reg[best].setdefault("aliases", []).append(raw)
            reg[best]["count"] = reg[best].get("count", 0) + 1
            return best
        return "misc"

    reg[n] = {"count": 1, "aliases": [], "first_seen": len(data.get("trail", []))}
    return n


def types_summary(data):
    """Human-readable registry (the agent's own, now-deduped vocabulary)."""
    reg = data.get("types", {})
    if not reg:
        return "[types] (none named yet)"
    lines = [f"=== KIND-FIELD ({len(reg)} kinds) ==="]
    for t, meta in sorted(reg.items(), key=lambda kv: -kv[1].get("count", 0)):
        aliases = meta.get("aliases") or []
        extra = f"  aliases: {', '.join(aliases)}" if aliases else ""
        lines.append(f"  {t}  x{meta.get('count', 0)}{extra}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Emergent forces (pure functions of the acts the agent performed)
# ---------------------------------------------------------------------------

def recompute(data, cfg=DEFAULT):
    """Recompute emergent physics from the agent's acts. Pure; mutates in place
    for convenience (caller saves). Returns the same data."""
    th = data.setdefault("thoughts", {})
    for t in th.values():
        _ensure(t)

    # --- charge from contradictions (opposite signs, tethered) ---
    for tid, t in th.items():
        for other in t.get("contradicts", []):
            if other in th:
                t["charge"] = (-abs(t["charge"]) - cfg.contradict_charge
                               if t["charge"] >= 0 else t["charge"])
                th[other]["charge"] = (abs(th[other]["charge"]) + cfg.contradict_charge
                                       if th[other]["charge"] <= 0 else th[other]["charge"])

    # --- mass from holds (rest mass grows with each held note) ---
    for t in th.values():
        holds = t.get("holds", [])
        if holds:
            t["mass"] = 1.0 + cfg.hold_mass_per_note * len(holds)

    # --- execution feedback: a real run's outcome reshapes the shipped slice ---
    # Prefer the executions ledger (most recent entry); fall back to the legacy
    # scalar. Success reinforces mass (the silence validated); failure weakens it
    # (the agent should reconsider).
    exec_weight = None
    entries = data.get("executions")
    if entries:
        exec_weight = entries[-1].get("weight")
    if exec_weight is None:
        exec_weight = data.get("execution_weight")
    if exec_weight is not None:
        for tid in data.get("ready", []):
            if tid in th:
                if exec_weight >= 1.0:
                    th[tid]["mass"] *= (1.0 + (exec_weight - 1.0) * cfg.execution_mass_gain)
                else:
                    th[tid]["mass"] *= max(cfg.execution_fail_floor, exec_weight)

    return data


def record_execution(data, weight, success=None, duration=None, errors=None, turn=None):
    """Log a real execution outcome into the substrate (the self-training loop).

    Appends to data['executions'] and mirrors the legacy scalar fields so older
    readers still work. Returns the recorded entry.
    """
    entry = {
        "turn": turn if turn is not None else len(data.get("trail", [])),
        "weight": round(float(weight), 3),
        "success": bool(success) if success is not None else (weight >= 1.0),
        "duration": duration,
        "errors": list(errors or []),
    }
    data.setdefault("executions", []).append(entry)
    data["execution_weight"] = entry["weight"]
    if entry["success"]:
        data["execution_success"] = True
        data.pop("execution_failed", None)
    else:
        data["execution_failed"] = True
    return entry


def proximity(a_text, b_text):
    """Felt proximity: shared significant tokens, Jaccard-ish, 0..1."""
    ta, tb = _tokens(a_text), _tokens(b_text)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def relation_resonance(data, cfg=DEFAULT):
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
                    res[key] = res.get(key, 0.0) + cfg.relation_resonance
    return res


def kind_resonance(data, cfg=DEFAULT):
    """Thoughts the agent named with the SAME (canonical) type attract."""
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
                res[key] = res.get(key, 0.0) + cfg.kind_resonance
    return res


# ---------------------------------------------------------------------------
# Open contradictions (first-class)
# ---------------------------------------------------------------------------

def active_conflict_ids(data):
    """Set of thought ids that sit in an ACTIVE (non-dormant) contradiction."""
    th = data.get("thoughts", {})
    out = set()
    for tid, t in th.items():
        for o in t.get("contradicts", []):
            if o in th and not (t.get("dormant") or th[o].get("dormant")):
                out.add(tid)
                out.add(o)
    return out


def open_tensions(data, cfg=DEFAULT):
    """All ACTIVE (unresolved, non-dormant) contradictions, ranked.

    Returns a list of dicts: {a, b, ripen, prox}. Dormant tensions are excluded
    on purpose — they were set aside honestly and no longer block.
    """
    recompute(data, cfg)
    th = data.get("thoughts", {})
    seen = set()
    out = []
    for tid, t in th.items():
        for other in t.get("contradicts", []):
            if other not in th:
                continue
            key = tuple(sorted((tid, other)))
            if key in seen:
                continue
            seen.add(key)
            if t.get("dormant") or th[other].get("dormant"):
                continue
            out.append({
                "a": tid, "b": other,
                "ripen": max(t.get("ripen", 0), th[other].get("ripen", 0)),
                "prox": round(proximity(t.get("text", ""), th[other].get("text", "")), 3),
            })
    out.sort(key=lambda x: (x["ripen"], x["prox"]), reverse=True)
    return out


# ---------------------------------------------------------------------------
# Salience — the single, auditable score per thought
# ---------------------------------------------------------------------------

def _inbound_counts(data):
    th = data.get("thoughts", {})
    counts = {tid: 0 for tid in th}
    for t in th.values():
        for ln in t.get("links", []):
            to = ln.get("to") if isinstance(ln, dict) else ln
            if to in counts:
                counts[to] += 1
    return counts


def _pairwise_proximity(data, cfg):
    prox = {}
    prox.update(relation_resonance(data, cfg))
    prox.update(kind_resonance(data, cfg))
    th = data.get("thoughts", {})
    ids = list(th.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            p = proximity(th[a].get("text", ""), th[b].get("text", ""))
            if p > 0:
                key = tuple(sorted((a, b)))
                prox[key] = prox.get(key, 0.0) + p
    return prox


def salience_components(data, cfg=DEFAULT):
    """Per-thought salience with a full component breakdown (0..1 each).

    Returns {id: {"score": float, "conflict": .., "reference": ..,
                  "recency": .., "proximity": .., "mass": ..}}.
    """
    recompute(data, cfg)
    th = data.get("thoughts", {})
    if not th:
        return {}
    clock = len(data.get("trail", []))
    inbound = _inbound_counts(data)
    conflicts = active_conflict_ids(data)

    prox = _pairwise_proximity(data, cfg)
    prox_sum = {tid: 0.0 for tid in th}
    for (a, b), s in prox.items():
        prox_sum[a] = prox_sum.get(a, 0.0) + s
        prox_sum[b] = prox_sum.get(b, 0.0) + s
    prox_max = max(prox_sum.values()) if prox_sum else 0.0

    out = {}
    for tid, t in th.items():
        born = t.get("born")
        dt = 0 if born is None else max(0, clock - born)
        recency = 0.5 ** (dt / cfg.recency_halflife) if cfg.recency_halflife else 1.0
        reference = min(1.0, inbound.get(tid, 0) / max(1, cfg.ref_saturate))
        prx = (prox_sum.get(tid, 0.0) / prox_max) if prox_max else 0.0
        mass = min(1.0, max(0.0, (t.get("mass", 1.0) - 1.0) / cfg.mass_saturate))
        conflict = 1.0 if tid in conflicts else 0.0

        score = (cfg.w_conflict * conflict + cfg.w_reference * reference
                 + cfg.w_recency * recency + cfg.w_proximity * prx
                 + cfg.w_mass * mass)
        out[tid] = {
            "score": round(score, 4),
            "conflict": round(conflict, 3),
            "reference": round(reference, 3),
            "recency": round(recency, 3),
            "proximity": round(prx, 3),
            "mass": round(mass, 3),
        }
    return out


def salience(data, cfg=DEFAULT):
    """Just the score per thought: {id: float}."""
    return {tid: c["score"] for tid, c in salience_components(data, cfg).items()}


def salience_report(data, cfg=DEFAULT, top=5):
    """Auditable, ranked breakdown for logs and prompts."""
    comp = salience_components(data, cfg)
    if not comp:
        return "=== SALIENCE (no thoughts) ==="
    ranked = sorted(comp.items(), key=lambda kv: kv[1]["score"], reverse=True)
    lines = ["=== SALIENCE (auditable; weights in SalienceConfig) ==="]
    for tid, c in ranked[:top]:
        lines.append(
            f"  {tid:>4}  {c['score']:.2f}  "
            f"[conflict {c['conflict']:.2f}  ref {c['reference']:.2f}  "
            f"recency {c['recency']:.2f}  prox {c['proximity']:.2f}  "
            f"mass {c['mass']:.2f}]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pull vector — what the silence leans toward (agent may override)
# ---------------------------------------------------------------------------

def pull_vector(data, cfg=DEFAULT):
    """The silence leans. Returns a dict describing forces the next op feels:
      tensions : list of (a, b, ripen, prox, dormant) — contradictions, ranked
      open_tensions : list of active {a,b,ripen,prox} (first-class)
      proximities : list of (a, b, strength) — felt closeness, ranked
      heavies : list of (id, mass) — thoughts too heavy to collapse easily
      salience : {id: score}
      leans : list of suggested ops the field proposes (agent may override)
    """
    recompute(data, cfg)
    th = data.get("thoughts", {})

    # tensions (all, including dormant, for reporting)
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
    prox = _pairwise_proximity(data, cfg)
    proximities = [(a, b, round(s, 3)) for (a, b), s in prox.items()
                   if s >= cfg.proximity_report]
    proximities.sort(key=lambda x: x[2], reverse=True)

    # heavies
    heavies = sorted(
        [(tid, round(t.get("mass", 1.0), 2)) for tid, t in th.items()
         if t.get("mass", 1.0) > cfg.heavy_mass],
        key=lambda x: x[1], reverse=True)

    sal = salience(data, cfg)

    def _sal(ids):
        return max((sal.get(i, 0.0) for i in ids), default=0.0)

    # leans — what the field proposes the agent might do. Within each tier,
    # order by salience so the silence leans, first, on what matters most.
    active = open_tensions(data, cfg)
    tension_leans = []
    for tn in active:
        a, b, ripen, p = tn["a"], tn["b"], tn["ripen"], tn["prox"]
        if ripen >= cfg.tension_resolve_ripen:
            tension_leans.append(
                (f"resolve {a} {b}   (tension ripened — silence leans to close it)", _sal((a, b))))
        elif p > cfg.proximity_collapse:
            tension_leans.append(
                (f"collapse {a} {b}   (high proximity + tension — silence leans to fuse)", _sal((a, b))))
    tension_leans.sort(key=lambda x: x[1], reverse=True)

    prox_leans = []
    for (a, b, s) in proximities[:3]:
        already = any(b in ln.get("to", "") for ln in th[a].get("links", [])
                      if isinstance(ln, dict))
        if not already:
            prox_leans.append(
                (f"link {a} {b} resonates   (felt proximity {s})", _sal((a, b))))
    prox_leans.sort(key=lambda x: x[1], reverse=True)

    heavy_leans = []
    for (tid, m) in heavies[:2]:
        if th[tid].get("holds"):
            continue  # already protected — the lean is satisfied
        heavy_leans.append(
            (f"hold {tid}   (heavy: mass {m} — protect from collapse)", _sal((tid,))))

    release_leans = []
    ready = set(data.get("ready", []))
    seed = data.get("seed")
    clock = len(data.get("trail", []))
    DEP_HOWS = ("needs", "depends-on", "fulfills", "branch")
    for tid, t in th.items():
        if tid in ready or tid == seed:
            continue  # the seed is sacred — never lean to release it.
        born = t.get("born")
        if born is not None and (clock - born) <= cfg.release_grace:
            continue
        has_hold = bool(t.get("holds"))
        has_con = bool(t.get("contradicts"))
        referenced = any(
            (ln.get("to") == tid if isinstance(ln, dict) else ln == tid)
            for o in th.values() for ln in o.get("links", []))
        outbound_dep = any(
            (ln.get("how") in DEP_HOWS) if isinstance(ln, dict) else False
            for ln in t.get("links", []))
        if not referenced and not outbound_dep and not has_hold and not has_con:
            release_leans.append(
                (f"release {tid}   (flicker — nothing holds it; let it go)", _sal((tid,))))
        elif (t.get("dormant") and not referenced and not outbound_dep
              and t.get("ripen", 0) >= cfg.release_dormant_ripen):
            release_leans.append(
                (f"release {tid}   (long dormant, unreferenced — may release)", _sal((tid,))))
    release_leans.sort(key=lambda x: x[1], reverse=True)

    leans = [x[0] for x in (tension_leans + prox_leans + heavy_leans + release_leans)]

    return {
        "tensions": tensions,
        "open_tensions": active,
        "proximities": proximities,
        "heavies": heavies,
        "salience": sal,
        "leans": leans,
    }


# ---------------------------------------------------------------------------
# Echo / release memory
# ---------------------------------------------------------------------------

def echoes_released(data, text):
    """If `text` is proximate to a RELEASED thought, return that ledger entry.
    This is 'returns years later' — the THEME resurfaces, not the thought
    itself."""
    rel = data.get("released", [])
    if not rel:
        return None
    best, best_p = None, 0.35
    for r in rel:
        p = proximity(r.get("text", ""), text or "")
        if p > best_p:
            best, best_p = r, p
    return best


# ---------------------------------------------------------------------------
# Drift — self-correction from within
# ---------------------------------------------------------------------------

def drift(data, cfg=DEFAULT):
    """Apply one turn of automatic field motion. Ripens held tensions; marks
    ignored tensions dormant after cfg.tension_dormant_after ripe turns.
    Mutates data, caller saves. Returns list of field events."""
    recompute(data, cfg)
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
            if t["ripen"] >= cfg.tension_dormant_after:
                t["dormant"] = True
                th[other]["dormant"] = True
                events.append(
                    f"dormant {tid} <> {other}  (tension stopped pulling; not resolved, set aside)")
    return events


# ---------------------------------------------------------------------------
# Human/agent-readable field state
# ---------------------------------------------------------------------------

def field_summary(data, cfg=DEFAULT):
    """Field state for the loop prompt / CLI. Surfaces OPEN CONTRADICTIONS and
    the auditable salience ladder, then the leans."""
    pv = pull_vector(data, cfg)
    lines = [f"=== FIELD (salience; config {CONFIG_SIGNATURE[:48]}…) ==="]

    # last real execution outcome (the self-training signal)
    ex = data.get("executions") or []
    if ex:
        e = ex[-1]
        lines.append(f"  last execution: weight={e['weight']} success={e['success']} "
                     f"(turn {e['turn']}) — mass reshaped via execution_mass_gain")

    # contradictions — first-class
    active = pv["open_tensions"]
    if active:
        lines.append("  OPEN CONTRADICTIONS (unresolved — these block incarnation):")
        for tn in active:
            lines.append(f"    {tn['a']} <> {tn['b']}  ripen={tn['ripen']}  prox={tn['prox']}")
    else:
        lines.append("  open contradictions: none")
    dormant = [t for t in pv["tensions"] if t[4]]
    if dormant:
        lines.append("  dormant (set aside, honest):")
        for (a, b, ripen, p, _) in dormant:
            lines.append(f"    {a} <> {b}  prox={p}")

    lines.append(salience_report(data, cfg, top=5))

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


if __name__ == "__main__":
    # `python3 physics.py` prints the active config (loggable/reproducible).
    print("SalienceConfig (active defaults):")
    for k, v in sorted(asdict(DEFAULT).items()):
        print(f"  {k} = {v}")
    print(f"\nsignature:\n  {CONFIG_SIGNATURE}")
