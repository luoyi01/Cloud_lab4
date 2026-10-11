from dataclasses import dataclass, field
import os
import socket


@dataclass(frozen=True)
class Settings:
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = field(default="", repr=False)
    redis_db: int = 0
    redis_prefix: str = "cloudlab"
    instance: str = "local"
    node: str = "local"
    app_title: str = "班级云留言板"
    app_version: str = "1.0.0"

    @classmethod
    def from_env(cls):
        return cls(redis_host=os.getenv("REDIS_HOST", "redis"),
                   redis_port=int(os.getenv("REDIS_PORT", "6379")),
                   redis_password=os.getenv("REDIS_PASSWORD", ""),
                   redis_db=int(os.getenv("REDIS_DB", "0")),
                   redis_prefix=os.getenv("REDIS_PREFIX", "cloudlab"),
                   instance=os.getenv("POD_NAME", socket.gethostname()),
                   node=os.getenv("NODE_NAME", "docker-host"),
                   app_title=os.getenv("APP_TITLE", "班级云留言板"),
                   app_version=os.getenv("APP_VERSION", "1.0.0"))
