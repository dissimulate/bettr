#!/usr/bin/env python3
"""Copy this package into Herdr; merge agent hooks only with --hooks."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("setup", ROOT / "mods/bettr-reporter/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

DEFAULT_TARGET = Path.home() / setup.CONFIG
LAYOUT = "layouts/bettr.json"
THEME = "themes/bettr.json"  # The layout's dark theme.
REPORTER = "bettr-reporter"
USAGE = "bettr-usage"
MODS = (USAGE, "bettr-spaces", "bettr-chrome", "bettr-tabs", REPORTER, "bettr-activity", "bettr-context", "bettr-pane", "bettr-files", "bettr-changes")
GENERATED_PANEL = "mod-panel-"  # The blocks bettr-tabs writes into the installed layout: bettr-tabs/panel-mods.js.


def same_layout(installed, source):
    """Whether two layout files say the same, apart from generated panel blocks and formatting."""
    def strip(node):
        if isinstance(node, dict):
            return {key: [strip(child) for child in value if not str(child.get("id", "")).startswith(GENERATED_PANEL)]
                    if key == "children" else value for key, value in node.items()}
        return node
    try:
        return strip(json.loads(installed)) == strip(json.loads(source))
    except ValueError:
        return False


def mod_files(mod):
    """A mod's files to install, relative to the repository. `setup.SKIP` leaves out tests and docs."""
    return [f"mods/{mod}/{name}" for name in setup.package_files(ROOT / "mods" / mod)]


def install_remote(args):
    """Install the reporter on a machine through its existing Herdr connection."""
    result = setup.run("install", args.remote, hooks=args.hooks, agents=args.agent)
    print(f"{args.remote}: reporter {result['state']}; hooks: "
          + ", ".join(f"{agent} {state}" for agent, state in result["agents"].items()))
    print(f"Backup on {args.remote}: {result['backup']}" if result["backup"] else "No existing files needed a backup.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="back up and replace changed installed files")
    parser.add_argument("--hooks", action="store_true", help="merge the included Claude and Codex hooks")
    parser.add_argument("--reporter-only", action="store_true", help="install only the agent reporter (Activity, Context, subagents) and its hooks")
    parser.add_argument("--agent", choices=setup.AGENTS, action="append", help="which agent hooks to install (default: both)")
    parser.add_argument("--remote", help="install the agent reporter on this Herdr machine, through its connection")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Herdr configuration folder")
    args = parser.parse_args()
    if args.remote:
        if not args.reporter_only or args.target != DEFAULT_TARGET:
            parser.error("--remote requires --reporter-only and the default target")
        install_remote(args)
        return
    if args.hooks and args.target.expanduser().resolve() != DEFAULT_TARGET.resolve():
        parser.error(f"--hooks uses the standard ~/{setup.CONFIG} location")

    writes = []
    target = args.target.expanduser().absolute()
    files = mod_files(REPORTER) if args.reporter_only else [THEME, LAYOUT, *(name for mod in MODS for name in mod_files(mod))]
    for relative in files:
        source, destination = ROOT / relative, args.target.expanduser() / relative
        for path in (destination.absolute(), *destination.absolute().parents):
            if path == target:
                break
            if path.is_symlink():
                parser.error(f"{path} is a link; replace it with an installed copy before updating")
        content = source.read_bytes()
        if destination.exists() and destination.read_bytes() == content:
            continue
        if relative == LAYOUT and destination.exists() and same_layout(destination.read_bytes(), content):
            continue
        if destination.exists() and not args.update:
            parser.error(f"{destination} differs; review it, then use --update for this package's installation")
        writes.append((destination, content))

    if args.hooks:
        # The same merge as setup.py install, from this checkout. An agent that is not used
        # here (no ~/.claude or ~/.codex folder) is skipped.
        mods = (REPORTER,) if args.reporter_only else (REPORTER, USAGE)
        fragments = setup.hook_fragments(*(ROOT / "mods" / mod for mod in mods))
        writes.extend(setup.plan_hooks(fragments, args.agent)[1].values())

    backup = setup.write_all(writes)
    print(f"Backup: {backup}" if backup else "No existing files needed a backup.")
    if not writes:
        print("Already installed; no files changed.")


if __name__ == "__main__":
    main()
