from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError

from .config import Settings
from .store import MessageStore


class NewMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, strict=True, extra="forbid")
    author: str = Field(min_length=1, max_length=30)
    content: str = Field(min_length=1, max_length=300)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application):
        application.state.store = MessageStore(config)
        yield
        application.state.store.close()

    application = FastAPI(title=config.app_title, version=config.app_version, lifespan=lifespan)

    def identity():
        return {"instance": config.instance, "node": config.node, "version": config.app_version}

    @application.middleware("http")
    async def stamp_instance(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Instance-ID"] = config.instance
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(RedisError)
    async def storage_unavailable(request, exc):
        return JSONResponse(status_code=503, content={"detail": "存储暂时不可用，请稍后重试。", **identity()})

    @application.get("/api/whoami")
    def whoami():
        return {**identity(), "title": config.app_title, "time": datetime.now(timezone.utc).isoformat()}

    @application.post("/api/messages", status_code=201)
    def create_message(message: NewMessage, request: Request):
        return {"message": request.app.state.store.create(message.author, message.content), **identity()}

    @application.get("/api/messages")
    def list_messages(request: Request, limit: int = Query(20, ge=1, le=50),
                      before: int | None = Query(None, ge=1)):
        return {**request.app.state.store.list(limit, before), **identity()}

    @application.post("/api/visits")
    def count_visit(request: Request):
        return {"count": request.app.state.store.visit(), **identity()}

    @application.get("/health/live")
    def live():
        return {"status": "alive", **identity()}

    @application.get("/health/ready")
    def ready(request: Request):
        request.app.state.store.ready()
        return {"status": "ready", **identity()}

    return application


app = create_app()
