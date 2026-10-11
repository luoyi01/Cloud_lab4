"""Fetch the fixed official amd64 metrics image through WSL curl into OCI format.

This avoids Docker Desktop's slow registry connection and never changes its proxy.
Every manifest/config/layer is checked against the publisher's SHA-256 digest.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".local/metrics-oci"
REGISTRY = "https://registry.k8s.io/v2/metrics-server/metrics-server"
INDEX = "sha256:d9862115e7c7881280d3d75ca26bda8ffc0fc213315979575bf23ce9826205c0"
AMD64 = "sha256:25d291fde59974547bac6f07fa9d6cf6f5bedd1f19d60c893311c5e741e0a42f"
IMAGE = "registry.k8s.io/metrics-server/metrics-server:v0.9.0"


def fetch(digest, endpoint):
    dest = STORE / "blobs/sha256" / digest.removeprefix("sha256:")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest() != digest.split(":")[1]:
        partial = dest.with_suffix(".partial")
        subprocess.run(["curl", "-fLsS", "--retry", "3", "--retry-all-errors", "--max-time", "900", "--continue-at", "-",
                        f"{REGISTRY}/{endpoint}/{digest}", "-o", str(partial)], check=True)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != digest.split(":")[1]:
            raise ValueError(f"Publisher digest mismatch: {digest}")
        partial.replace(dest)
    print("Verified", digest, flush=True)
    return dest


def main():
    index = json.loads(fetch(INDEX, "manifests").read_bytes())
    descriptor = next(m for m in index["manifests"] if m.get("platform") == {"architecture": "amd64", "os": "linux"})
    assert descriptor["digest"] == AMD64
    manifest = json.loads(fetch(AMD64, "manifests").read_bytes())
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda item: fetch(item["digest"], "blobs"), [manifest["config"], *manifest["layers"]]))
    descriptor["annotations"] = {"org.opencontainers.image.ref.name": IMAGE}
    (STORE / "index.json").write_text(json.dumps({"schemaVersion": 2, "manifests": [descriptor]}))
    (STORE / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
    with tarfile.open(ROOT / ".local/metrics-image.tar", "w") as archive:
        for path in STORE.rglob("*"):
            if path.is_file() and not path.name.endswith(".partial"):
                archive.add(path, arcname=path.relative_to(STORE), recursive=False)
    print("Verified official metrics OCI archive ready.", flush=True)


if __name__ == "__main__":
    import fcntl
    STORE.mkdir(parents=True, exist_ok=True)
    with (STORE / ".fetch.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
