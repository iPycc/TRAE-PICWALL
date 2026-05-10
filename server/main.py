from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from server.api.router import api_router
from server.core.config import get_settings
from server.core.db import SessionLocal
from server.core.error import http_exception_handler, unhandled_exception_handler
from server.service.bootstrap import ensure_seed, init_db


settings = get_settings()


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
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.on_event("startup")
    def startup() -> None:
        init_db()
        db = SessionLocal()
        try:
            ensure_seed(db)
        finally:
            db.close()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

