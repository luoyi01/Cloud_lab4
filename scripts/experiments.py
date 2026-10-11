"""Controlled experiments against lab-owned resources, with raw evidence."""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
KUBE = str(ROOT / ".local/kubeconfig")
KUBECTL = str(ROOT / ".local/bin/kubectl") if (ROOT / ".local/bin/kubectl").is_file() else "kubectl"
OUT = ROOT / "results"
URLS = {"compose": "http://127.0.0.1:8090", "k8s": "http://127.0.0.1:8080"}


def now():
    return datetime.now(timezone.utc).isoformat()


def command(*args, allow_failure=False, payload=None):
    result = subprocess.run(args, cwd=ROOT, text=True, input=payload, capture_output=True)
    if result.returncode and not allow_failure:
        raise RuntimeError(f"{' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def k(*args, **kwargs):
    return command(KUBECTL, "--kubeconfig", KUBE, "-n", "cloudlab", *args, **kwargs)


def dc(*args, **kwargs):
    return command("docker", "compose", "--env-file", str(ROOT / ".env"), "-f",
                   str(ROOT / "docker/compose.yaml"), *args, **kwargs)


def save(path, value):
    path = OUT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def http(url, path="/api/messages?limit=1", payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = Request(url + path, data=data, headers={"Content-Type": "application/json", "Connection": "close"})
    with urlopen(req, timeout=2) as response:
        return response.status, json.load(response)


def ready(url):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if http(url)[0] == 200:
                return
        except Exception:
            pass
        time.sleep(.25)
    raise TimeoutError(f"Endpoint never ready: {url}")


def probe(url, duration, path, interval=.2, workers=1):
    """Each worker sends one request per interval; no retries, fresh connections."""
    start = time.monotonic()
    rows = []
    lock = threading.Lock()

    def run(worker):
        scheduled = start
        while time.monotonic() - start < duration:
            begun = time.monotonic()
            row = {"utc": now(), "elapsed_s": round(begun - start, 4), "worker": worker,
                   "status": 0, "latency_ms": 0, "instance": "", "node": "", "error": ""}
            try:
                status, data = http(url)
                row.update(status=status, instance=data.get("instance", ""), node=data.get("node", ""))
            except HTTPError as error:
                row.update(status=error.code, error=str(error))
            except Exception as error:
                row["error"] = f"{type(error).__name__}: {error}"
            row["latency_ms"] = round((time.monotonic() - begun) * 1000, 3)
            with lock:
                rows.append(row)
            # Skip missed slots instead of bursting after a timeout.
            scheduled += interval
            if scheduled < time.monotonic():
                scheduled = time.monotonic()
            time.sleep(max(0, scheduled - time.monotonic()))

    threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    rows.sort(key=lambda row: row["elapsed_s"])
    dest = OUT / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    good = [row for row in rows if row["status"] == 200]
    latencies = sorted(row["latency_ms"] for row in good)
    summary = {"url": url, "duration_s": duration, "workers": workers, "interval_s": interval,
               "requests": len(rows), "success": len(good), "errors": len(rows) - len(good),
               "success_percent": round(100 * len(good) / len(rows), 3),
               "p50_ms": statistics.median(latencies) if latencies else None,
               "p95_ms": latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
               "instances": sorted({row["instance"] for row in good}),
               "client_retries": 0, "csv": str(path)}
    save(str(path).replace(".csv", ".summary.json"), summary)
    return summary


def launch_probe(scheme, duration, path, workers=1):
    result = {}
    thread = threading.Thread(target=lambda: result.update(probe(URLS[scheme], duration, path, workers=workers)))
    thread.start()
    return thread, result


def pods():
    return json.loads(k("get", "pods", "-l", "app=api", "-o", "json").stdout)["items"]


def is_ready(pod):
    return not pod["metadata"].get("deletionTimestamp") and any(
        c["type"] == "Ready" and c["status"] == "True" for c in pod["status"].get("conditions", []))


def scale(scheme, replicas):
    begun = time.monotonic()
    if scheme == "compose":
        dc("up", "-d", "--scale", f"api={replicas}", "--wait", "--wait-timeout", "120")
    else:
        k("scale", "deployment/api", f"--replicas={replicas}")
        k("rollout", "status", "deployment/api", "--timeout=120s")
        deadline = time.monotonic() + 120
        while len([p for p in pods() if is_ready(p)]) != replicas:
            if time.monotonic() > deadline:
                raise TimeoutError("Ready replicas did not match target")
            time.sleep(.5)
    ready(URLS[scheme])
    return round(time.monotonic() - begun, 3)


def restore_all(*actions):
    """Attempt every recovery independently and report all failures."""
    errors = []
    for action in actions:
        try:
            action()
        except Exception as error:
            errors.append(str(error))
    if errors:
        raise RuntimeError("Recovery failures (other actions were still attempted):\n" + "\n".join(errors))


def restore_compose():
    scale("compose", 3)


def restore_k8s(restart=False):
    actions = [lambda: k("scale", "deployment/web", "--replicas=1"),
               lambda: k("scale", "deployment/api", "--replicas=3")]
    if restart:
        actions.append(lambda: k("rollout", "restart", "deployment/api"))
    actions.extend([lambda: k("rollout", "status", "deployment/api", "--timeout=120s"),
                    lambda: k("rollout", "status", "deployment/web", "--timeout=120s"),
                    lambda: ready(URLS["k8s"])])
    restore_all(*actions)


def resources(scheme):
    if scheme == "compose":
        ids = dc("ps", "-q").stdout.split()
        result = command("docker", "stats", "--no-stream", "--format", "{{json .}}", *ids)
        return {"utc": now(), "source": "docker stats --no-stream", "containers":
                [json.loads(line) for line in result.stdout.splitlines()]}
    result = k("get", "--raw", "/apis/metrics.k8s.io/v1beta1/namespaces/cloudlab/pods")
    return {"utc": now(), "source": "metrics.k8s.io/v1beta1", "metrics": json.loads(result.stdout)}


def capture(name):
    commands = [("nodes", [KUBECTL, "--kubeconfig", KUBE, "get", "nodes", "-o", "wide"]),
                ("workloads", [KUBECTL, "--kubeconfig", KUBE, "-n", "cloudlab", "get", "deploy,sts,pods,svc,pvc,pdb", "-o", "wide"]),
                ("events", [KUBECTL, "--kubeconfig", KUBE, "-n", "cloudlab", "get", "events", "--sort-by=.metadata.creationTimestamp"])]
    path = OUT / name
    path.mkdir(parents=True, exist_ok=True)
    for label, args in commands:
        result = command(*args)
        (path / f"{label}.txt").write_text(f"UTC {now()}\n$ {' '.join(args).replace(KUBE, '.local/kubeconfig')}\n{result.stdout}", encoding="utf-8")


def self_heal():
    scale("k8s", 3)
    initial = pods()
    target = next(p for p in initial if is_ready(p))
    before = {p["metadata"]["uid"] for p in initial}
    thread, summary = launch_probe("k8s", 45, "self-heal/requests.csv")
    time.sleep(5)
    event = {"fault_utc": now(), "old_name": target["metadata"]["name"], "old_uid": target["metadata"]["uid"],
             "method": "kubectl delete pod --wait=false (default graceful deletion)"}
    begun = time.monotonic()
    k("delete", "pod", target["metadata"]["name"], "--wait=false")
    deadline = begun + 120
    while time.monotonic() < deadline:
        replacement = next((p for p in pods() if p["metadata"]["uid"] not in before and is_ready(p)), None)
        if replacement:
            event.update(new_name=replacement["metadata"]["name"], new_uid=replacement["metadata"]["uid"],
                         new_node=replacement["spec"]["nodeName"], replacement_ready_s=round(time.monotonic()-begun, 3))
            break
        time.sleep(.25)
    else:
        raise TimeoutError("Replacement Pod was not ready")
    thread.join()
    save("self-heal/event.json", {**event, "traffic": summary})
    capture("self-heal")
    print("Pod self-heal:", json.dumps(event, ensure_ascii=False), flush=True)


def _scale_experiment(duration=60):
    records = []
    for scheme in ("compose", "k8s"):
        # Only one path's API/Web runs during the matched workload. Keep both data stores.
        if scheme == "compose":
            k("scale", "deployment/api", "deployment/web", "--replicas=0")
            k("wait", "--for=delete", "pod", "-l", "app=api", "--timeout=120s")
            k("wait", "--for=delete", "pod", "-l", "app=web", "--timeout=120s")
        else:
            dc("stop", "api", "web")
            k("scale", "deployment/web", "--replicas=1")
            k("rollout", "status", "deployment/web", "--timeout=120s")
        for step, replicas in enumerate((1, 3, 5, 3), 1):
            elapsed = scale(scheme, replicas)
            if step == 1:
                seed = (ROOT / "scripts/seed_benchmark.py").read_text(encoding="utf-8")
                if scheme == "compose":
                    seeded = dc("exec", "-T", "api", "python", "-c", seed)
                else:
                    seeded = k("exec", "deployment/api", "--", "python", "-c", seed)
                dataset = json.loads(seeded.stdout)
                save(f"scale/{scheme}-dataset.json", dataset)
                if scheme == "k8s":
                    assert dataset == json.loads((OUT / "scale/compose-dataset.json").read_text()), "Datasets differ"
            name = f"scale/{scheme}-{step}-{replicas}"
            thread, summary = launch_probe(scheme, duration + 5, name + ".csv", workers=4)
            samples = []
            started = time.monotonic()
            # Five observations, not five independent experimental runs.
            for sample_at in (20, 30, 40, 50, 60):
                sample_at *= duration / 60
                time.sleep(max(0, started + sample_at - time.monotonic()))
                samples.append(resources(scheme))
            thread.join()
            record = {"scheme": scheme, "replicas": replicas, "step": step, "scale_ready_s": elapsed,
                      "resource_samples": samples, "traffic": summary}
            records.append(record)
            save(name + ".resources.json", record)
            print(f"Scale {scheme} {replicas}: {elapsed}s, {summary['errors']} errors", flush=True)
    save("scale/summary.json", records)
    capture("scale")


def scale_experiment(duration=60):
    previous_env = os.environ.get("REDIS_PREFIX")
    config = json.loads(k("get", "configmap", "cloudlab-config", "-o", "json").stdout)
    previous_prefix = config["data"].get("REDIS_PREFIX", "cloudlab")
    os.environ["REDIS_PREFIX"] = "cloudlab-benchmark"
    try:
        k("patch", "configmap", "cloudlab-config", "--type=merge", "-p", json.dumps({"data": {"REDIS_PREFIX": "cloudlab-benchmark"}}))
        _scale_experiment(duration)
    finally:
        if previous_env is None:
            os.environ.pop("REDIS_PREFIX", None)
        else:
            os.environ["REDIS_PREFIX"] = previous_env
        restore_all(lambda: k("patch", "configmap", "cloudlab-config", "--type=merge", "-p",
                              json.dumps({"data": {"REDIS_PREFIX": previous_prefix}})),
                    restore_compose, lambda: restore_k8s(restart=True))


def persistence():
    for scheme in ("compose", "k8s"):
        marker = f"持久化验证-{scheme}-{int(time.time())}"
        _, created = http(URLS[scheme], "/api/messages", {"author": "实验验证", "content": marker})
        item = created["message"]
        time.sleep(2)  # Redis appendfsync everysec; this is a graceful restart test.
        begun = time.monotonic()
        if scheme == "compose":
            dc("restart", "redis")
        else:
            k("delete", "pod", "redis-0")
            k("rollout", "status", "statefulset/redis", "--timeout=120s")
        ready(URLS[scheme])
        _, result = http(URLS[scheme], "/api/messages?limit=50")
        assert any(m == item for m in result["items"]), "Persisted message was lost"
        event = {"scheme": scheme, "utc": now(), "message": item, "readback": "identical",
                 "restart_to_endpoint_ready_s": round(time.monotonic()-begun, 3),
                 "scope": "graceful Redis restart; not power loss or storage-node failure"}
        save(f"persistence/{scheme}.json", event)
        print("Persistence:", scheme, "passed", flush=True)
    capture("persistence")


def pdb_experiment():
    try:
        scale("k8s", 2)
        deadline = time.monotonic() + 30
        while True:
            status = json.loads(k("get", "pdb", "api", "-o", "json").stdout)["status"]
            if status.get("currentHealthy") == 2 and status.get("disruptionsAllowed") == 0:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("PDB budget did not become zero")
            time.sleep(.5)
        target = next(p for p in pods() if is_ready(p))
        name = target["metadata"]["name"]
        eviction = json.dumps({"apiVersion": "policy/v1", "kind": "Eviction", "metadata": {"name": name, "namespace": "cloudlab"}})
        result = k("create", "--raw", f"/api/v1/namespaces/cloudlab/pods/{name}/eviction", "-f", "-", payload=eviction, allow_failure=True)
        assert result.returncode != 0 and "disruption budget" in result.stderr.lower(), result.stderr
        assert any(p["metadata"]["uid"] == target["metadata"]["uid"] and is_ready(p) for p in pods())
        save("pdb/eviction.json", {"utc": now(), "replicas": 2, "minAvailable": 2,
                                   "status": status, "pod": name, "exit_code": result.returncode,
                                   "stderr": result.stderr, "same_pod_still_ready": True})
        capture("pdb")
        print("PDB: eviction rejected at two healthy replicas", flush=True)
    finally:
        scale("k8s", 3)


def worker_failure():
    scale("k8s", 3)
    node = "cloudlab-worker2"
    initial = pods()
    affected = [p["metadata"]["name"] for p in initial if p["spec"].get("nodeName") == node and is_ready(p)]
    assert affected, "No API Pod on fault worker; check scheduling before injection"
    for label in ("web", "redis"):
        items = json.loads(k("get", "pod", "-l", f"app={label}", "-o", "json").stdout)["items"]
        assert all(p["spec"]["nodeName"] != node for p in items)
    capture("node-failure/before")
    thread, summary = launch_probe("k8s", 150, "node-failure/requests.csv")
    time.sleep(5)
    event = {"fault_utc": now(), "worker": node, "affected_api_pods": affected,
             "method": "docker stop Kind worker container", "toleration_seconds": 20,
             "scope": "one simulated API worker on the same physical host"}
    begun = time.monotonic()
    try:
        command("docker", "stop", "-t", "1", node)
        deadline = begun + 120
        saw_not_ready = False
        while time.monotonic() < deadline:
            state = json.loads(k("get", "node", node, "-o", "json").stdout)
            if not any(c["type"] == "Ready" and c["status"] == "True" for c in state["status"]["conditions"]):
                saw_not_ready = True
                event.setdefault("node_not_ready_s", round(time.monotonic()-begun, 3))
            active = [p for p in pods() if is_ready(p) and p["spec"].get("nodeName") != node]
            if saw_not_ready and len(active) == 3:
                event.update(all_api_ready_on_survivor_s=round(time.monotonic()-begun, 3),
                             surviving_pods=[p["metadata"]["name"] for p in active])
                break
            time.sleep(1)
        else:
            raise TimeoutError("API was not rescheduled to the surviving worker")
        capture("node-failure/during")
        thread.join()
        save("node-failure/event.json", {**event, "traffic": summary})
        print("Worker failure:", json.dumps(event, ensure_ascii=False), flush=True)
    finally:
        command("docker", "start", node)
        k("wait", "--for=condition=Ready", f"node/{node}", "--timeout=120s")
        capture("node-failure/after")


def compose_delete():
    scale("compose", 3)
    target = dc("ps", "-q", "api").stdout.split()[0]
    thread, summary = launch_probe("compose", 40, "compose-delete/requests.csv")
    time.sleep(5)
    try:
        command("docker", "rm", "-f", target)
        time.sleep(15)
        remaining = dc("ps", "-q", "api").stdout.split()
        assert len(remaining) == 2, "Unexpected declarative controller in Compose"
        event = {"utc": now(), "removed_container": target[:12], "remaining_after_15s": len(remaining),
                 "auto_recreated_after_deletion": False}
    finally:
        scale("compose", 3)
    thread.join()
    save("compose-delete/event.json", {**event, "traffic": summary})
    print("Compose deletion: stays at 2 until compose up", flush=True)


def _warm_start():
    records = []
    # Redis and the cluster are kept running. Excludes pulls, builds, engine and cluster creation.
    for scheme in ("compose", "k8s"):
        scale(scheme, 3)
        for run in range(1, 6):
            if scheme == "compose":
                dc("stop", "api", "web")
            else:
                k("scale", "deployment/api", "deployment/web", "--replicas=0")
                k("wait", "--for=delete", "pod", "-l", "app=api", "--timeout=120s")
                k("wait", "--for=delete", "pod", "-l", "app=web", "--timeout=120s")
            begun = time.monotonic()
            if scheme == "compose":
                dc("start", "api", "web", "--wait", "--wait-timeout", "120")
            else:
                k("scale", "deployment/api", "--replicas=3")
                k("scale", "deployment/web", "--replicas=1")
                k("rollout", "status", "deployment/api", "--timeout=120s")
                k("rollout", "status", "deployment/web", "--timeout=120s")
            ready(URLS[scheme])
            row = {"scheme": scheme, "run": run, "utc": now(), "ready_s": round(time.monotonic()-begun, 3),
                   "scope": "warm stateless API(3)+Web(1) restart; Redis and platform stay running"}
            records.append(row)
            save("comparison/warm-start.json", records)
            print(f"Warm start {scheme} #{run}: {row['ready_s']}s", flush=True)


def warm_start():
    try:
        _warm_start()
    finally:
        restore_all(restore_compose, restore_k8s)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", choices=["self-heal", "scale", "persistence", "pdb", "node-failure", "compose-delete", "warm-start", "capture", "probe"])
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--scheme", choices=URLS, default="k8s")
    args = parser.parse_args()
    import fcntl
    with (ROOT / ".local/experiments.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        actions = {"self-heal": self_heal, "scale": lambda: scale_experiment(args.duration),
                   "persistence": persistence, "pdb": pdb_experiment, "node-failure": worker_failure,
                   "compose-delete": compose_delete, "warm-start": warm_start,
                   "capture": lambda: capture("deployment"),
                   "probe": lambda: print(json.dumps(probe(URLS[args.scheme], args.duration, "probe/requests.csv"), ensure_ascii=False))}
        actions[args.experiment]()
