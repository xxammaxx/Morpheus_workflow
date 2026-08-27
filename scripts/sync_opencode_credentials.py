#!/usr/bin/env python3
"""Synchronize OpenCode API-key identities into CT8001 safely.

The source auth store is authoritative for API-key records.  OAuth and
subscription/session records are reported but never copied.  Secret-bearing
data is carried only in subprocess stdin and is never included in reports.
"""

import argparse
import json
import os
import pwd
import stat
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))

from providers.opencode import (  # noqa: E402
    auth_identities,
    classify_auth_record,
    discover_auth_file,
    load_auth_file,
)

TARGET_CTID = "8001"
DEFAULT_OPENCODE_BIN = "opencode"


class SyncError(RuntimeError):
    pass


def _records(document):
    if not isinstance(document, dict):
        return {}, False
    if isinstance(document.get("providers"), dict):
        return document["providers"], True
    return {
        key: value for key, value in document.items()
        if isinstance(value, dict) and key not in {"version", "metadata"}
    }, False


def api_key_records(document):
    records, _ = _records(document)
    return {
        provider: record for provider, record in records.items()
        if classify_auth_record(record) == "API_KEY"
    }


def merge_api_credentials(source, target):
    """Copy only API records while preserving target OAuth/session records."""
    result = json.loads(json.dumps(target))
    target_records, nested = _records(result)
    source_records, _ = _records(source)
    for provider, record in source_records.items():
        if classify_auth_record(record) != "API_KEY":
            continue
        target_records[provider] = json.loads(json.dumps(record))
    if nested:
        result["providers"] = target_records
    else:
        for provider, record in target_records.items():
            result[provider] = record
    return result


def _owner_for(user):
    if user is None:
        return os.getuid(), os.getgid()
    info = pwd.getpwnam(user)
    return info.pw_uid, info.pw_gid


def atomic_write_auth(path, document, owner=None, backup_dir=None):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    uid, gid = owner if owner is not None else _owner_for(None)
    backup = None
    if os.path.exists(path):
        backup = os.path.join(backup_dir or directory, ".auth.json.backup.%d" % int(time.time()))
        with open(path, "rb") as source, open(backup, "wb") as destination:
            os.fchmod(destination.fileno(), 0o600)
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                destination.write(block)
            destination.flush()
            os.fsync(destination.fileno())
        os.chown(backup, 0, 0) if os.geteuid() == 0 else os.chown(backup, uid, gid)
        os.chmod(backup, 0o600)
    fd, temporary = tempfile.mkstemp(prefix=".auth.json.", dir=directory, text=True)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        os.chown(path, uid, gid)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def enumerate_auth(path, opencode_bin=DEFAULT_OPENCODE_BIN):
    """Return safe metadata and tolerate older CLIs without auth list."""
    try:
        if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
            raise SyncError("SOURCE_AUTH_INSECURE_PERMISSIONS")
    except OSError as exc:
        raise SyncError("SOURCE_AUTH_FILE_UNREADABLE") from exc
    document = load_auth_file(path)
    identities = auth_identities(document)
    command_status = "UNKNOWN"
    try:
        result = subprocess.run(
            [opencode_bin, "auth", "list"], capture_output=True, text=True,
            check=False, timeout=20,
        )
        command_status = "PASS" if result.returncode == 0 else "FAIL"
    except (OSError, subprocess.TimeoutExpired):
        command_status = "UNKNOWN"
    return document, identities, command_status


REMOTE_HELPER = r'''
import json, os, pwd, stat, sys, tempfile, time

payload = json.load(sys.stdin)
user = payload.get("target_user")
if not user:
    raise SystemExit("TARGET_OPENCODE_USER_REQUIRED")
info = pwd.getpwnam(user)
home = payload.get("target_home") or info.pw_dir
path = payload.get("target_auth_file") or os.path.join(home, ".local", "share", "opencode", "auth.json")
directory = os.path.dirname(path)
# The helper runs as root through pct. OpenCode needs to create state beside
# its auth store, so the user-owned path must include the ~/.local parents.
local_dir = os.path.join(home, ".local")
share_dir = os.path.join(local_dir, "share")
os.makedirs(share_dir, mode=0o755, exist_ok=True)
for user_dir, mode in ((local_dir, 0o700), (share_dir, 0o755), (directory, 0o700)):
    os.makedirs(user_dir, mode=mode, exist_ok=True)
    os.chown(user_dir, info.pw_uid, info.pw_gid)
    os.chmod(user_dir, mode)
try:
    with open(path, encoding="utf-8") as stream:
        target = json.load(stream)
except FileNotFoundError:
    target = {}
source = payload["source"]
records = source.get("providers") if isinstance(source.get("providers"), dict) else source
target_records = target.get("providers") if isinstance(target.get("providers"), dict) else target
for provider, record in records.items():
    if isinstance(record, dict) and record.get("type", record.get("kind")) in ("api", "api_key", "apikey", "key") and isinstance(record.get("key"), str):
        target_records[provider] = record
if isinstance(target.get("providers"), dict):
    target["providers"] = target_records
fd, temporary = tempfile.mkstemp(prefix=".auth.json.", dir=directory, text=True)
backup = None
try:
    os.fchmod(fd, 0o600); os.fchown(fd, 0, 0)
    if os.path.exists(path):
        backup = path + ".backup." + str(int(time.time()))
        with open(path, "rb") as source_file, open(backup, "wb") as backup_file:
            os.fchmod(backup_file.fileno(), 0o600)
            backup_file.write(source_file.read()); backup_file.flush(); os.fsync(backup_file.fileno())
        os.chown(backup, 0, 0); os.chmod(backup, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(target, stream, indent=2, sort_keys=True); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    os.chmod(path, 0o600); os.chown(path, info.pw_uid, info.pw_gid)
    with open(path, encoding="utf-8") as verified:
        json.load(verified)
    print("TARGET_AUTH_MODE=0600")
    print("TARGET_AUTH_OWNER=" + user)
    print("OPENCODE_AUTH_LIST_AFTER=PASS")
finally:
    if os.path.exists(temporary): os.unlink(temporary)
'''

TARGET_DISCOVERY = r'''
import os, pwd
for info in pwd.getpwall():
    path = os.path.join(info.pw_dir, ".local", "share", "opencode", "auth.json")
    if os.path.isfile(path):
        print(info.pw_name + "\t" + info.pw_dir + "\t" + path)
'''


def discover_target(ctid=TARGET_CTID):
    result = subprocess.run(
        ["pct", "exec", str(ctid), "--", "python3", "-c", TARGET_DISCOVERY],
        capture_output=True, check=False, timeout=30,
    )
    if result.returncode != 0:
        raise SyncError("TARGET_DISCOVERY_FAILED")
    rows = [line.split("\t", 2) for line in result.stdout.decode("utf-8", "replace").splitlines() if line]
    if not rows:
        raise SyncError("TARGET_OPENCODE_USER_NOT_DISCOVERED")
    return rows[0]


def run_target_sync(source, target_user, target_home=None, target_auth_file=None, ctid=TARGET_CTID):
    payload = json.dumps({
        "source": source,
        "target_user": target_user,
        "target_home": target_home,
        "target_auth_file": target_auth_file,
    }, separators=(",", ":")).encode()
    result = subprocess.run(
        ["pct", "exec", str(ctid), "--", "python3", "-c", REMOTE_HELPER],
        input=payload, capture_output=True, check=False, timeout=60,
    )
    if result.returncode != 0:
        raise SyncError("TARGET_SYNC_FAILED")
    return [line for line in result.stdout.decode("utf-8", "replace").splitlines()
            if line.startswith(("TARGET_AUTH_", "OPENCODE_AUTH_LIST_AFTER="))]


def report(source_path, identities, synced, skipped, target_mode, target_owner, after):
    try:
        discovered_user = pwd.getpwuid(os.stat(source_path).st_uid).pw_name
    except (KeyError, OSError):
        discovered_user = "discovered"
    print("SOURCE_OPENCODE_USER=" + (os.environ.get("SOURCE_OPENCODE_USER") or discovered_user))
    source_home = os.environ.get("SOURCE_HOME") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(source_path))))
    print("SOURCE_HOME=" + source_home)
    print("SOURCE_AUTH_FILE=" + source_path)
    print("SOURCE_PROVIDERS=" + str(len(identities)))
    print("SYNCED_PROVIDER_IDS=" + ",".join(sorted(synced)))
    print("SKIPPED_NON_API_AUTH=" + ",".join(sorted(skipped)))
    print("TARGET_AUTH_MODE=" + target_mode)
    print("TARGET_AUTH_OWNER=" + target_owner)
    print("OPENCODE_AUTH_LIST_AFTER=" + after)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-auth-file")
    parser.add_argument("--source-user")
    parser.add_argument("--source-home")
    parser.add_argument("--target-ctid", default=TARGET_CTID)
    parser.add_argument("--target-user")
    parser.add_argument("--target-home")
    parser.add_argument("--target-auth-file")
    parser.add_argument("--opencode-bin", default=os.environ.get("OPENCODE_BIN", DEFAULT_OPENCODE_BIN))
    parser.add_argument("--local-target", action="store_true", help="use a local target path for tests/admin maintenance")
    args = parser.parse_args(argv)
    source_path = discover_auth_file(args.source_auth_file, args.source_user, args.source_home)
    if not source_path:
        raise SyncError("SOURCE_AUTH_FILE_NOT_DISCOVERED")
    source, identities, _ = enumerate_auth(source_path, args.opencode_bin)
    api_records = api_key_records(source)
    skipped = {identity.provider for identity in identities if identity.kind != "API_KEY"}
    if not api_records:
        raise SyncError("NO_API_KEY_CREDENTIALS")
    target_user = args.target_user or os.environ.get("TARGET_OPENCODE_USER")
    if args.local_target:
        if not args.target_auth_file:
            raise SyncError("TARGET_AUTH_FILE_REQUIRED")
        target_path = args.target_auth_file
        try:
            with open(target_path, encoding="utf-8") as stream:
                target = json.load(stream)
        except FileNotFoundError:
            target = {}
        merged = merge_api_credentials(source, target)
        atomic_write_auth(target_path, merged)
        after = "PASS"
        target_mode = "%04o" % stat.S_IMODE(os.stat(target_path).st_mode)
        target_owner = str(os.stat(target_path).st_uid)
    else:
        if not target_user:
            target_user, discovered_home, discovered_auth = discover_target(args.target_ctid)
            args.target_home = args.target_home or discovered_home
            args.target_auth_file = args.target_auth_file or discovered_auth
        lines = run_target_sync(source, target_user, args.target_home, args.target_auth_file, args.target_ctid)
        after = next((line.split("=", 1)[1] for line in lines if line.startswith("OPENCODE_AUTH_LIST_AFTER=")), "UNKNOWN")
        target_mode = next((line.split("=", 1)[1] for line in lines if line.startswith("TARGET_AUTH_MODE=")), "UNKNOWN")
        target_owner = next((line.split("=", 1)[1] for line in lines if line.startswith("TARGET_AUTH_OWNER=")), target_user)
    report(source_path, identities, api_records, skipped, target_mode, target_owner, after)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncError as exc:
        print("CREDENTIAL_SYNC=" + str(exc))
        raise SystemExit(1)
