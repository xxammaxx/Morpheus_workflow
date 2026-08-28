"""Read-only runtime telemetry collectors for the Morpheus Control Tower.

The module deliberately has no mutation or arbitrary command surface.  Hosts,
nodes, guests and query fields are all server-side configuration.  The cache is
bounded and in-memory only; it is a visualization aid, never a source of
record.
"""
import csv
import datetime as dt
import io
import json
import os
import shutil
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque


CONTRACT = "autodev.runtime-telemetry.v1"
SAMPLE_CACHE_SECONDS = max(2.0, float(os.environ.get("RUNTIME_TELEMETRY_CACHE_SECONDS", "3")))
STALE_AFTER_SECONDS = max(SAMPLE_CACHE_SECONDS * 2, float(os.environ.get("RUNTIME_TELEMETRY_STALE_SECONDS", "10")))
HISTORY_LIMIT = 30
NVIDIA_GPU_FIELDS = (
    "index", "uuid", "name", "driver_version", "memory.total", "utilization.gpu",
    "utilization.memory", "memory.used", "temperature.gpu", "power.draw",
    "clocks.gr", "clocks.mem", "fan.speed",
)
NVIDIA_PROCESS_FIELDS = ("pid", "process_name", "used_memory")
NVIDIA_QUERY = ",".join(NVIDIA_GPU_FIELDS)
NVIDIA_PROCESS_QUERY = ",".join(NVIDIA_PROCESS_FIELDS)


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def age_ms(sampled_at):
    try:
        value = dt.datetime.fromisoformat(str(sampled_at).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return max(0, int((dt.datetime.now(dt.timezone.utc) - value.astimezone(dt.timezone.utc)).total_seconds() * 1000))
    except (TypeError, ValueError, OverflowError):
        return None


def freshness(sampled_at):
    age = age_ms(sampled_at)
    if age is None:
        return "UNAVAILABLE"
    return "LIVE" if age <= STALE_AFTER_SECONDS * 1000 else "STALE"


def envelope(source, sampled_at, status="LIVE", **values):
    result = {
        "sampled_at": sampled_at,
        "source": source,
        "age_ms": age_ms(sampled_at),
        "freshness": freshness(sampled_at) if status == "LIVE" else status,
        "status": status,
    }
    result.update(values)
    return result


def _credential(name):
    directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if not directory:
        return ""
    try:
        return open(os.path.join(directory, name), encoding="utf-8").read().strip()
    except OSError:
        return ""


def _secret(env_name, credential_name):
    return os.environ.get(env_name, "") or _credential(credential_name)


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).strip())
        return parsed if parsed == parsed else None
    except (TypeError, ValueError):
        return None


def _integer(value):
    parsed = _number(value)
    return int(parsed) if parsed is not None else None


def _metric(value, unit=None):
    if value is None:
        return {"value": None, "status": "NOT_SUPPORTED", "unit": unit}
    return {"value": value, "status": "OK", "unit": unit}


def _load_json_env(name, default):
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        value = json.loads(raw)
        return value
    except (TypeError, ValueError):
        return default


class _HTTPError(Exception):
    def __init__(self, status=0):
        super().__init__(str(status))
        self.status = status


class _JSONClient:
    def __init__(self, base_url, headers=None, context=None):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.context = context

    def get(self, path, query=None, timeout=4):
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=self.context) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _HTTPError(exc.code) from exc
        except (OSError, ValueError, UnicodeError) as exc:
            raise _HTTPError(0) from exc


def _proxmox_config():
    base = os.environ.get("PROXMOX_API_BASE", "").rstrip("/")
    node = os.environ.get("PROXMOX_NODE", "")
    allowed_hosts = {item.strip() for item in os.environ.get("PROXMOX_ALLOWED_HOSTS", "").split(",") if item.strip()}
    token_id = os.environ.get("PROXMOX_API_TOKEN_ID", "")
    token_secret = _secret("PROXMOX_API_TOKEN_SECRET", "proxmox_api_token_secret")
    ca_file = os.environ.get("PROXMOX_CA_FILE", "")
    guests = _load_json_env("MORPHEUS_RUNTIME_GUESTS", {})
    if not isinstance(guests, dict):
        guests = {}
    return base, node, allowed_hosts, token_id, token_secret, ca_file, guests


def _proxmox_context(ca_file):
    if not ca_file:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=ca_file)


def _valid_guest(value, configured_node, guests):
    if not isinstance(value, dict) or value.get("type", "lxc") != "lxc":
        return None
    node = str(value.get("node") or configured_node or "")
    vmid = str(value.get("vmid") or value.get("guest_id") or "")
    if not node or node != configured_node or not vmid.isdigit() or int(vmid) < 100:
        return None
    allowed = {str(item.get("vmid")) for item in guests if isinstance(item, dict)}
    if allowed and vmid not in allowed:
        return None
    return {
        "node": node,
        "vmid": int(vmid),
        "type": "lxc",
        "name": value.get("name"),
        "role": value.get("role"),
    }


def resolve_runtime_guests(run, configured_node, configured_guests):
    """Resolve only canonical metadata or a server-side allowlisted mapping."""
    run = run if isinstance(run, dict) else {}
    allowlisted = []
    for values in configured_guests.values():
        if isinstance(values, dict):
            values = [values]
        if isinstance(values, list):
            allowlisted.extend(values)
    if isinstance(allowlisted, dict):
        allowlisted = [allowlisted]
    if not isinstance(allowlisted, list):
        allowlisted = []
    explicit = run.get("runtime_guests")
    candidates = explicit if isinstance(explicit, list) else []
    if not candidates and isinstance(run.get("runtime_guest"), dict):
        candidates = [run["runtime_guest"]]
    guests = []
    configured_ids = {str(item.get("vmid")) for item in allowlisted if isinstance(item, dict)}
    for candidate in candidates:
        guest = _valid_guest(candidate, configured_node, allowlisted)
        if guest and (not configured_ids or str(guest["vmid"]) in configured_ids):
            guests.append(guest)
    if not guests:
        backend = str(run.get("backend") or run.get("runtime_backend") or "")
        if backend in configured_guests:
            values = configured_guests.get(backend)
            if isinstance(values, dict):
                values = [values]
            for candidate in values if isinstance(values, list) else []:
                guest = _valid_guest(candidate, configured_node, allowlisted or values)
                if guest:
                    guests.append(guest)
    unique = {}
    for guest in guests:
        unique[(guest["node"], guest["vmid"])] = guest
    return list(unique.values())[:8]


def _proxmox_status(client, guest):
    path = "/nodes/%s/lxc/%s/status/current" % (
        urllib.parse.quote(guest["node"], safe=""), guest["vmid"]
    )
    status, payload = client.get(path)
    value = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(value, dict):
        value = {}
    status_value = str(value.get("status") or "UNKNOWN").upper()
    maxmem = _number(value.get("maxmem"))
    mem = _number(value.get("mem"))
    maxswap = _number(value.get("maxswap"))
    swap = _number(value.get("swap"))
    maxdisk = _number(value.get("maxdisk"))
    disk = _number(value.get("disk"))
    cpus = _number(value.get("cpus"))
    raw_cpu = _number(value.get("cpu"))
    cpu = raw_cpu * 100 if raw_cpu is not None and raw_cpu <= 1.5 else raw_cpu
    return {
        "guest": {**guest, "name": value.get("name") or guest.get("name"), "vmid": value.get("vmid", guest["vmid"])},
        "status": "STOPPED" if status_value == "STOPPED" else "OK",
        "proxmox_status": status_value,
        "cpu": _metric(round(cpu, 2) if cpu is not None else None, "%"),
        "cpus": _metric(cpus, "count"),
        "ram": {"used": _metric(mem, "bytes"), "total": _metric(maxmem, "bytes"), "percent": _metric(round(mem / maxmem * 100, 2) if mem is not None and maxmem else None, "%")},
        "swap": {"used": _metric(swap, "bytes"), "total": _metric(maxswap, "bytes"), "percent": _metric(round(swap / maxswap * 100, 2) if swap is not None and maxswap else None, "%")},
        "disk": {"used": _metric(disk, "bytes"), "total": _metric(maxdisk, "bytes"), "percent": _metric(round(disk / maxdisk * 100, 2) if disk is not None and maxdisk else None, "%")},
        "network": {"in_total": _metric(_number(value.get("netin")), "bytes"), "out_total": _metric(_number(value.get("netout")), "bytes"), "in_rate": _metric(None, "bytes_per_second"), "out_rate": _metric(None, "bytes_per_second")},
        "uptime_seconds": _metric(_number(value.get("uptime")), "seconds"),
        "raw": {key: value.get(key) for key in ("vmid", "name", "status", "cpu", "cpus", "mem", "maxmem", "swap", "maxswap", "disk", "maxdisk", "netin", "netout", "uptime") if key in value},
    }


def _parse_guest_history(client, guest):
    try:
        path = "/nodes/%s/lxc/%s/rrddata" % (urllib.parse.quote(guest["node"], safe=""), guest["vmid"])
        _, payload = client.get(path, {"timeframe": "hour", "cf": "AVERAGE"}, timeout=4)
        rows = payload.get("data", payload) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return []
        return [{"time": row.get("time"), "cpu": row.get("cpu"), "mem": row.get("mem"), "netin": row.get("netin"), "netout": row.get("netout")} for row in rows[-HISTORY_LIMIT:] if isinstance(row, dict)]
    except _HTTPError:
        return []


class _Ring:
    def __init__(self):
        self.lock = threading.Lock()
        self.values = {}

    def append(self, key, sampled_at, values):
        with self.lock:
            bucket = self.values.setdefault(key, deque(maxlen=HISTORY_LIMIT))
            bucket.append({"sampled_at": sampled_at, **values})
            return list(bucket)


_guest_ring = _Ring()
_gpu_ring = _Ring()


def proxmox_telemetry(run):
    sampled_at = utc_now()
    base, configured_node, allowed_hosts, token_id, token_secret, ca_file, configured_guests = _proxmox_config()
    guests = resolve_runtime_guests(run, configured_node, configured_guests)
    parsed_base = urllib.parse.urlparse(base)
    if not base or parsed_base.scheme != "https" or parsed_base.hostname not in allowed_hosts or not configured_node or not token_id or not token_secret:
        return envelope("PROXMOX_API", sampled_at, "NOT_CONFIGURED", node=configured_node or None, runtime_guests=[], active_guest=None, error_code="NOT_CONFIGURED")
    if not guests:
        return envelope("MORPHEUS_RUNTIME_EVIDENCE", sampled_at, "UNAVAILABLE", node=configured_node, runtime_guests=[], active_guest=None, error_code="GUEST_NOT_MAPPED")
    headers = {"Authorization": "PVEAPIToken=%s=%s" % (token_id, token_secret), "Accept": "application/json"}
    try:
        client = _JSONClient(base, headers, _proxmox_context(ca_file))
        values = []
        for guest in guests:
            values.append(_proxmox_status(client, guest))
    except (OSError, ssl.SSLError):
        return envelope("PROXMOX_API", sampled_at, "UNAVAILABLE", node=configured_node, runtime_guests=guests, active_guest=None, error_code="PROXMOX_UNREACHABLE")
    except _HTTPError as exc:
        error_code = "PROXMOX_AUTH_FAILED" if exc.status in (401, 403) else "PROXMOX_UNREACHABLE" if exc.status == 0 else "GUEST_NOT_FOUND" if exc.status == 404 else "UNAVAILABLE"
        return envelope("PROXMOX_API", sampled_at, "UNAVAILABLE", node=configured_node, runtime_guests=guests, active_guest=None, error_code=error_code)
    for value in values:
        network = value["network"]
        key = "%s/%s" % (value["guest"]["node"], value["guest"]["vmid"])
        previous = _guest_ring.append(key, sampled_at, {"in_total": network["in_total"]["value"], "out_total": network["out_total"]["value"], "cpu": value["cpu"]["value"], "ram": value["ram"]["percent"]["value"]})
        if len(previous) >= 2:
            old, new = previous[-2], previous[-1]
            interval = ((dt.datetime.fromisoformat(new["sampled_at"]) - dt.datetime.fromisoformat(old["sampled_at"])).total_seconds())
            if interval > 0:
                for direction, field in (("in", "in_total"), ("out", "out_total")):
                    old_total, new_total = old.get(field), new.get(field)
                    delta = new_total - old_total if old_total is not None and new_total is not None else None
                    value["network"][direction + "_rate"] = _metric(round(delta / interval, 2) if delta is not None and delta >= 0 else None, "bytes_per_second")
        value["history"] = previous
        value["rrd_history"] = _parse_guest_history(client, value["guest"])
    primary = values[0]
    status = "STOPPED" if primary["status"] == "STOPPED" else "LIVE"
    return envelope("PROXMOX_API", sampled_at, status, node=configured_node, runtime_guests=values, active_guest=primary["guest"], error_code=None)


def _gpu_config():
    host = os.environ.get("NVIDIA_GPU_HOST", os.environ.get("GPU_HOST", ""))
    user = os.environ.get("NVIDIA_GPU_SSH_USER", os.environ.get("GPU_SSH_USER", ""))
    identity = os.environ.get("NVIDIA_GPU_SSH_IDENTITY_FILE", os.environ.get("GPU_SSH_IDENTITY_FILE", ""))
    allowed = {item.strip() for item in os.environ.get("NVIDIA_GPU_ALLOWED_HOSTS", host).split(",") if item.strip()}
    return host, user, identity, allowed


def _nvidia_command(host, user, identity, query, processes=False):
    executable = shutil.which("nvidia-smi") if not host or host in {"127.0.0.1", "localhost"} else None
    if executable:
        return [executable, "--query-compute-apps=" + query if processes else "--query-gpu=" + query, "--format=csv,noheader,nounits"]
    if not host:
        return None
    if host not in _gpu_config()[3] or not user:
        return None
    destination = "%s@%s" % (user, host)
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=yes"]
    if identity:
        command += ["-i", identity]
    command += [destination, "nvidia-smi", "--query-compute-apps=" + query if processes else "--query-gpu=" + query, "--format=csv,noheader,nounits"]
    return command


def _run_fixed(command):
    if command is None:
        return None, "NOT_CONFIGURED"
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except FileNotFoundError:
        return None, "NVIDIA_SMI_NOT_INSTALLED"
    except (OSError, subprocess.TimeoutExpired):
        return None, "GPU_HOST_UNREACHABLE"
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.returncode != 0:
        if "not found" in error.lower() or "no such file" in error.lower():
            return None, "NVIDIA_SMI_NOT_INSTALLED"
        if "driver" in error.lower() or "failed" in error.lower():
            return None, "NVIDIA_DRIVER_UNAVAILABLE"
        return None, "GPU_HOST_UNREACHABLE"
    return output, None


def _csv_rows(output, fields):
    if not output:
        return []
    rows = []
    for row in csv.reader(io.StringIO(output), skipinitialspace=True):
        if len(row) != len(fields):
            continue
        rows.append(dict(zip(fields, [value.strip() for value in row])))
    return rows


def _gpu_metric(raw, unit):
    raw_text = "" if raw is None else str(raw).strip()
    if not raw_text or raw_text.upper() in {"N/A", "NA", "[NOT SUPPORTED]", "NOT SUPPORTED"}:
        return _metric(None, unit)
    value = _number(raw_text)
    return _metric(round(value, 2) if value is not None else None, unit) if value is not None else _metric(None, unit)


def gpu_telemetry():
    sampled_at = utc_now()
    host, user, identity, allowed = _gpu_config()
    if not host and not shutil.which("nvidia-smi"):
        return envelope("NVIDIA_SMI", sampled_at, "NOT_CONFIGURED", host=None, gpus=[], error_code="NOT_CONFIGURED")
    if host and host not in allowed and host not in {"127.0.0.1", "localhost"}:
        return envelope("NVIDIA_SMI", sampled_at, "NOT_CONFIGURED", host=host, gpus=[], error_code="NOT_CONFIGURED")
    output, error_code = _run_fixed(_nvidia_command(host, user, identity, NVIDIA_QUERY))
    if error_code:
        return envelope("NVIDIA_SMI", sampled_at, error_code, host=host or "local", gpus=[], error_code=error_code)
    process_output, process_error = _run_fixed(_nvidia_command(host, user, identity, NVIDIA_PROCESS_QUERY, processes=True))
    processes = _csv_rows(process_output, NVIDIA_PROCESS_FIELDS) if process_output is not None else []
    process_rows = [{"pid": _integer(row.get("pid")), "process_name": row.get("process_name"), "memory_used": _gpu_metric(row.get("used_memory"), "MiB")} for row in processes]
    gpus = []
    for row in _csv_rows(output, NVIDIA_GPU_FIELDS):
        gpu = {
            "index": _integer(row.get("index")), "uuid": row.get("uuid"), "name": row.get("name"), "driver_version": row.get("driver_version"),
            "memory": {"used": _gpu_metric(row.get("memory.used"), "MiB"), "total": _gpu_metric(row.get("memory.total"), "MiB"), "percent": _gpu_metric(round(_number(row.get("memory.used")) / _number(row.get("memory.total")) * 100, 2) if _number(row.get("memory.used")) is not None and _number(row.get("memory.total")) else None, "%")},
            "utilization": {"gpu": _gpu_metric(row.get("utilization.gpu"), "%"), "memory": _gpu_metric(row.get("utilization.memory"), "%")},
            "temperature": _gpu_metric(row.get("temperature.gpu"), "C"), "power": _gpu_metric(row.get("power.draw"), "W"),
            "clocks": {"graphics": _gpu_metric(row.get("clocks.gr"), "MHz"), "memory": _gpu_metric(row.get("clocks.mem"), "MHz")},
            "fan": _gpu_metric(row.get("fan.speed"), "%"), "processes": process_rows,
        }
        key = gpu.get("uuid") or "index-%s" % gpu.get("index")
        gpu["history"] = _gpu_ring.append(key, sampled_at, {"utilization": gpu["utilization"]["gpu"]["value"], "vram_percent": gpu["memory"]["percent"]["value"]})
        gpus.append(gpu)
    return envelope("NVIDIA_SMI", sampled_at, "LIVE" if gpus else "GPU_NOT_FOUND", host=host or "local", gpus=gpus, error_code=None if gpus else "GPU_NOT_FOUND", process_query_status=process_error or "OK")


def _lm_config():
    base = os.environ.get("LMSTUDIO_BASE_URL", "").rstrip("/")
    token = _secret("LMSTUDIO_API_TOKEN", "lmstudio_api_token")
    allowed = {item.strip() for item in os.environ.get("LMSTUDIO_ALLOWED_HOSTS", "").split(",") if item.strip()}
    return base, token, allowed


def _lm_models(client):
    for path in ("/api/v1/models", "/v1/models"):
        try:
            status, payload = client.get(path)
            if status == 200:
                value = payload.get("data", payload) if isinstance(payload, dict) else payload
                rows = value if isinstance(value, list) else value.get("models", []) if isinstance(value, dict) else []
                return [{"id": row.get("key") or row.get("id") or row.get("model"), "name": row.get("display_name") or row.get("name"), "loaded": bool(row.get("loaded_instances") or row.get("loaded"))} for row in rows if isinstance(row, dict)], path
        except _HTTPError as exc:
            if exc.status in (401, 403):
                return [], "AUTH_FAILED"
    return [], "UNREACHABLE"


def _approved_stats(run):
    allowed = {"input_tokens", "prompt_tokens", "output_tokens", "completion_tokens", "total_output_tokens", "reasoning_output_tokens", "tokens_per_second", "time_to_first_token_seconds", "ttft_seconds", "model_load_time_seconds"}
    sources = {"LMSTUDIO_API", "MORPHEUS_RUNTIME_EVIDENCE"}
    found = {}
    def visit(value):
        if isinstance(value, dict):
            source = value.get("stats_source") or value.get("source")
            for key, item in value.items():
                normalized = {"prompt_tokens": "input_tokens", "completion_tokens": "output_tokens", "ttft_seconds": "time_to_first_token_seconds"}.get(key, key)
                if normalized in allowed and isinstance(item, (int, float)) and not isinstance(item, bool):
                    found.setdefault(normalized, item)
                if key not in {"reasoning_content", "reasoning", "content", "text", "prompt", "response"}:
                    visit(item)
            if source in sources and source == "LMSTUDIO_API":
                found["stats_source"] = source
        elif isinstance(value, list):
            for item in value[-20:]:
                visit(item)
    visit(run)
    return found


def lmstudio_telemetry(run, events):
    sampled_at = utc_now()
    base, token, allowed = _lm_config()
    if not base:
        return envelope("LMSTUDIO_API", sampled_at, "NOT_CONFIGURED", host=None, model=None, server_status="NOT_CONFIGURED", inference_status="IDLE", stats={}, models=[])
    parsed = urllib.parse.urlparse(base)
    if parsed.hostname not in allowed:
        return envelope("LMSTUDIO_API", sampled_at, "NOT_CONFIGURED", host=parsed.hostname, port=parsed.port, model=None, server_status="NOT_CONFIGURED", inference_status="IDLE", stats={}, models=[])
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    client = _JSONClient(base, headers)
    try:
        models, model_path = _lm_models(client)
    except _HTTPError as exc:
        code = "AUTH_FAILED" if exc.status in (401, 403) else "UNREACHABLE"
        return envelope("LMSTUDIO_API", sampled_at, code, host=parsed.hostname, port=parsed.port, model=None, server_status=code, inference_status="IDLE", stats={}, models=[])
    if model_path in {"AUTH_FAILED", "UNREACHABLE"}:
        return envelope("LMSTUDIO_API", sampled_at, model_path, host=parsed.hostname, port=parsed.port, model=None, server_status=model_path, inference_status="IDLE", stats={}, models=[])
    provider = str((run or {}).get("actual_provider") or "").lower()
    active = str((run or {}).get("state") or "").upper() in {"ACCEPTED", "BASELINING", "RESEARCHING", "PLANNING", "BUILDING", "VERIFYING", "REVIEWING", "DECIDING", "RUNNING", "ACTIVE"}
    observed_lm = provider in {"lmstudio", "local_lmstudio"} and active
    stats = _approved_stats(run)
    model = (run or {}).get("actual_model") or (run or {}).get("resolved_model") if observed_lm else None
    return envelope("LMSTUDIO_API", sampled_at, "LIVE", host=parsed.hostname, port=parsed.port, server_status="ONLINE", inference_status="GENERATING" if observed_lm else "IDLE", model=model, models=models, model_endpoint=model_path, stats=stats, stats_source=stats.get("stats_source", "NOT_AVAILABLE"), correlation={"project_id": run.get("project_id") if observed_lm else None, "run_id": run.get("run_id") if observed_lm else None, "attempt_id": run.get("attempt_id") if observed_lm else None, "stage": run.get("current_job") if observed_lm else None, "provider": provider if observed_lm else None})


def _build(run, events):
    gpu = gpu_telemetry()
    lmstudio = lmstudio_telemetry(run or {}, events)
    process_names = [str(item.get("process_name") or "").lower() for device in gpu.get("gpus", []) for item in device.get("processes", [])]
    correlated_process = any("lmstudio" in name or "llm" in name for name in process_names)
    if lmstudio.get("inference_status") == "GENERATING":
        gpu["inference_correlation"] = "HIGH" if correlated_process else "NOT_CORRELATED"
        lmstudio["gpu_offload"] = "PROVEN" if correlated_process else "NOT_PROVEN"
    else:
        gpu["inference_correlation"] = "NOT_CORRELATED"
        lmstudio["gpu_offload"] = "NOT_APPLICABLE"
    return {
        "contract": CONTRACT, "version": "v1", "sampled_at": utc_now(), "source": "CONTROL_TOWER_READ_ONLY",
        "age_ms": 0, "freshness": "LIVE", "run": {"project_id": run.get("project_id") if run else None, "run_id": run.get("run_id") if run else None, "attempt_id": run.get("attempt_id") if run else None, "stage": run.get("current_job") if run else None, "provider": (run or {}).get("actual_provider") or (run or {}).get("selected_provider") if run else None, "model": (run or {}).get("actual_model") or (run or {}).get("resolved_model") if run else None},
        "proxmox": proxmox_telemetry(run or {}), "gpus": gpu.get("gpus", []), "gpu_telemetry": gpu, "lmstudio": lmstudio,
        "architecture": {"n8n_sole_control_plane": True, "second_sor": False, "runtime_dashboard_writes": 0, "no_private_cot_storage": True},
    }


class TelemetryCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._sampled_monotonic = 0.0
        self._value = None
        self._run_id = None

    def get(self, run, events):
        current = time.monotonic()
        run_id = (run or {}).get("run_id")
        with self._lock:
            if self._value is not None and self._run_id == run_id and current - self._sampled_monotonic < SAMPLE_CACHE_SECONDS:
                value = json.loads(json.dumps(self._value))
                age = int((current - self._sampled_monotonic) * 1000)
                value["age_ms"] = age
                value["freshness"] = "LIVE" if current - self._sampled_monotonic <= STALE_AFTER_SECONDS else "STALE"
                for key in ("proxmox", "gpu_telemetry", "lmstudio"):
                    if isinstance(value.get(key), dict):
                        value[key]["age_ms"] = age
                        if value[key].get("status") == "LIVE":
                            value[key]["freshness"] = value["freshness"]
                return value
            value = _build(run, events)
            self._value = value
            self._run_id = run_id
            self._sampled_monotonic = current
            return json.loads(json.dumps(value))


CACHE = TelemetryCache()


def runtime_telemetry(run=None, events=None):
    return CACHE.get(run or {}, events or [])
