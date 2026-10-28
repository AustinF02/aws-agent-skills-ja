import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills/aws-login-helper/scripts/aws_mcp_login.py"


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("helper", SOURCE)
        cls.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.helper)

    def test_profile_argument_rejects_options(self):
        with self.assertRaises(ValueError):
            self.helper.validate("-debug", "ap-northeast-1")

    def test_region_rejects_shell_text(self):
        with self.assertRaises(ValueError):
            self.helper.validate("example-profile", "ap-northeast-1; echo test")

    def test_valid_profile_and_region(self):
        self.helper.validate("example-profile", "ap-northeast-1")

    def test_valid_credentials_do_not_login(self):
        with patch.object(self.helper, "check_auth", return_value=True), patch.object(self.helper, "login") as login, tempfile.TemporaryDirectory() as directory:
            self.helper.ensure_auth("aws", "example-profile", "ap-northeast-1", Path(directory))
            login.assert_not_called()

    def test_expired_credentials_login_once_then_recheck(self):
        with patch.object(self.helper, "check_auth", side_effect=[False, True]) as check, patch.object(self.helper, "login") as login, tempfile.TemporaryDirectory() as directory:
            self.helper.ensure_auth("aws", "example-profile", "ap-northeast-1", Path(directory))
            login.assert_called_once()
            self.assertEqual(check.call_count, 2)

    def test_login_does_not_claim_success_if_still_expired(self):
        with patch.object(self.helper, "check_auth", return_value=False), patch.object(self.helper, "login"), tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                self.helper.ensure_auth("aws", "example-profile", "ap-northeast-1", Path(directory))

    def test_sts_response_not_logged(self):
        response = subprocess.CompletedProcess([], 0, stdout="true", stderr="")
        with patch.object(self.helper.subprocess, "run", return_value=response) as run:
            self.assertTrue(self.helper.check_auth("aws", "example-profile", "ap-northeast-1"))
            self.assertIn("--query", run.call_args.args[0])
            self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_expired_refresh_token_recognized(self):
        response = subprocess.CompletedProcess([], 1, stdout="", stderr="The refresh token has expired.")
        with patch.object(self.helper.subprocess, "run", return_value=response):
            self.assertFalse(self.helper.check_auth("aws", "example-profile", "ap-northeast-1"))

    def test_network_failure_is_not_expiry(self):
        response = subprocess.CompletedProcess([], 1, stdout="", stderr="Could not connect to endpoint")
        with patch.object(self.helper.subprocess, "run", return_value=response), self.assertRaises(RuntimeError):
            self.helper.check_auth("aws", "example-profile", "ap-northeast-1")

    def test_login_cancellation_stops(self):
        with patch.object(self.helper.sys.stdin, "isatty", return_value=True), patch.object(self.helper.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(RuntimeError):
                self.helper.login("aws", "example-profile", "ap-northeast-1")

    def test_clean_environment_removes_ambient_credentials(self):
        with patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "test-value", "AWS_SECRET_ACCESS_KEY": "test-value", "AWS_SESSION_TOKEN": "test-value"}):
            env = self.helper.environment("example-profile", "ap-northeast-1")
            for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
                self.assertNotIn(key, env)
            self.assertEqual(env["AWS_PROFILE"], "example-profile")


    def test_non_macos_gui_requires_terminal(self):
        with patch.object(self.helper.sys.stdin, "isatty", return_value=False), patch.object(self.helper.sys, "platform", "linux"), patch.object(self.helper.subprocess, "run") as run:
            with self.assertRaises(RuntimeError):
                self.helper.login("aws", "example-profile", "ap-northeast-1")
            run.assert_not_called()

    def test_macos_gui_opens_terminal_and_waits_for_auth(self):
        with patch.object(self.helper.sys.stdin, "isatty", return_value=False), patch.object(self.helper.sys, "platform", "darwin"), patch.object(self.helper.subprocess, "run") as run, patch.object(self.helper.time, "sleep"), patch.object(self.helper, "check_auth", return_value=True):
            self.helper.login("aws", "example-profile", "ap-northeast-1")
            self.assertEqual(run.call_args.args[0][0], "/usr/bin/osascript")
            self.assertIn("--login-only", run.call_args.args[0][-1])
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_lock_serializes_concurrent_startup(self):
        import threading
        acquired = threading.Event()
        started = threading.Event()
        errors = []
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "shared.lock"
            def second():
                started.set()
                try:
                    with self.helper.login_lock(lock):
                        acquired.set()
                except BaseException as error:
                    errors.append(error)
            with self.helper.login_lock(lock):
                worker = threading.Thread(target=second)
                worker.start()
                self.assertTrue(started.wait(2))
                self.assertFalse(acquired.wait(0.15))
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)
            self.assertTrue(acquired.is_set())


class PackageTests(unittest.TestCase):
    def test_five_discoverable_skills(self):
        paths = list((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(len(paths), 5)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            front = text.split("---", 2)[1]
            self.assertIn("name: " + path.parent.name, front)
            self.assertIn("description:", front)

    def test_theme_and_personal_data_not_bundled(self):
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for forbidden in ("/Users/" + "austinfang", "austin" + "-os", "BEGIN " + "PRIVATE KEY"):
                self.assertNotIn(forbidden, text, str(path))

    def test_local_skill_links_exist(self):
        import re
        for path in (ROOT / "skills").rglob("*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue((path.parent / target.split("#")[0]).exists(), f"{path}: {target}")


if __name__ == "__main__":
    unittest.main()
