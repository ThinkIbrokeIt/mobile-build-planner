#!/usr/bin/env python3
"""
record_demo.py — record scripts/demo.sh into an asciinema cast (docs/demo.cast).
================================================================================

Dependency-free: runs the demo under a pseudo-terminal, captures the real output
with real timing, and writes an asciinema v2 `.cast` (one JSON header line, then
[time, "o", "text"] events). Playable at asciinema.org or with `asciinema play`.

    python3 scripts/record_demo.py            # -> docs/demo.cast
"""

import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CAST = os.path.join(REPO, "docs", "demo.cast")
COLS, ROWS = 108, 32


def record():
    master, slave = pty.openpty()
    # size the pty so the demo wraps to the width the viewer expects
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))

    env = dict(os.environ, TERM="xterm-256color", LANG="C.UTF-8")
    proc = subprocess.Popen(["bash", os.path.join(HERE, "demo.sh")],
                            stdin=slave, stdout=slave, stderr=slave,
                            env=env, close_fds=True, cwd=REPO)
    os.close(slave)

    events = []
    start = time.time()
    while True:
        r, _, _ = select.select([master], [], [], 0.1)
        if r:
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            events.append([round(time.time() - start, 3), "o",
                           data.decode("utf-8", "replace")])
        elif proc.poll() is not None:
            break
    proc.wait()
    os.close(master)
    return events


def main():
    print("recording scripts/demo.sh ... (this runs the real demo)")
    events = record()
    if not events:
        print("no output captured", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(CAST), exist_ok=True)
    header = {
        "version": 2,
        "width": COLS,
        "height": ROWS,
        "timestamp": int(time.time()),
        "idle_time_limit": 2.0,
        "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"},
        "title": "silent layer — the contradiction gate",
    }
    with open(CAST, "w") as f:
        f.write(json.dumps(header) + "\n")
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    dur = events[-1][0]
    print(f"wrote {CAST}  ({len(events)} events, {dur:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
