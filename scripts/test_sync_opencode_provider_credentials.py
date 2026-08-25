#!/usr/bin/env python3
"""Compatibility tests for the dynamic OpenCode credential synchronizer."""

import json
import os
import stat
import tempfile
import unittest

import sync_opencode_credentials as sync


class CredentialSyncTests(unittest.TestCase):
    def test_only_api_keys_are_merged(self):
        source = {
            "openrouter": {"type": "api", "key": "fixture-api-value"},
            "github": {"type": "oauth", "access_token": "fixture-oauth-value"},
        }
        target = {
            "github": {"type": "oauth", "access_token": "target-oauth"},
            "zen": {"type": "api", "key": "old"},
        }
        merged = sync.merge_api_credentials(source, target)
        self.assertEqual(merged["openrouter"]["key"], "fixture-api-value")
        self.assertEqual(merged["github"]["access_token"], "target-oauth")
        self.assertEqual(merged["zen"]["key"], "old")

    def test_nested_schema_is_preserved(self):
        source = {"providers": {"zen": {"type": "api", "key": "fixture-api-value"}}}
        target = {"version": 1, "providers": {"zen": {"type": "oauth"}}}
        merged = sync.merge_api_credentials(source, target)
        self.assertEqual(merged["version"], 1)
        self.assertEqual(merged["providers"]["zen"]["key"], "fixture-api-value")

    def test_atomic_local_write_is_0600_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "auth.json")
            document = {"zen": {"type": "api", "key": "fixture-api-value"}}
            sync.atomic_write_auth(path, document)
            first = open(path, encoding="utf-8").read()
            sync.atomic_write_auth(path, document)
            self.assertEqual(first, open(path, encoding="utf-8").read())
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertNotIn("secret", json.dumps({"report": "metadata-only"}))

    def test_remote_helper_assigns_auth_directory_to_target_user(self):
        self.assertIn("os.chown(directory, info.pw_uid, info.pw_gid)", sync.REMOTE_HELPER)
        self.assertIn("os.chmod(directory, 0o700)", sync.REMOTE_HELPER)


if __name__ == "__main__":
    unittest.main()
