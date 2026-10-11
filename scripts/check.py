"""Check the real public endpoint; no client retries conceal failures."""
import argparse
import json
import uuid
from urllib.request import Request, urlopen


def request(url, path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = Request(url.rstrip("/") + path, data=data,
                  headers={"Content-Type": "application/json", "Connection": "close"})
    with urlopen(req, timeout=3) as response:
        return json.load(response)


def check(url, expected):
    identities = {request(url, "/api/whoami")["instance"] for _ in range(60)}
    assert len(identities) == expected, f"expected {expected} instances, got {sorted(identities)}"
    marker = "复现检查-" + uuid.uuid4().hex[:8]
    result = request(url, "/api/messages", {"author": "实验验证", "content": marker})
    message_id = result["message"]["id"]
    # The latest message must be visible through every replica selected by the entry point.
    readers = set()
    for _ in range(60):
        result = request(url, "/api/messages?limit=50")
        assert any(item["id"] == message_id and item["content"] == marker for item in result["items"])
        readers.add(result["instance"])
    assert readers == identities
    first = request(url, "/api/visits", {})["count"]
    assert request(url, "/api/visits", {})["count"] == first + 1
    print(json.dumps({"url": url, "instances": sorted(identities), "replicas": len(identities),
                      "shared_message_id": message_id, "marker": marker, "checks": "passed"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--replicas", type=int, default=3)
    args = parser.parse_args()
    check(args.url, args.replicas)
