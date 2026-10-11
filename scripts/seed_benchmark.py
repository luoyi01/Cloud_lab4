"""Executed inside an API container; reset only the named synthetic dataset."""
import hashlib
import json
from app.config import Settings
from app.store import MessageStore, CREATE_MESSAGE

settings = Settings.from_env()
assert settings.redis_prefix == "cloudlab-benchmark", "Refuse to reset the normal application prefix"
store = MessageStore(settings)
prefix = settings.redis_prefix
keys = [f"{prefix}:sequence", f"{prefix}:messages", f"{prefix}:index"]
store.redis.delete(*keys, f"{prefix}:visits")
for number in range(1, 101):
    store.redis.eval(CREATE_MESSAGE, 3, *keys, "固定测试数据", f"第 {number:03d} 条固定留言：用于对比副本资源用量。", "2026-01-01T00:00:00+00:00")
items = [json.loads(item) for item in store.redis.hvals(f"{prefix}:messages")]
items.sort(key=lambda item: item["id"])
digest = hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
print(json.dumps({"prefix": prefix, "messages": len(items), "sha256": digest}, ensure_ascii=False))
store.close()
