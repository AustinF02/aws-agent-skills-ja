import importlib.util
from contextlib import contextmanager
import io
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

    @contextmanager
    def configured_main(self, config, version="aws-cli/2.32.0 Python/3", credentials="",
                        mode="--check", profile="example-profile", version_code=0):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config"
            credentials_path = Path(directory) / "credentials"
            config_path.write_text(config, encoding="utf-8")
            credentials_path.write_text(credentials, encoding="utf-8")
            argv = ["helper", "--profile", profile, "--region", "ap-northeast-1"]
            if mode:
                argv.append(mode)
            with patch.dict(os.environ, {"AWS_CONFIG_FILE": str(config_path),
                                         "AWS_SHARED_CREDENTIALS_FILE": str(credentials_path)}), \
                    patch.object(self.helper.sys, "argv", argv), \
                    patch.object(self.helper.shutil, "which", side_effect=lambda name: name), \
                    patch.object(self.helper.subprocess, "run", return_value=subprocess.CompletedProcess(
                        [], version_code, stdout=version, stderr="private diagnostic")) as run, \
                    patch.object(self.helper, "check_auth", return_value=True) as check, \
                    patch.object(self.helper, "login") as login, \
                    patch.object(self.helper, "ensure_auth") as ensure, \
                    patch.object(self.helper.os, "execvpe") as start, \
                    patch("sys.stdout", new_callable=io.StringIO):
                yield check, login, ensure, start, run

    def test_all_modes_reject_unsupported_cli_before_authentication(self):
        for version, code in (("aws-cli/1.42.0", 0), ("aws-cli/2.31.99", 0),
                              ("unrecognized version", 0), ("aws-cli/2.32.0", 1)):
            for mode in ("--check", "--login-only", ""):
                with self.subTest(version=version, code=code, mode=mode), self.configured_main(
                        "[profile example-profile]\nlogin_session = example-session\n",
                        version=version, version_code=code, mode=mode) as calls:
                    with self.assertRaises(RuntimeError) as error:
                        self.helper.main()
                    self.assertNotIn("private diagnostic", str(error.exception))
                    for call in calls[:4]:
                        call.assert_not_called()

    def test_supported_cli_preserves_each_mode(self):
        for version in ("aws-cli/2.32.0", "aws-cli/2.38.5"):
            for mode in ("--check", "--login-only", ""):
                with self.subTest(version=version, mode=mode), self.configured_main(
                        "[profile example-profile]\nlogin_session = example-session\n",
                        version=version, mode=mode) as (check, login, ensure, start, run):
                    self.helper.main()
                    run.assert_called_once()
                    self.assertEqual(run.call_args.args[0], ["aws", "--version"])
                    if mode == "--check":
                        check.assert_called_once()
                        login.assert_not_called()
                        start.assert_not_called()
                    elif mode == "--login-only":
                        login.assert_called_once()
                        check.assert_called_once()
                        start.assert_not_called()
                    else:
                        ensure.assert_called_once()
                        start.assert_called_once()

    def test_missing_or_uninitialized_profile_never_authenticates(self):
        for config in ("", "[profile other]\nlogin_session = example-session\n",
                       "[profile example-profile]\nregion = ap-northeast-1\n",
                       "[profile example-profile]\nlogin_session =\n"):
            for mode in ("--check", "--login-only", ""):
                with self.subTest(config=config, mode=mode), self.configured_main(
                        config, mode=mode) as calls:
                    with self.assertRaises(RuntimeError):
                        self.helper.main()
                    for call in calls[:4]:
                        call.assert_not_called()

    def test_other_authentication_settings_never_authenticate(self):
        for setting in ("sso_session", "sso_start_url", "sso_account_id", "sso_role_name",
                        "role_arn", "source_profile", "credential_source", "credential_process",
                        "web_identity_token_file", "aws_access_key_id", "aws_secret_access_key",
                        "aws_session_token"):
            for mode in ("--check", "--login-only", ""):
                config = "[profile example-profile]\nlogin_session = example-session\n" + setting + " =\n"
                with self.subTest(setting=setting, mode=mode), self.configured_main(
                        config, mode=mode) as calls:
                    with self.assertRaises(RuntimeError):
                        self.helper.main()
                    for call in calls[:4]:
                        call.assert_not_called()

    def test_shared_credentials_conflict_never_authenticates(self):
        for mode in ("--check", "--login-only", ""):
            with self.subTest(mode=mode), self.configured_main(
                    "[profile example-profile]\nlogin_session = example-session\n",
                    credentials="[example-profile]\naws_access_key_id =\n", mode=mode) as calls:
                with self.assertRaises(RuntimeError):
                    self.helper.main()
                for call in calls[:4]:
                    call.assert_not_called()

    def test_default_profile_and_unrelated_credentials_are_preserved(self):
        with self.configured_main("[default]\nlogin_session = example-session\n",
                                  credentials="[other]\naws_access_key_id =\n",
                                  profile="default") as (check, login, ensure, start, run):
            self.helper.main()
            check.assert_called_once_with("aws", "default", "ap-northeast-1")
            login.assert_not_called()

    def test_malformed_configuration_stops_without_raw_details(self):
        for config in ("private diagnostic without a section",
                       "[profile example-profile]\nlogin_session = one\nlogin_session = two\n"):
            with self.subTest(config=config), self.configured_main(config) as calls:
                with self.assertRaises(RuntimeError) as error:
                    self.helper.main()
                self.assertNotIn("private diagnostic", str(error.exception))
                for call in calls[:4]:
                    call.assert_not_called()

    def test_unreadable_configuration_stops_before_authentication(self):
        with self.configured_main("[profile example-profile]\nlogin_session = example-session\n") as calls:
            with patch.object(self.helper.Path, "open", side_effect=PermissionError("private diagnostic")):
                with self.assertRaises(RuntimeError) as error:
                    self.helper.main()
            self.assertNotIn("private diagnostic", str(error.exception))
            for call in calls[:4]:
                call.assert_not_called()


class PackageTests(unittest.TestCase):
    def test_six_discoverable_skills(self):
        paths = list((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(len(paths), 6)
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
