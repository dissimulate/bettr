import argparse
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("install", Path(__file__).with_name("install.py"))
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)
setup = install.setup


class InstallTests(unittest.TestCase):
    def test_remote_bundle_preserves_settings_and_is_repeatable(self):
        args = argparse.Namespace(agent=["claude"], update=True, hooks=True, remote="devbox")
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            # The settings file is a link into a dotfiles folder: it is written through and keeps its mode.
            dotfile, settings = home / "dotfiles/settings.json", home / ".claude/settings.json"
            dotfile.parent.mkdir()
            settings.parent.mkdir()
            old = {"theme": "dark", "statusLine": {"type": "command", "command": "existing-status-line"},
                   "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "existing-hook"}]}]}}
            dotfile.write_text(json.dumps(old))
            dotfile.chmod(0o644)
            settings.symlink_to(dotfile)
            commands, real_run = [], subprocess.run

            def remote(command, input, **_):
                # Run the bundle as the other machine would, in a temporary home.
                commands.append(command)
                return real_run([sys.executable, "-"], input=input, capture_output=True,
                                env={**os.environ, "HOME": folder}, check=False)
            with patch.object(setup.subprocess, "run", side_effect=remote), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                states = [setup.run("status", "devbox")["state"]]
                for _ in range(2):
                    install.install_remote(args)
                states.append(setup.run("status", "devbox")["state"])
            self.assertEqual(commands[0][1:], ["exec", "--on", "devbox", "-i", "--", "python3", "-"])
            self.assertEqual(states, ["missing", "current"])
            self.assertTrue(settings.is_symlink())
            self.assertEqual(dotfile.stat().st_mode & 0o777, 0o644)
            actual = json.loads(dotfile.read_text())
            self.assertEqual(actual["theme"], "dark")
            self.assertEqual(actual["statusLine"], old["statusLine"])
            self.assertNotIn("subagentStatusLine", actual)
            # The user's own Stop hook is kept; the reporter's is added after it.
            self.assertEqual(actual["hooks"]["Stop"][0], old["hooks"]["Stop"][0])
            for event in ("SessionStart", "UserPromptSubmit", "SessionEnd", "SubagentStart", "SubagentStop", "PostToolUse"):
                self.assertEqual(len(actual["hooks"][event]), 1)
            self.assertTrue((home / ".config/herdr-app/mods/bettr-reporter/providers/claude.py").is_file())
            for event in ("Stop", "StopFailure", "PostToolUseFailure"):
                self.assertEqual(len(actual["hooks"][event]), 1 + (event == "Stop"))
            self.assertTrue(actual["hooks"]["PostToolUse"][0]["hooks"][0]["async"])
            self.assertFalse((home / ".codex/hooks.json").exists())
            self.assertFalse((home / ".config/herdr-app/layouts").exists())
            # Only the first install changed the settings: one backup, with the original bytes.
            backup, = (home / ".local/state/bettr/backups").iterdir()
            saved, target = (backup / "paths.txt").read_text().strip().split("\t")
            self.assertEqual(((backup / saved).read_text(), target), (json.dumps(old), str(dotfile.resolve())))

    def test_local_setup_also_merges_the_usage_hooks(self):
        # The gallery copies only the mod folders: this one command must set up every hook.
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"HOME": folder}), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            home = Path(folder)
            (home / ".claude").mkdir()
            usage = home / setup.USAGE / "hooks"
            usage.mkdir(parents=True)
            for agent in setup.AGENTS:
                (usage / f"{agent}.json").write_bytes((install.ROOT / "mods/bettr-usage/hooks" / f"{agent}.json").read_bytes())
            self.assertEqual(setup.run("install")["agents"], {"claude": "current", "codex": "absent"})
            settings = json.loads((home / ".claude/settings.json").read_text())
            scripts = {hook["command"].split("/mods/")[1].split()[0] for groups in settings["hooks"].values()
                       for group in groups for hook in group["hooks"]}
            self.assertEqual(scripts, {"bettr-reporter/report.py", "bettr-usage/report_usage.py"})
            self.assertEqual(setup.run("status")["state"], "current")
            self.assertFalse((home / ".codex").exists())

    def test_invalid_settings_stop_the_install_unchanged(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"HOME": folder}):
            settings = Path(folder) / ".claude/settings.json"
            settings.parent.mkdir()
            settings.write_text("{not json")
            with self.assertRaises(ValueError):
                setup.run("install")
            self.assertEqual(settings.read_text(), "{not json")
            self.assertFalse((Path(folder) / ".config").exists())

    def test_merge_updates_changed_package_hooks_and_keeps_others(self):
        ours = "python3 -I ~/.config/herdr-app/mods/bettr-reporter/report.py codex"
        existing = {"hooks": {
            "PostToolUse": [
                {"matcher": "^(Agent|spawn_agent)$", "hooks": [{"type": "command", "command": ours, "timeout": 5}]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-hook"},
                                              {"type": "command", "command": ours}]},
                {"hooks": []},
            ],
            "Stop": [{"hooks": [{"type": "command", "command": "user-stop"}]}]}}
        fragment = {"hooks": {"PostToolUse": [{"matcher": "(^|\\.)(Agent|spawn_agent)$",
                                               "hooks": [{"type": "command", "command": ours, "timeout": 5}]}]}}
        merged = setup.merge_hooks(existing, fragment)
        self.assertEqual(merged["hooks"]["PostToolUse"], [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-hook"}]},
            {"hooks": []},
            fragment["hooks"]["PostToolUse"][0],
        ])
        self.assertEqual(merged["hooks"]["Stop"], [{"hooks": [{"type": "command", "command": "user-stop"}]}])
        again = setup.merge_hooks(json.loads(json.dumps(merged)), fragment)
        self.assertEqual(again, merged)
        # Changed options, or an edited interpreter, update our hook in place, after the user's own.
        ours = "python3 -I ~/.config/herdr-app/mods/bettr-reporter/report.py claude"
        edited = "python3.12 -B /home/ann/.config/herdr-app/mods/bettr-reporter/report.py claude"
        existing = {"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": "usage", "async": True},
                                                         {"type": "command", "command": edited, "timeout": 5}]}]}}
        hook = {"type": "command", "command": ours, "timeout": 5, "async": True}
        merged = setup.merge_hooks(existing, {"hooks": {"PostToolUse": [{"hooks": [hook]}]}})
        self.assertEqual(merged["hooks"]["PostToolUse"],
                         [{"hooks": [{"type": "command", "command": "usage", "async": True}, hook]}])


if __name__ == "__main__":
    unittest.main()
