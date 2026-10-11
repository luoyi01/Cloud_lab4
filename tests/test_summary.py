import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.summary import cpu_millicores, memory_bytes, summarize_resources
from scripts import experiments


class UnitsTest(unittest.TestCase):
    def test_cpu_and_memory_sources_have_consistent_units(self):
        self.assertEqual(cpu_millicores("15000000n"), 15)
        self.assertEqual(cpu_millicores("15m"), 15)
        self.assertEqual(cpu_millicores("1"), 1000)
        self.assertEqual(memory_bytes("2Mi"), 2 * 1024**2)
        self.assertEqual(memory_bytes("2MiB"), 2 * 1024**2)
        self.assertEqual(memory_bytes("2MB"), 2_000_000)

    def test_resource_total_keeps_app_and_api_scopes_distinct(self):
        docker = {"containers": [{"Name": "cloudlab-api-1", "CPUPerc": "1.50%", "MemUsage": "50MiB / 256MiB"},
                                 {"Name": "cloudlab-web-1", "CPUPerc": "0.50%", "MemUsage": "5MiB / 128MiB"}]}
        kubernetes = {"metrics": {"items": [
            {"metadata": {"name": "api-abc"}, "containers": [{"usage": {"cpu": "15000000n", "memory": "51200Ki"}}]},
            {"metadata": {"name": "web-abc"}, "containers": [{"usage": {"cpu": "5m", "memory": "5Mi"}}]}]}}
        expected = {"app_cpu_m": 20, "api_cpu_m": 15, "app_memory_mib": 55, "api_memory_mib": 50}
        self.assertEqual(summarize_resources(docker), expected)
        self.assertEqual(summarize_resources(kubernetes), expected)


class ProbeTest(unittest.TestCase):
    def test_every_http_error_is_recorded_without_hidden_retries(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                status = 200 if len(seen) % 2 == 0 else 503
                seen.append(status)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"instance": "test", "node": "local"}).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp, patch.object(experiments, "OUT", Path(temp)):
                result = experiments.probe(f"http://127.0.0.1:{server.server_port}", .2, "requests.csv", interval=.05)
                with (Path(temp) / "requests.csv").open(encoding="utf-8") as source:
                    rows = list(csv.DictReader(source))
                self.assertGreaterEqual(len(seen), 2)
                self.assertEqual(result["requests"], len(seen))
                self.assertEqual(result["errors"], seen.count(503))
                self.assertEqual([int(row["status"]) for row in rows], seen)
                self.assertEqual(result["client_retries"], 0)
        finally:
            server.shutdown()
            server.server_close()


class RecoveryTest(unittest.TestCase):
    def test_one_recovery_error_does_not_skip_the_other_platform(self):
        attempted = []

        def failed():
            attempted.append("compose")
            raise RuntimeError("injected recovery error")

        with self.assertRaisesRegex(RuntimeError, "injected recovery error"):
            experiments.restore_all(failed, lambda: attempted.append("k8s"))
        self.assertEqual(attempted, ["compose", "k8s"])

    def test_warm_start_restores_both_platforms_after_stop_failure(self):
        with patch.object(experiments, "scale"), patch.object(experiments, "dc", side_effect=RuntimeError("stop failed")), \
             patch.object(experiments, "restore_compose") as compose, patch.object(experiments, "restore_k8s") as kubernetes:
            with self.assertRaisesRegex(RuntimeError, "stop failed"):
                experiments.warm_start()
        compose.assert_called_once()
        kubernetes.assert_called_once()

    def test_compose_delete_restores_three_replicas_after_delete_failure(self):
        from types import SimpleNamespace
        with patch.object(experiments, "scale") as scale, \
             patch.object(experiments, "dc", return_value=SimpleNamespace(stdout="container-id")), \
             patch.object(experiments, "launch_probe"), patch.object(experiments.time, "sleep"), \
             patch.object(experiments, "command", side_effect=RuntimeError("delete failed")):
            experiments.launch_probe.return_value = (None, {})
            with self.assertRaisesRegex(RuntimeError, "delete failed"):
                experiments.compose_delete()
        self.assertEqual(scale.call_args_list, [unittest.mock.call("compose", 3), unittest.mock.call("compose", 3)])
