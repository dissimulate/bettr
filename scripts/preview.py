#!/usr/bin/env python3
"""Open Bettr in its own Herdr window, filled with fixed demo data, for preview.png.

Take the screenshot yourself (Cmd-Shift-4, Space, Option-click the window: it keeps the
window buttons and drops the shadow), then quit the window (Cmd-Q) or press Ctrl-C here.
The window is 16:10, the shape of a card on herdr.dev/gallery. A card crops other shapes.

Edit scripts/preview/demo.json to change what the window shows. The window has its own
app home, HOME and herdr-core, so it never sees or changes your spaces, machines,
caches or agents. Everything is removed when it closes.

Requires a Herdr install (`herdr-app` and `hc` on PATH).
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "scripts/preview/demo.json"
FAKE_AGENT = ROOT / "scripts/preview/fake_agent.py"
# In demo.json, these keys hold seconds before now; labels need Unix seconds.
TIME_KEYS = {"at", "startedAt", "endedAt", "updatedAt", "since"}


def ago(value, now):
    """Change every TIME_KEYS number in `value` from seconds-ago to Unix seconds."""
    if isinstance(value, dict):
        return {key: now - item if key in TIME_KEYS and isinstance(item, (int, float)) else ago(item, now)
                for key, item in value.items()}
    if isinstance(value, list):
        return [ago(item, now) for item in value]
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


def tool(name):
    found = shutil.which(name)
    if not found:
        sys.exit(f"{name} is not on PATH: install Herdr first")
    return os.path.realpath(found)


class Preview:
    def __init__(self, demo, base):
        self.demo, self.base = demo, base
        self.app, self.home = base / "app", base / "home"
        self.herdr_app, self.hc = tool("herdr-app"), tool("hc")
        # A clean environment: no HC_* from the calling terminal, a fake HOME (so no ssh
        # hosts, caches or shell config of yours), and this window's app home.
        self.env = {"PATH": f"{self.home}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(self.home), "SHELL": "/bin/zsh",
                    "TERM": "xterm-256color", "LANG": "en_US.UTF-8", "HERDR_APP_HOME": str(self.app)}
        self.process = None

    def run(self, *argv):
        out = subprocess.run(argv, env=self.env, capture_output=True, text=True)
        if out.returncode:
            sys.exit(f"{' '.join(map(str, argv[:3]))}: {(out.stdout + out.stderr).strip()}")
        return out.stdout

    def do(self, command, **args):
        return json.loads(self.run(self.herdr_app, "do", command, json.dumps(args)) or "{}")

    def prepare(self):
        """The app home (Bettr installed, first-run screens done) and the fake HOME."""
        subprocess.run([sys.executable, "-I", ROOT / "scripts/install.py", "--target", self.app],
                       check=True, capture_output=True)
        window = self.demo["window"]
        version = subprocess.run([self.herdr_app, "--version"], capture_output=True, text=True).stdout.split()[-1]
        write_json(self.app / "settings.json", {"core": self.hc, "telemetry": False, "sounds": {"enabled": False},
                                                "appearance": window.get("appearance", "dark")})
        write_json(self.app / "window.json", {"state": "windowed", "bounds": [40.0, 40.0, window["width"], window["height"]]})
        write_json(self.app / "shared.json", {"layout": "bettr", "frame.welcomed": "finished"})
        write_json(self.app / "update-notes.json", {"last_run": version, "presented": [version]})
        write_json(self.app / "bettr-preview.json", {"system": self.demo["system"]})
        now = time.time()
        for snapshot in self.demo["usage"]:
            windows = [{"label": w["label"], "used": w["used"], "resetsAt": now + w["resetsIn"]} for w in snapshot["windows"]]
            write_json(self.home / f".cache/bettr/usage/{snapshot['agent']}.json",
                       {"agent": snapshot["agent"], "name": snapshot["name"], "updatedAt": now - 60, "windows": windows})
        (self.home / ".zshrc").write_text("PROMPT='%~ %# '\n")
        # Found here, as on a real machine: herdr-core by the demo machines, hc by the mods.
        (self.home / ".local/bin").mkdir(parents=True)
        for name in ("herdr-core", "hc"):
            (self.home / ".local/bin" / name).symlink_to(self.hc)

    def mute_toasts(self, on=True):
        """Herdr's toasts (an agent finished) would cover the panels: in this window, close
        each one at once. Herdr's own mods are installed at start, so this comes after it.
        Off puts Herdr's copy back: at start, Herdr moves an edited copy away with a toast."""
        toast = self.app / "mods/toast/main.js"
        if not on:
            toast.write_text(self.toast)
            return
        self.toast = toast.read_text()
        toast.write_text(
            'import { View, div } from "gpui-kit";\nimport { closeOverlay, props } from "herdr";\n\n'
            "export default class Toast extends View {\n"
            "  init() { closeOverlay(props()?.overlay); }\n"
            "  render() { return div(); }\n}\n")

    def add_machines(self):
        """Each demo machine is a second herdr-core on this computer (its own session),
        reached through `sh -c` instead of ssh: Herdr shows it as a connected remote machine."""
        for name in self.demo.get("machines", []):
            self.run(self.hc, "machine", "add", "--json", "--via", "sh -c", "--name", name, "--session", name)

    def start(self):
        log = open(self.base / "app.log", "a")
        self.process = subprocess.Popen([self.herdr_app], env=self.env, stdout=log, stderr=log, start_new_session=True)
        for _ in range(60):
            if subprocess.run([self.herdr_app, "status"], env=self.env, capture_output=True).returncode == 0:
                return
            time.sleep(0.5)
        sys.exit(f"the preview window did not start; see {self.base / 'app.log'}")

    def argv(self, terminal):
        if "argv" in terminal:
            return terminal["argv"]
        screen = str(DEMO.parent / terminal["screen"]) if "screen" in terminal else "-"
        return [sys.executable, "-I", str(FAKE_AGENT), screen, terminal.get("app", "-"), terminal.get("status", "idle")]

    def labels(self, address, terminal, now):
        labels = terminal.get("labels", {})
        if isinstance(labels, str):
            labels = json.loads((DEMO.parent / labels).read_text())
        if labels:
            self.run(self.hc, "label", address,
                     *(f"{key}={json.dumps(ago(value, now), separators=(',', ':'))}" for key, value in labels.items()))

    def fill(self):
        """Spaces, tabs and panes from demo.json. Keeps the terminal to focus and each
        agent's `since` (seconds in its state) by address."""
        # Whole seconds: the Context panel drops a cache miss or compaction with a fraction.
        now, self.focus, self.since = int(time.time()), None, {}
        for space in self.demo["spaces"]:
            folder = self.home / "code" / space.get("folder", space["name"])
            folder.mkdir(parents=True, exist_ok=True)
            space_id = None
            for tab in space["tabs"]:
                for index, terminal in enumerate(tab["panes"]):
                    if index:
                        made = self.do("pane.split", direction=terminal.get("split", "right"), argv=self.argv(terminal))
                    elif space_id is None:
                        made = self.do("space.new", name=space["name"], folder=str(folder), tab=tab["name"],
                                       argv=self.argv(terminal), machine=space.get("machine", ""))
                        space_id = made["space"]
                    else:
                        made = self.do("tab.new", name=tab["name"], space=space_id, folder=str(folder), argv=self.argv(terminal))
                    self.labels(made["terminal"], terminal, now)
                    if terminal.get("focus"):
                        self.focus = made["terminal"]
                    if "since" in terminal:
                        self.since[made["terminal"]] = (terminal.get("status", "idle"), terminal["since"])

    def stop_window(self):
        if self.process and self.process.poll() is None:
            subprocess.run([self.herdr_app, "do", "app.quit"], env=self.env, capture_output=True)
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def age_agents(self):
        """The sidebar shows how long each agent is in its state, from when bettr-spaces first
        saw it. It reads those times only at start: quit, write them, start again. The
        cores keep the terminals."""
        self.mute_toasts(False)
        self.stop_window()
        now = time.time() * 1000
        changed = {address: {"s": "idle" if status == "done" else status, "at": int(now - seconds * 1000)}
                   for address, (status, seconds) in self.since.items()}
        write_json(self.app / "data/bettr-spaces/store.json", {"changed": json.dumps(changed)})
        self.start()
        self.mute_toasts()

    def arrange(self):
        """Focus the demo's agent and open its side panels."""
        if self.focus:
            self.do("pane.focus", terminal=self.focus)
        # The side panels, about window.panel[i] px each: the first takes the rest, the others a fixed px.
        panels, widths = self.demo.get("panels", []), self.demo["window"]["panel"]
        for index, panel in enumerate(panels):
            self.do("layout.show", id=panel)
            self.do("layout.resize", id=panel, **({"px": widths[index]} if index else {"weight": 1}))
        if panels:
            self.do("layout.show", id="panel")
            self.do("layout.resize", id="panel", px=sum(widths))
        errors = json.loads(self.run(self.herdr_app, "status")).get("errors")
        if errors:
            print("Herdr reports:", json.dumps(errors, indent=2), file=sys.stderr)

    def stop(self):
        self.stop_window()
        # The fake HOME selects this window's own cores.
        for session in [None, *self.demo.get("machines", [])]:
            env = {**self.env, "HC_SESSION": session} if session else self.env
            subprocess.run([self.hc, "server", "stop"], env=env, capture_output=True)


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    demo = json.loads(DEMO.read_text())
    # A short folder: macOS limits a socket path to about 100 characters. Resolved, so
    # panes show `~/code/…` (on macOS /tmp is a link to /private/tmp).
    base = Path(tempfile.mkdtemp(prefix="bettr-", dir="/tmp")).resolve()
    # Clean up on a kill too (a background job ignores Ctrl-C).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
    preview = Preview(demo, base)
    try:
        preview.prepare()
        preview.add_machines()
        preview.start()
        preview.mute_toasts()
        preview.fill()
        preview.age_agents()
        preview.arrange()
        print("Ready: take the screenshot (Cmd-Shift-4, Space, Option-click the window).")
        print("Then quit the window (Cmd-Q) or press Ctrl-C here to clean up.")
        preview.process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        preview.stop()
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
