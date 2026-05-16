from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from server.api.router import api_router
from server.core.config import get_settings
from server.core.db import SessionLocal
from server.core.error import http_exception_handler, unhandled_exception_handler
from server.service.bootstrap import ensure_seed, init_db


settings = get_settings()


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 404 and self.html:
            index = Path(str(self.directory)) / "index.html"
            if index.exists():
                return await super().get_response("index.html", scope)
        return response



def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    web_base_path = (settings.web_base_path or "").strip().rstrip("/")
    web_prefix = f"/{web_base_path.lstrip('/')}" if web_base_path else ""
    app.include_router(api_router, prefix=f"{web_prefix}{settings.api_prefix}")

    @app.on_event("startup")
    def startup() -> None:
        init_db()
        db = SessionLocal()
        try:
            ensure_seed(db)
        finally:
            db.close()

    @app.get(f"{web_prefix}/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if web_prefix:
        @app.get("/health")
        def root_health() -> dict[str, str]:
            return {"status": "ok"}

    dist_dir = Path(__file__).resolve().parents[2] / "PIC-WALL-Frontend" / "dist"
    if dist_dir.exists():
        app.mount(web_prefix or "/", SpaStaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return app


app = create_app()
