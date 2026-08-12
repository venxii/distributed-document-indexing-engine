from fastapi import FastAPI

from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.sources import router as sources_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Incremental Document Indexing Engine",
        version="0.1.0",
    )
    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(sources_router)
    return app


app = create_app()
