#!/usr/bin/env python3
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

import sync_opencode_provider_credentials as bridge


class BridgeTests(unittest.TestCase):
    def auth_file(self, document, mode=0o600):
        handle = tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8")
        json.dump(document, handle)
        handle.close()
        os.chmod(handle.name, mode)
        self.addCleanup(lambda: os.unlink(handle.name))
        return handle.name

    def present(self, groq="TEST_GROQ_SECRET_DO_NOT_USE", router="TEST_OPENROUTER_SECRET_DO_NOT_USE"):
        return {"groq": {"key": groq, "type": "api"}, "openrouter": {"key": router, "type": "api"}, "unrelated": {"key": "UNRELATED"}}

    def test_missing_auth_store(self):
        with self.assertRaisesRegex(bridge.BridgeError, "SOURCE_AUTH_STORE_UNREADABLE"):
            bridge.load_credentials("/path/that/does/not/exist")

    def test_malformed_auth_json(self):
        path = tempfile.NamedTemporaryFile(mode="w", delete=False)
        path.write("{not-json")
        path.close()
        os.chmod(path.name, 0o600)
        self.addCleanup(lambda: os.unlink(path.name))
        with self.assertRaisesRegex(bridge.BridgeError, "SOURCE_AUTH_STORE_INVALID"):
            bridge.load_credentials(path.name)

    def test_insecure_permissions_blocked(self):
        path = self.auth_file(self.present(), 0o644)
        with self.assertRaisesRegex(bridge.BridgeError, "BLOCKED_INSECURE_SOURCE_PERMISSIONS"):
            bridge.load_credentials(path)

    def test_missing_provider(self):
        path = self.auth_file({"groq": {"key": "x"}})
        with self.assertRaisesRegex(bridge.BridgeError, "provider=openrouter"):
            bridge.load_credentials(path)

    def test_both_present_and_unrelated_ignored_without_output(self):
        path = self.auth_file(self.present())
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            values = bridge.load_credentials(path)
        self.assertEqual(set(values), {"GROQ_API_KEY", "OPENROUTER_API_KEY"})
        self.assertIn("SOURCE_OPENCODE_GROQ=PRESENT", output.getvalue())
        self.assertNotIn("TEST_GROQ_SECRET_DO_NOT_USE", output.getvalue())
        self.assertNotIn("UNRELATED", output.getvalue())

    @mock.patch.object(bridge.subprocess, "run")
    def test_dry_run_performs_no_remote_write(self, run):
        run.return_value = mock.Mock(returncode=0, stdout=b"SSH_TARGET=PASS\n", stderr=b"")
        path = self.auth_file(self.present())
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            rc = bridge.main(["--auth-store", path, "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(run.call_count, 1)
        self.assertIn("DRY_RUN=PASS", output.getvalue())
        self.assertNotIn("TEST_GROQ_SECRET_DO_NOT_USE", output.getvalue())
        self.assertNotIn("TEST_OPENROUTER_SECRET_DO_NOT_USE", output.getvalue())
        self.assertNotIn("GROQ_API_KEY=", run.call_args.args[0][-1])
        self.assertIsNone(run.call_args.kwargs.get("input"))

    @mock.patch.object(bridge.subprocess, "run")
    def test_transfer_uses_stdin_and_never_argv(self, run):
        run.return_value = mock.Mock(
            returncode=0,
            stdout=b"REMOTE_PROVIDER_ENV_FILE=PASS\nREMOTE_PROVIDER_ENV_MODE=0600\nSYSTEMD_PROVIDER_ENVIRONMENT_WIRED=true\nSERVICE_RESTART=PASS\n",
            stderr=b"",
        )
        path = self.auth_file(self.present())
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            rc = bridge.main(["--auth-store", path])
        self.assertEqual(rc, 0)
        args = run.call_args.args[0]
        self.assertTrue(all("TEST_" not in item for item in args))
        payload = run.call_args.kwargs["input"].decode()
        self.assertIn("TEST_GROQ_SECRET_DO_NOT_USE", payload)
        self.assertIn("TEST_OPENROUTER_SECRET_DO_NOT_USE", payload)
        self.assertNotIn("TEST_GROQ_SECRET_DO_NOT_USE", output.getvalue())
        self.assertNotIn("TEST_OPENROUTER_SECRET_DO_NOT_USE", output.getvalue())
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
