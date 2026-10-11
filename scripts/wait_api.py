"""Wait for three ready Pods and matching ready Service endpoints after a rollout."""
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
KUBECTL = str(ROOT / ".local/bin/kubectl") if (ROOT / ".local/bin/kubectl").is_file() else "kubectl"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicas", type=int, default=3)
    args = parser.parse_args()
    base = [KUBECTL, "--kubeconfig", str(ROOT/".local/kubeconfig"), "-n", "cloudlab", "get"]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        pods = json.loads(subprocess.check_output([*base,"pods","-l","app=api","-o","json"]))["items"]
        ready = [pod for pod in pods if not pod["metadata"].get("deletionTimestamp") and any(
            item["type"] == "Ready" and item["status"] == "True" for item in pod["status"].get("conditions", []))]
        slices = json.loads(subprocess.check_output([*base,"endpointslices","-l","kubernetes.io/service-name=api","-o","json"]))["items"]
        addresses = {address for item in slices for endpoint in item.get("endpoints", [])
                     if endpoint.get("conditions", {}).get("ready") and not endpoint.get("conditions", {}).get("terminating")
                     for address in endpoint["addresses"]}
        pod_ips = {pod["status"]["podIP"] for pod in ready}
        if len(pods) == len(ready) == args.replicas and addresses == pod_ips:
            print(f"API stable: {len(ready)} ready Pods, matching Service endpoints.")
            return
        time.sleep(.5)
    raise SystemExit("API Pod/EndpointSlice state did not converge.")


if __name__ == "__main__":
    main()
