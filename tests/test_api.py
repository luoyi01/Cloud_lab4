import importlib.util
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from redis import Redis


def test_application_module_exists():
    assert importlib.util.find_spec("app") is not None, "API application is not implemented"


@pytest.fixture
def settings():
    from app.config import Settings
    return Settings(redis_host=os.getenv("REDIS_HOST", "redis"),
                    redis_password=os.getenv("REDIS_PASSWORD", ""),
                    redis_db=15, redis_prefix=f"test:{uuid.uuid4().hex}",
                    instance="test-instance", node="test-node")


@pytest.fixture
def client(settings):
    from app.main import create_app
    with TestClient(create_app(settings)) as c:
        yield c
    redis = Redis(host=settings.redis_host, password=settings.redis_password or None,
                  db=15, decode_responses=True)
    keys = list(redis.scan_iter(match=f"{settings.redis_prefix}:*"))
    if keys:
        redis.delete(*keys)
    redis.close()


def test_message_roundtrip_and_trimming(client):
    r = client.post("/api/messages", json={"author": "  同学  ", "content": "  第一条留言  "})
    assert r.status_code == 201
    message = r.json()["message"]
    assert message["author"] == "同学"
    assert message["content"] == "第一条留言"
    assert message["id"] > 0 and message["created_at"]
    listing = client.get("/api/messages").json()
    assert listing["items"] == [message]
    assert listing["total"] == 1
    assert listing["next_cursor"] is None


@pytest.mark.parametrize("data", [
    {"author": "  ", "content": "ok"}, {"author": "a", "content": "\n"},
    {"author": "a" * 31, "content": "ok"}, {"author": "a", "content": "x" * 301},
    {"author": 12, "content": "ok"}, {"author": "a", "content": None},
])
def test_invalid_input_is_rejected_without_writing(client, data):
    assert client.post("/api/messages", json=data).status_code == 422
    assert client.get("/api/messages").json()["total"] == 0


def test_cursor_pagination_survives_new_messages(client):
    for i in range(5):
        client.post("/api/messages", json={"author": "a", "content": str(i)})
    page1 = client.get("/api/messages?limit=2").json()
    assert [x["content"] for x in page1["items"]] == ["4", "3"]
    client.post("/api/messages", json={"author": "a", "content": "new"})
    page2 = client.get(f'/api/messages?limit=2&before={page1["next_cursor"]}').json()
    assert [x["content"] for x in page2["items"]] == ["2", "1"]
    assert client.get("/api/messages?limit=0").status_code == 422
    assert client.get("/api/messages?before=0").status_code == 422


def test_concurrent_creates_are_atomic(client):
    def write(i):
        response = client.post("/api/messages", json={"author": "parallel", "content": str(i)})
        assert response.status_code == 201
        return response.json()["message"]["id"]
    with ThreadPoolExecutor(max_workers=10) as pool:
        ids = list(pool.map(write, range(40)))
    assert len(set(ids)) == 40
    page = client.get("/api/messages?limit=50").json()
    assert page["total"] == 40 and len(page["items"]) == 40


def test_concurrent_counter_keeps_all_increments(client):
    with ThreadPoolExecutor(max_workers=10) as pool:
        counts = list(pool.map(lambda _: client.post("/api/visits").json()["count"], range(40)))
    assert sorted(counts) == list(range(1, 41))


def test_identity_and_health(client):
    identity = client.get("/api/whoami").json()
    assert identity["instance"] == "test-instance" and identity["node"] == "test-node"
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_messages_survive_application_recreation(client, settings):
    from app.main import create_app
    expected = client.post("/api/messages", json={"author": "a", "content": "persistent"}).json()["message"]
    with TestClient(create_app(settings)) as second:
        assert second.get("/api/messages").json()["items"] == [expected]


def test_storage_failure_affects_readiness_but_not_liveness():
    from app.config import Settings
    from app.main import create_app
    with TestClient(create_app(Settings(redis_host="127.0.0.1", redis_port=1))) as c:
        assert c.get("/health/live").status_code == 200
        assert c.get("/health/ready").status_code == 503
        r = c.get("/api/messages")
        assert r.status_code == 503
        assert "Traceback" not in r.text and "127.0.0.1" not in r.text
