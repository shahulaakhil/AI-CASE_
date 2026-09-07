"""FastAPI application entry point.

Serves the JSON API under /api and the single page front end from /web.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, settings
from .api.routes import router
from .llm import LLMError, registry as llm

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("litigatai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        db.init()
        logger.info("Storage ready on %s.", db.backend_name())
        if settings.DEMO_SEED:
            from .services import seed

            seed.seed_if_empty()
    except Exception as exc:  # noqa: BLE001 - the API still works without the tracker
        logger.error("Storage could not be initialised: %s", exc)

    configured = [p.label for p in llm.available_providers()]
    if configured:
        logger.info("Server side AI provider keys: %s.", ", ".join(configured))
    elif settings.ALLOW_CLIENT_KEYS:
        logger.info(
            "No server side provider key. Running in bring your own key mode: each "
            "visitor supplies their own key from the Settings panel."
        )
    else:
        logger.warning(
            "No AI provider key found and ALLOW_CLIENT_KEYS is off, so no tool can "
            "run. Set GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY or "
            "HUGGINGFACE_API_KEY."
        )
    yield


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description="AI workbench for Indian litigation practice.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

origins = [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def timing(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Response-Time"] = f"{elapsed:.0f}ms"
    if request.url.path.startswith("/api/"):
        # An API response can depend on the caller's own API key, so it must
        # never be held in a shared cache along the way.
        response.headers.setdefault("Cache-Control", "no-store")
        if elapsed > 1000:
            logger.info("%s %s took %.0f ms", request.method, request.url.path, elapsed)
    return response


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    logger.warning("Provider error on %s: %s", request.url.path, exc.message)
    return JSONResponse(status_code=502, content={"error": exc.to_dict()})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Something went wrong on the server.",
                "detail": str(exc)[:400] if settings.DEBUG else "",
            }
        },
    )


app.include_router(router, prefix="/api")

# The front end and the API are versioned together: a browser holding an old
# app.js against a new server, or the reverse, is confusing to debug. Asking
# the browser to revalidate these three files on every load costs one cheap
# conditional request and removes that whole class of problem after a deploy.
REVALIDATE = {"Cache-Control": "no-cache"}

if settings.WEB_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=settings.WEB_DIR / "assets"),
        name="assets",
    )

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(settings.WEB_DIR / "index.html", headers=REVALIDATE)

    @app.get("/styles.css", include_in_schema=False)
    async def styles() -> FileResponse:
        return FileResponse(
            settings.WEB_DIR / "styles.css", media_type="text/css", headers=REVALIDATE
        )

    @app.get("/app.js", include_in_schema=False)
    async def script() -> FileResponse:
        return FileResponse(
            settings.WEB_DIR / "app.js",
            media_type="application/javascript",
            headers=REVALIDATE,
        )

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(settings.WEB_DIR / "assets" / "favicon.svg")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        """Hash routing means any other path is a deep link into the app shell."""
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"message": "Not found."}})
        return FileResponse(settings.WEB_DIR / "index.html", headers=REVALIDATE)
