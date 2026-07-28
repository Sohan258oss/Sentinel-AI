"""FastAPI application entry point.

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from app import __version__
from app.api.routes import router
from app.core.config import settings
from app.core.exceptions import SentinelError
from app.core.llm import get_llm_engine
from app.core.logging import configure_logging, get_logger
from app.rag.store import get_vector_store
from app.tools import load_tools

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm every subsystem at startup and report honestly on each.

    Doing this eagerly means the first incident does not pay the cost of
    loading a CNN and an embedding model, and — more importantly — that any
    misconfiguration is visible in the startup log rather than surfacing as a
    mysteriously degraded agent mid-demo.
    """
    configure_logging()
    logger.info("startup.begin", app=settings.app_name, version=__version__, env=settings.env)

    load_tools()

    engine = get_llm_engine()
    logger.info(
        "startup.llm",
        provider=engine.descriptor,
        available=engine.available,
        mode="reasoning" if engine.available else "deterministic fallback",
    )

    try:
        chunks = get_vector_store().count()
        if chunks == 0:
            logger.warning(
                "startup.rag_empty",
                detail="run: python -m app.rag.ingest --reset --probe",
            )
        else:
            logger.info("startup.rag", indexed_chunks=chunks)
    except Exception as exc:  # noqa: BLE001 - never block startup
        logger.error("startup.rag_failed", error=str(exc)[:200])

    try:
        from app.vision.classifier import DamageClassifier

        classifier = DamageClassifier()
        if classifier.available:
            logger.info("startup.vision", **{
                k: v for k, v in classifier.metadata.items()
                if k in {"val_accuracy", "val_macro_f1", "architecture"}
            })
        else:
            logger.warning(
                "startup.vision_untrained",
                detail="run: python -m ml.prepare_dataset && python -m ml.train_damage_classifier",
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("startup.vision_failed", error=str(exc)[:200])

    logger.info("startup.complete")
    yield
    logger.info("shutdown.complete")


app = FastAPI(
    title=settings.app_name,
    description=(
        "Autonomous Multi-Agent Disaster Intelligence & Resilience Platform. "
        "Predict. Coordinate. Respond. Recover."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(SentinelError)
async def sentinel_error_handler(request: Request, exc: SentinelError) -> JSONResponse:
    """Domain errors become structured responses, not stack traces."""
    logger.warning(
        "api.domain_error",
        path=request.url.path,
        error=exc.message,
        recoverable=exc.recoverable,
    )
    return JSONResponse(
        status_code=404 if not exc.recoverable else 500,
        content={"error": exc.message, "recoverable": exc.recoverable},
    )


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "tagline": settings.app_tagline,
        "version": __version__,
        "docs": "/docs",
        "api": "/api",
    }
