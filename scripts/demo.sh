#!/usr/bin/env bash
# demo.sh — the 60-second story: a conflict that would ship, and the gate that stops it.
# Deterministic; uses the real CLIs. Re-record with: python3 scripts/record_demo.py
set -euo pipefail
cd "$(dirname "$0")/.."

B=$'\e[1m'; D=$'\e[2m'; R=$'\e[0m'
CY=$'\e[36m'; GR=$'\e[32m'; RD=$'\e[31m'
DEMO=gate-demo

step()  { printf '\n%s%s▸ %s%s\n' "$CY" "$B" "$1" "$R"; sleep 0.35; }
say()   { printf '%s%s%s\n' "$D" "$1" "$R"; sleep 0.25; }
cmd()   { printf '%s$ %s%s\n' "$D" "$*" "$R"; sleep 0.3; }
run()   { cmd "$@"; "$@"; }
runq()  { cmd "$@"; "$@" >/dev/null; }

rm -rf "projects/$DEMO" "projects/${DEMO}__incarnated"

printf '%s%s\n' "$B" "silent layer — a deliberation layer and contradiction gate for agents"
printf '%s\n' "$D" "the same tools you saw a moment ago, on a design with a hidden conflict"

step "1  an agent reasons: gamify the tracker, but never shame the user"
runq python3 substrate.py "$DEMO" seed  "a habit tracker that gamifies daily tasks"
runq python3 substrate.py "$DEMO" branch t0 "the one committed act at its center"
runq python3 substrate.py "$DEMO" branch t0 "what it must never become: no shaming"
runq python3 substrate.py "$DEMO" link  t1 t0 needs
runq python3 substrate.py "$DEMO" link  t2 t0 needs
runq python3 substrate.py "$DEMO" name  t1 committed
runq python3 substrate.py "$DEMO" name  t2 musts
runq python3 substrate.py "$DEMO" hold  t2 "guard: never shame the user"
run  python3 substrate.py "$DEMO" contradict t1 t2
say  "              ...i.e. 'streak pressure' and 'never shame' are in tension."

step "2  the field sees the conflict (a first-class object, not a vibe)"
run python3 substrate.py "$DEMO" field

step "3  the agent marks it READY — and the gate refuses to ship it"
runq python3 substrate.py "$DEMO" ready t0 t1 t2
run  python3 forge.py from-substrate "$DEMO" --name "${DEMO}__incarnated"

step "4  resolve it honestly, then commit"
run python3 substrate.py "$DEMO" resolve t1 t2 "the act IS the never — one promise a day is the anti-shame"
printf '%s$ %s%s\n' "$D" "python3 forge.py from-substrate $DEMO --name ${DEMO}__incarnated" "$R"; sleep 0.3
python3 forge.py from-substrate "$DEMO" --name "${DEMO}__incarnated" \
  | grep -E "THE WORD|App incarnated|Success:|execution weight"

step "5  and it is measured, not asserted"
run python3 bench.py

rm -rf "projects/$DEMO" "projects/${DEMO}__incarnated"
say ""
say "clean. no conflict silently shipped."
