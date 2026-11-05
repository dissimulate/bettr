#!/usr/bin/env python3
"""A stand-in agent for scripts/preview.py: report a status, print a fixed screen, wait.

Usage: fake_agent.py <screen file or -> <app or -> <status>
The screen file is plain text; `\\e` in it becomes ESC, for colours (`\\e[2m` dim).
"""
import sys
import time
from pathlib import Path


def main():
    screen, app, status = sys.argv[1:4]
    if app != "-":
        # OSC 7501: Herdr shows the terminal as this agent, with this status.
        sys.stdout.write(f"\033]7501;state={status}:app={app}\007\033[?25l")
    if screen != "-":
        sys.stdout.write(Path(screen).read_text().replace("\\e", "\033"))
    sys.stdout.flush()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
