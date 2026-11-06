#!/usr/bin/env python3
"""A stand-in agent for scripts/preview.py: report a status, draw a fixed screen, wait.

Usage: fake_agent.py <screen file or -> <app or -> <status>
The screen file is plain text; `\\e` in it becomes ESC, for colours (`\\e[2m` dim), and
`{rule}` a line across the pane. As in a real TUI, the screen is drawn again when the pane
resizes, a screen taller than the pane loses its top lines, and long lines are cut.
"""
import os
import signal
import sys
from pathlib import Path


def draw(text):
    size = os.get_terminal_size(sys.stdout.fileno())
    lines = text.replace("{rule}", "─" * size.columns).rstrip("\n").split("\n")
    sys.stdout.write("\033[?7l\033[H\033[2J" + "\r\n".join(lines[-size.lines:]))
    sys.stdout.flush()


def main():
    screen, app, status = sys.argv[1:4]
    if app != "-":
        # OSC 7501: Herdr shows the terminal as this agent, with this status.
        sys.stdout.write(f"\033]7501;state={status}:app={app}\007\033[?25l")
        sys.stdout.flush()
    if screen != "-":
        text = Path(screen).read_text().replace("\\e", "\033")
        signal.signal(signal.SIGWINCH, lambda *_: draw(text))
        draw(text)
    while True:
        signal.pause()


if __name__ == "__main__":
    main()
