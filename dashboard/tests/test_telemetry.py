import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import telemetry


class FakeProxmoxClient:
    def __init__(self, values):
        self.values = iter(values)

    def get(self, path, query=None, timeout=4):
        if path.endswith("rrddata"):
            return 200, {"data": []}
        return 200, {"data": next(self.values)}


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.env = dict(os.environ)
        telemetry._guest_ring = telemetry._Ring()
        telemetry._gpu_ring = telemetry._Ring()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)

    def configure_proxmox(self):
        os.environ.update({
            "PROXMOX_API_BASE": "https://pve:8006/api2/json",
            "PROXMOX_NODE": "pve",
            "PROXMOX_ALLOWED_HOSTS": "pve",
            "PROXMOX_API_TOKEN_ID": "monitor@pam!control-tower",
            "PROXMOX_API_TOKEN_SECRET": "fixture-secret",
            "MORPHEUS_RUNTIME_GUESTS": json.dumps({"opencode-builder-8001": [{"node": "pve", "vmid": 8001, "type": "lxc"}]}),
        })

    def test_proxmox_maps_real_fields_and_network_rate(self):
        self.configure_proxmox()
        samples = [
            {"vmid": 8001, "name": "builder", "status": "running", "cpu": 0.37, "cpus": 2, "mem": 2, "maxmem": 10, "swap": 0, "maxswap": 4, "disk": 3, "maxdisk": 20, "netin": 100, "netout": 50, "uptime": 120},
            {"vmid": 8001, "name": "builder", "status": "running", "cpu": 0.42, "cpus": 2, "mem": 4, "maxmem": 10, "swap": 1, "maxswap": 4, "disk": 3, "maxdisk": 20, "netin": 300, "netout": 70, "uptime": 122},
        ]
        with patch.object(telemetry, "_JSONClient", return_value=FakeProxmoxClient(samples)), patch.object(telemetry, "utc_now", side_effect=["2026-08-28T10:00:00+00:00", "2026-08-28T10:00:02+00:00"]):
            first = telemetry.proxmox_telemetry({"backend": "opencode-builder-8001"})
            second = telemetry.proxmox_telemetry({"backend": "opencode-builder-8001"})
        guest = second["runtime_guests"][0]
        self.assertEqual(first["active_guest"]["vmid"], 8001)
        self.assertEqual(guest["cpu"]["value"], 42.0)
        self.assertEqual(guest["network"]["in_rate"]["value"], 100.0)

    def test_proxmox_stopped_and_missing_optional_fields_are_truthful(self):
        self.configure_proxmox()
        sample = {"vmid": 8001, "status": "stopped", "name": "builder", "maxmem": 10}
        with patch.object(telemetry, "_JSONClient", return_value=FakeProxmoxClient([sample])):
            result = telemetry.proxmox_telemetry({"backend": "opencode-builder-8001"})
        guest = result["runtime_guests"][0]
        self.assertEqual(result["status"], "STOPPED")
        self.assertEqual(guest["proxmox_status"], "STOPPED")
        self.assertIsNone(guest["ram"]["used"]["value"])
        self.assertEqual(guest["ram"]["used"]["status"], "NOT_SUPPORTED")

    def test_proxmox_auth_failure_is_not_guest_failure(self):
        self.configure_proxmox()
        with patch.object(telemetry, "_JSONClient", side_effect=telemetry._HTTPError(401)):
            result = telemetry.proxmox_telemetry({"backend": "opencode-builder-8001"})
        self.assertEqual(result["error_code"], "PROXMOX_AUTH_FAILED")

    def test_guest_without_canonical_mapping_is_unassigned(self):
        self.configure_proxmox()
        with patch.dict(os.environ, {"MORPHEUS_RUNTIME_GUESTS": "{}"}):
            result = telemetry.proxmox_telemetry({"backend": "unknown-backend"})
        self.assertEqual(result["error_code"], "GUEST_NOT_MAPPED")
        self.assertIsNone(result["active_guest"])

    def test_nvidia_csv_supports_multiple_gpus_and_unsupported_fields(self):
        gpu_rows = "0, GPU-a, RTX A, 555, 8192, 91, 80, 4096, 69, 126, 1800, 700, [Not Supported]\n1, GPU-b, RTX B, 555, 16384, 2, 4, 512, 45, N/A, 1000, 500, 30"
        processes = "123, lmstudio, 2048\n"
        with patch.dict(os.environ, {"NVIDIA_GPU_HOST": "127.0.0.1"}, clear=False), patch.object(telemetry.shutil, "which", return_value="/usr/bin/nvidia-smi"), patch.object(telemetry, "_run_fixed", side_effect=[(gpu_rows, None), (processes, None)]):
            result = telemetry.gpu_telemetry()
        self.assertEqual(result["status"], "LIVE")
        self.assertEqual(len(result["gpus"]), 2)
        self.assertEqual(result["gpus"][0]["uuid"], "GPU-a")
        self.assertEqual(result["gpus"][0]["fan"]["status"], "NOT_SUPPORTED")
        self.assertEqual(result["gpus"][0]["processes"][0]["pid"], 123)

    def test_nvidia_host_key_failure_is_unreachable_not_driver_failure(self):
        with patch.object(telemetry.subprocess, "run", return_value=type("Result", (), {"returncode": 255, "stdout": "", "stderr": "Host key verification failed."})()):
            result = telemetry._run_fixed(["ssh", "xxammaxx@192.168.1.50", "nvidia-smi"])
        self.assertEqual(result[1], "GPU_HOST_UNREACHABLE")

    def test_lmstudio_requires_actual_morpheus_provider_and_redacts_reasoning(self):
        os.environ.update({"LMSTUDIO_BASE_URL": "http://lmstudio:1234", "LMSTUDIO_ALLOWED_HOSTS": "lmstudio"})
        with patch.object(telemetry, "_lm_models", return_value=([{"id": "qwen", "loaded": True}], "/api/v1/models")):
            generating = telemetry.lmstudio_telemetry({"run_id": "run-1", "state": "BUILDING", "actual_provider": "lmstudio", "actual_model": "qwen", "reasoning_content": "private"}, [])
            idle = telemetry.lmstudio_telemetry({"run_id": "run-2", "state": "BUILDING", "selected_provider": "lmstudio"}, [])
        self.assertEqual(generating["inference_status"], "GENERATING")
        self.assertEqual(generating["model"], "qwen")
        self.assertEqual(idle["inference_status"], "IDLE")
        self.assertNotIn("reasoning_content", json.dumps(generating))

    def test_lmstudio_unreachable_is_optional_and_truthful(self):
        os.environ.update({"LMSTUDIO_BASE_URL": "http://lmstudio:1234", "LMSTUDIO_ALLOWED_HOSTS": "lmstudio"})
        with patch.object(telemetry, "_lm_models", return_value=([], "UNREACHABLE")):
            result = telemetry.lmstudio_telemetry({}, [])
        self.assertEqual(result["status"], "UNREACHABLE")
        self.assertEqual(result["server_status"], "UNREACHABLE")
        self.assertEqual(result["inference_status"], "IDLE")

    def test_gpu_busy_does_not_prove_lmstudio_inference(self):
        gpu = {"status": "LIVE", "gpus": [{"processes": [{"process_name": "python", "memory_used": {"value": 100}}]}]}
        with patch.object(telemetry, "gpu_telemetry", return_value=gpu), patch.object(telemetry, "lmstudio_telemetry", return_value={"status": "LIVE", "inference_status": "IDLE"}):
            result = telemetry._build({"run_id": "run-1", "state": "BUILDING", "actual_provider": "openai"}, [])
        self.assertEqual(result["lmstudio"]["inference_status"], "IDLE")
        self.assertEqual(result["gpu_telemetry"]["inference_correlation"], "NOT_CORRELATED")

    def test_correlated_lmstudio_process_proves_gpu_offload_only_for_active_run(self):
        gpu = {"status": "LIVE", "gpus": [{"processes": [{"process_name": "lmstudio", "memory_used": {"value": 100}}]}]}
        lm = {"status": "LIVE", "inference_status": "GENERATING"}
        with patch.object(telemetry, "gpu_telemetry", return_value=gpu), patch.object(telemetry, "lmstudio_telemetry", return_value=lm):
            result = telemetry._build({"run_id": "run-1", "state": "BUILDING", "actual_provider": "lmstudio"}, [])
        self.assertEqual(result["lmstudio"]["gpu_offload"], "PROVEN")
        self.assertEqual(result["gpu_telemetry"]["inference_correlation"], "HIGH")

    def test_cache_is_bounded_and_reuses_same_run(self):
        cache = telemetry.TelemetryCache()
        value = {"sampled_at": "2026-08-28T10:00:00+00:00", "gpus": [], "proxmox": {}, "lmstudio": {}}
        with patch.object(telemetry, "_build", return_value=value) as build:
            cache.get({"run_id": "run-1"}, [])
            cache.get({"run_id": "run-1"}, [])
        self.assertEqual(build.call_count, 1)

    def test_contract_is_versioned(self):
        contract = json.loads((Path(__file__).parents[1] / "contracts/autodev.runtime-telemetry.v1.schema.json").read_text())
        self.assertEqual(contract["$id"], "autodev.runtime-telemetry.v1")
        self.assertIn("gpus", contract["required"])


if __name__ == "__main__":
    unittest.main()
