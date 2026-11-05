#!/usr/bin/env python3
"""Copy Lucide icons into a mod: scripts/lucide.py [--stroke W] <mod> <icon> [<icon> ...].

Icons come from the lucide-static npm package at a fixed version, and go to
mods/<mod>/icons/<icon>.svg. Use them in code as "mods/<mod>/icons/<icon>.svg".
--stroke sets the line width (Lucide draws 2; Herdr's top-row icons use 1.5).
Lucide is ISC licensed; its licence goes in the same folder once.
scripts/install.py installs every file in the mod folder, so the icons need no other step.
"""
import argparse
from pathlib import Path
import re
import urllib.error
import urllib.request

VERSION = "1.59.0"
BASE = f"https://unpkg.com/lucide-static@{VERSION}"
ROOT = Path(__file__).resolve().parents[1]


def fetch(path):
    with urllib.request.urlopen(f"{BASE}/{path}", timeout=20) as response:
        return response.read().decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mod", help="mod folder under mods/")
    parser.add_argument("icons", nargs="+", help="Lucide icon names, e.g. git-compare")
    parser.add_argument("--stroke", type=float, help="stroke width, e.g. 1.5 (default: Lucide's 2)")
    args = parser.parse_args()
    folder = ROOT / "mods" / args.mod
    if not folder.is_dir():
        parser.error(f"{folder} is not a mod folder")
    out = folder / "icons"
    out.mkdir(exist_ok=True)
    licence = out / "LICENSE-Lucide.txt"
    if not licence.exists():
        licence.write_text(fetch("LICENSE"))
    for name in args.icons:
        if not re.fullmatch(r"[a-z0-9-]+", name):
            parser.error(f"{name!r} is not a Lucide icon name")
        try:
            svg = fetch(f"icons/{name}.svg")
        except urllib.error.HTTPError as error:
            parser.error(f"{name}: {error.code} at {BASE}/icons/{name}.svg (not in Lucide {VERSION}?)")
        if "<svg" not in svg:
            parser.error(f"{name}: no SVG at {BASE}/icons/{name}.svg")
        if args.stroke:
            svg = svg.replace('stroke-width="2"', f'stroke-width="{args.stroke:g}"', 1)
        (out / f"{name}.svg").write_text(svg)
        print(f"mods/{args.mod}/icons/{name}.svg")


if __name__ == "__main__":
    main()
