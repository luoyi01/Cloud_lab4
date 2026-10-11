import json
from datetime import datetime, timezone

from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from .config import Settings


CREATE_MESSAGE = """
local id = redis.call('INCR', KEYS[1])
local item = cjson.encode({id=id, author=ARGV[1], content=ARGV[2], created_at=ARGV[3]})
redis.call('HSET', KEYS[2], tostring(id), item)
redis.call('ZADD', KEYS[3], id, tostring(id))
return item
"""


class MessageStore:
    def __init__(self, settings: Settings):
        self.prefix = settings.redis_prefix
        self.redis = Redis(host=settings.redis_host, port=settings.redis_port,
                           password=settings.redis_password or None, db=settings.redis_db,
                           decode_responses=True, socket_timeout=1, socket_connect_timeout=1,
                           retry=Retry(NoBackoff(), 0))

    def create(self, author: str, content: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        value = self.redis.eval(CREATE_MESSAGE, 3, f"{self.prefix}:sequence",
                                f"{self.prefix}:messages", f"{self.prefix}:index",
                                author, content, timestamp)
        return json.loads(value)

    def list(self, limit: int, before: int | None):
        maximum = f"({before}" if before is not None else "+inf"
        ids = self.redis.zrevrangebyscore(f"{self.prefix}:index", maximum, "-inf",
                                        start=0, num=limit + 1)
        selected = ids[:limit]
        values = self.redis.hmget(f"{self.prefix}:messages", selected) if selected else []
        return {"items": [json.loads(v) for v in values if v is not None],
                "total": self.redis.zcard(f"{self.prefix}:index"),
                "next_cursor": int(selected[-1]) if len(ids) > limit else None}

    def visit(self):
        return self.redis.incr(f"{self.prefix}:visits")

    def ready(self):
        return self.redis.ping()

    def close(self):
        self.redis.close()
