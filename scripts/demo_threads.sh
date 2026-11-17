#!/usr/bin/env bash
# demo_threads.sh — an idea may be incomplete; it may not be SILENTLY incomplete.
# The agent grows thoughts; the gate refuses to let any vanish without a decision.
set -euo pipefail
cd "$(dirname "$0")/.."

B=$'\e[1m'; D=$'\e[2m'; R=$'\e[0m'; CY=$'\e[36m'; RD=$'\e[31m'; GR=$'\e[32m'
IDEA="an app for neighbors to share tools"
ROOT=threads-demo

step() { printf '\n%s%s▸ %s%s\n' "$CY" "$B" "$1" "$R"; sleep 0.3; }
runq() { printf '%s$ %s%s\n' "$D" "$*" "$R"; sleep 0.25; "$@" >/dev/null; }
run()  { printf '%s$ %s%s\n' "$D" "$*" "$R"; sleep 0.3; "$@"; }

rm -rf "projects/$ROOT" "projects/${ROOT}__incarnated"

step "1  an idea arrives — incomplete, as ideas are"
runq python3 substrate.py "$ROOT" seed "$IDEA"
runq python3 substrate.py "$ROOT" branch t0 "how neighbors find each other"
runq python3 substrate.py "$ROOT" branch t0 "how trust is established between strangers"
runq python3 substrate.py "$ROOT" branch t0 "how a tool is tracked while borrowed"
runq python3 substrate.py "$ROOT" link t1 t0 needs
runq python3 substrate.py "$ROOT" link t2 t0 needs
runq python3 substrate.py "$ROOT" link t3 t0 needs
run python3 substrate.py "$ROOT" trail | tail -n 6

step "2  the agent decides t1 and t3 are 'ready' — and quietly forgets t2"
runq python3 substrate.py "$ROOT" ready t0 t1 t3
run python3 forge.py from-substrate "$ROOT" --name "${ROOT}__incarnated"

printf '\n%s  ^ trust-between-strangers would have vanished. the agent never said so.%s\n' "$RD" "$R"

step "3  the agent accounts for it — its own choice: hold it open, or let it go"
runq python3 substrate.py "$ROOT" hold t2 "not designed yet — needs a trust model decision"
runq python3 substrate.py "$ROOT" ready t0 t1 t3

step "4  the idea becomes real — with its openness intact"
run python3 forge.py from-substrate "$ROOT" --name "${ROOT}__incarnated" \
  | grep -E "BECOME FLESH|coverage|silently|app dir" || true

step "5  the artifact carries its own honest accounting"
run cat "projects/${ROOT}__incarnated/app/OPEN_THREADS.md"

rm -rf "projects/$ROOT" "projects/${ROOT}__incarnated"
