#!/usr/bin/env python3
"""Bridge only the local Groq/OpenRouter keys into the harness service.

Secret values are read into this process, sent only as SSH stdin to a root
remote helper, and are never placed in argv, logs, or command output.
"""

import argparse
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile

PROVIDERS = ("groq", "openrouter")
ENV_NAMES = {"groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
DEFAULT_AUTH_STORE = "~/.local/share/opencode/auth.json"
DEFAULT_STATE_DIR = "/var/lib/autodev-harness-v2"
DEFAULT_ENV_PATH = DEFAULT_STATE_DIR + "/provider.env"
DEFAULT_DROPIN = "/etc/systemd/system/autodev-harness-v2.service.d/20-provider-credentials.conf"

# This code is intentionally passed as a non-secret remote command. Values
# arrive only through stdin and are parsed on the remote host.
REMOTE_HELPER = r'''
import json, os, stat, subprocess, sys, tempfile

env_path = sys.argv[1]
dropin = sys.argv[2]
service = sys.argv[3]
payload = json.load(sys.stdin)
values = payload["values"]
directory = os.path.dirname(env_path)
dropin_dir = os.path.dirname(dropin)
if not os.path.isdir(directory):
    raise SystemExit("TARGET_STATE_DIR_MISSING")
if not os.path.isdir(dropin_dir):
    os.makedirs(dropin_dir, mode=0o755, exist_ok=True)
for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
    value = values.get(name)
    if not isinstance(value, str) or not value:
        raise SystemExit("TARGET_CREDENTIAL_MISSING")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise SystemExit("TARGET_CREDENTIAL_INVALID")

content = "GROQ_API_KEY=" + values["GROQ_API_KEY"] + "\n"
content += "OPENROUTER_API_KEY=" + values["OPENROUTER_API_KEY"] + "\n"
fd, temporary = tempfile.mkstemp(prefix=".provider.env.", dir=directory, text=True)
try:
    os.fchmod(fd, 0o600)
    os.fchown(fd, 0, 0)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, env_path)
    os.chmod(env_path, 0o600)
    os.chown(env_path, 0, 0)
    fd = None
    if os.stat(env_path).st_uid != 0 or os.stat(env_path).st_gid != 0:
        raise SystemExit("TARGET_CREDENTIAL_PERMISSIONS")
    if stat.S_IMODE(os.stat(env_path).st_mode) != 0o600:
        raise SystemExit("TARGET_CREDENTIAL_PERMISSIONS")
    fd2, dropin_tmp = tempfile.mkstemp(prefix=".20-provider-credentials.", dir=dropin_dir, text=True)
    try:
        with os.fdopen(fd2, "w", encoding="utf-8") as stream:
            stream.write("[Service]\nEnvironmentFile=" + env_path + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(dropin_tmp, 0, 0)
        os.chmod(dropin_tmp, 0o644)
        os.replace(dropin_tmp, dropin)
    finally:
        if os.path.exists(dropin_tmp):
            os.unlink(dropin_tmp)
    subprocess.run(["systemctl", "daemon-reload"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "restart", service], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    active = subprocess.run(["systemctl", "is-active", "--quiet", service], check=False)
    if active.returncode != 0:
        raise SystemExit("SERVICE_NOT_ACTIVE")
    print("REMOTE_PROVIDER_ENV_FILE=PASS")
    print("REMOTE_PROVIDER_ENV_MODE=0600")
    print("SYSTEMD_PROVIDER_ENVIRONMENT_WIRED=true")
    print("SERVICE_RESTART=PASS")
finally:
    if fd is not None:
        os.close(fd)
    if os.path.exists(temporary):
        os.unlink(temporary)
'''


class BridgeError(RuntimeError):
    pass


def _status(message):
    print(message)


def load_credentials(path):
    """Return the two required values, emitting only presence statuses."""
    try:
        info = os.stat(path)
    except OSError as exc:
        raise BridgeError("SOURCE_AUTH_STORE_UNREADABLE") from exc
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise BridgeError("BLOCKED_INSECURE_SOURCE_PERMISSIONS")
    try:
        with open(path, encoding="utf-8") as stream:
            document = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BridgeError("SOURCE_AUTH_STORE_INVALID") from exc
    if not isinstance(document, dict):
        raise BridgeError("SOURCE_AUTH_STORE_INVALID")
    values = {}
    for provider in PROVIDERS:
        record = document.get(provider)
        value = record.get("key") if isinstance(record, dict) else None
        if not isinstance(value, str) or not value:
            raise BridgeError("BLOCKED_SOURCE_CREDENTIAL_MISSING provider=" + provider)
        values[ENV_NAMES[provider]] = value
        _status("SOURCE_OPENCODE_%s=PRESENT" % provider.upper())
    return values


def _ssh_base(host, user="root", host_key_alias=None):
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if host_key_alias:
        command.extend(["-o", "HostKeyAlias=" + host_key_alias])
    command.append((user + "@" + host) if user else host)
    return command


def run_ssh(host, remote_command, input_bytes=None, user="root", host_key_alias=None):
    command = _ssh_base(host, user, host_key_alias) + [remote_command]
    try:
        result = subprocess.run(
            command,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise BridgeError("BLOCKED_CREDENTIAL_TRANSFER_TRANSPORT") from exc
    if result.returncode != 0:
        raise BridgeError("BLOCKED_CREDENTIAL_TRANSFER_TRANSPORT")
    return result.stdout.decode("utf-8", "replace")


def remote_preflight(host, service, state_dir, user="root", host_key_alias=None):
    command = (
        "test -d %s && test -d /etc/systemd/system && "
        "systemctl cat %s >/dev/null && "
        "printf 'SSH_TARGET=PASS\\nSERVICE_EXISTS=true\\nTARGET_DIRECTORIES=PASS\\n'"
        % (shlex.quote(state_dir), shlex.quote(service))
    )
    return run_ssh(host, command, user=user, host_key_alias=host_key_alias)


def sync(host, service, values, state_dir=DEFAULT_STATE_DIR, user="root", host_key_alias=None):
    env_path = state_dir + "/provider.env"
    dropin = "/etc/systemd/system/%s.service.d/20-provider-credentials.conf" % service
    payload = json.dumps({"values": values}, separators=(",", ":")).encode("utf-8")
    command = "python3 -c %s %s %s %s" % (
        shlex.quote(REMOTE_HELPER),
        shlex.quote(env_path),
        shlex.quote(dropin),
        shlex.quote(service),
    )
    _status("TRANSFER_CHANNEL=SSH_STDIN")
    output = run_ssh(host, command, input_bytes=payload, user=user, host_key_alias=host_key_alias)
    for line in output.splitlines():
        if line.startswith(("REMOTE_PROVIDER_ENV_", "SYSTEMD_PROVIDER_", "SERVICE_RESTART=")):
            _status(line)
    _status("REMOTE_PROVIDER_ENV_PATH=" + env_path)
    _status("SYSTEMD_DROPIN=" + dropin)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="pve")
    parser.add_argument("--user", default="root")
    parser.add_argument("--host-key-alias")
    parser.add_argument("--service", default="autodev-harness-v2")
    parser.add_argument("--auth-store", default=DEFAULT_AUTH_STORE)
    parser.add_argument("--state-dir", default=DEFAULT_STATE_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        values = load_credentials(os.path.expanduser(args.auth_store))
        remote_preflight(args.host, args.service, args.state_dir, args.user, args.host_key_alias)
        _status("SSH_TARGET=PASS")
        if args.dry_run or args.verify_only:
            _status("DRY_RUN=PASS" if args.dry_run else "VERIFY_ONLY=PASS")
            return 0
        sync(args.host, args.service, values, args.state_dir, args.user, args.host_key_alias)
        _status("CREDENTIAL_SYNC=PASS")
        return 0
    except BridgeError as exc:
        _status("CREDENTIAL_BRIDGE=%s" % str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
