"""Regression checks; integration tests never use the default tmux socket."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import tmux_ai
from tmux_parking import parking_name


def load_script(name):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / "bin" / name))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SessionTests(unittest.TestCase):
    def test_parking_names_are_distinct_and_safe(self):
        self.assertNotEqual(parking_name("a b"), parking_name("a-b"))
        self.assertEqual(bytes.fromhex(parking_name("demo")[10:]).decode(), "demo")

    def test_title_match_requires_unique_identity(self):
        self.assertEqual(tmux_ai.title_match([("one", ["A task"])], "A task"), "one")
        self.assertIsNone(tmux_ai.title_match(
            [("one", ["A task"]), ("two", ["A task"])], "A task"))
        self.assertIsNone(tmux_ai.title_match([("one", ["A task"])], ""))

    def test_only_explicit_long_truncations_match(self):
        rows = [("one", ["Investigate the example service"])]
        self.assertEqual(tmux_ai.title_match(rows, "Investigate the example…"), "one")
        self.assertIsNone(tmux_ai.title_match(rows, "Investigate the example"))
        self.assertIsNone(tmux_ai.title_match(rows, "Inv…"))

    def test_resume_arguments_are_shell_quoted(self):
        module = load_script("tmux-load")
        sid = "id; echo should-not-run"
        command = module.resume_command({"tool": "opencode", "ai_session": sid})
        self.assertEqual(shlex.split(command), ["opencode", "--session", sid])
        self.assertIsNone(module.resume_command({"tool": "shell"}))

    def test_proc_argument_lookup(self):
        with patch.object(tmux_ai, "proc_args", return_value=["opencode", "--session=ses_demo"]):
            self.assertEqual(tmux_ai.session_arg(1, ("--session",), r"ses_\w+"), "ses_demo")


@unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmux-workspace-test-")
        self.home = Path(self.temp.name)
        self.socket = "workspace-test-" + uuid.uuid4().hex
        self.binary = shutil.which("tmux")
        self.env = dict(os.environ, HOME=str(self.home))
        for key in ("TMUX", "TMUX_PANE"):
            self.env.pop(key, None)
        wrapper_dir = self.home / "test-bin"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "tmux"
        wrapper.write_text(
            "#!/bin/sh\nexec " + shlex.quote(self.binary) + " -L " + self.socket
            + " -f /dev/null \"$@\"\n"
        )
        wrapper.chmod(0o755)
        # Do not notify the real desktop while testing attention events.
        for name in ("notify-send", "canberra-gtk-play"):
            stub = wrapper_dir / name
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
        self.env["PATH"] = str(wrapper_dir) + os.pathsep + self.env["PATH"]
        self.tmux("new-session", "-d", "-s", "demo", "-n", "main", "-c", str(self.home))
        self.tmux("set-option", "-g", "default-shell", "/bin/sh")
        self.tmux("set-option", "-g", "default-command", "/bin/sh")

    def tearDown(self):
        subprocess.run([self.binary, "-L", self.socket, "kill-server"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.temp.cleanup()

    def run_command(self, args, **kwargs):
        return subprocess.run(args, env=self.env, capture_output=True, text=True,
                              check=True, **kwargs).stdout.strip()

    def tmux(self, *args):
        return self.run_command(["tmux", *args])

    def script(self, name, *args):
        return self.run_command([sys.executable, str(ROOT / "bin" / name), *args])

    def test_park_and_unpark_last_window(self):
        wid = self.tmux("display-message", "-p", "-t", "demo:main", "#{window_id}")
        self.script("tmux-park", "park", wid, "--session", "demo")
        self.assertIn(wid, self.script("tmux-park", "list", "--session", "demo"))
        self.assertNotIn(wid, self.tmux("list-windows", "-t", "=demo", "-F", "#{window_id}"))
        self.script("tmux-park", "unpark", wid, "--session", "demo")
        self.assertIn(wid, self.tmux("list-windows", "-t", "=demo", "-F", "#{window_id}"))
        self.assertIn("empty", self.script("tmux-park", "list", "--session", "demo"))

    def test_save_dry_run_restore_and_duplicate_skip(self):
        wid = self.tmux("new-window", "-d", "-t", "demo:", "-n", "parked",
                        "-c", str(self.home), "-P", "-F", "#{window_id}")
        self.script("tmux-park", "park", wid, "--session", "demo")
        self.script("tmux-save", "--session", "demo")
        snapshot = self.home / ".tmux-ai-sessions.json"
        data = json.loads(snapshot.read_text())
        self.assertEqual([w["name"] for w in data["windows"]], ["main"])
        self.assertEqual([w["name"] for w in data["parked_windows"]], ["parked"])
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
        self.script("tmux-save", "--session", "demo")
        self.assertTrue(Path(str(snapshot) + ".bak").exists())
        self.script("tmux-load", "--session", "restored", "--dry-run")
        sessions = self.tmux("list-sessions", "-F", "#{session_name}").splitlines()
        self.assertNotIn("restored", sessions)
        self.script("tmux-load", "--session", "restored")
        self.assertEqual(self.tmux("list-windows", "-t", "=restored", "-F", "#{window_name}"), "main")
        self.assertEqual(self.tmux("list-windows", "-t", "=" + parking_name("restored"),
                                   "-F", "#{window_name}"), "parked")
        self.assertIn("skip window", self.script("tmux-load", "--session", "restored"))

    def test_attention_marker_and_config_acknowledgement(self):
        self.tmux("source-file", str(ROOT / "config" / "tmux.conf"))
        self.env["TMUX"] = "test"
        self.env["TMUX_PANE"] = self.tmux("display-message", "-p", "-t", "demo:main", "#{pane_id}")
        helper = str(ROOT / "bin" / "tmux-agent-status")
        self.run_command(["sh", helper, "waiting"])
        self.assertEqual(self.tmux("show-option", "-wqv", "-t", "demo:main", "@agent_waiting"), "1")
        self.run_command(["sh", helper, "waiting"])
        self.run_command(["sh", helper, "active"])
        self.assertEqual(self.tmux("show-option", "-wqv", "-t", "demo:main", "@agent_waiting"), "")
        self.run_command(["sh", helper, "waiting"])
        self.tmux("select-window", "-t", "demo:main")
        self.assertEqual(self.tmux("show-option", "-wqv", "-t", "demo:main", "@agent_waiting"), "")

    def test_installer_backup_and_no_default_config_change(self):
        self.run_command(["sh", str(ROOT / "install.sh")])
        self.assertFalse((self.home / ".tmux.conf").exists())
        self.assertTrue(os.access(self.home / "bin/tmux-save", os.X_OK))
        config = self.home / ".tmux.conf"
        config.write_text("# existing config\n")
        self.run_command(["sh", str(ROOT / "install.sh"), "--with-tmux-config"])
        backups = list(self.home.glob(".tmux.conf.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "# existing config\n")
        self.assertEqual(config.read_text(), (ROOT / "config/tmux.conf").read_text())


if __name__ == "__main__":
    unittest.main()
