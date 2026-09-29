from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_events import router as events_router
from app.api.routes_ingress import router as ingress_router
from app.api.routes_invoice import router as invoice_router
from app.api.routes_leads import router as leads_router
from app.api.routes_runs import router as runs_router
from app.api.routes_scheduler import router as scheduler_router
from app.api.routes_simulators import router as simulators_router
from app.api.routes_teams import router as teams_router
from app.api.routes_zoho_mail import router as zoho_mail_router
from app.band_b.mock_consumer import mock_consumer
from app.config import settings
from app.correlation import new_correlation_id, set_correlation_id
from app.database import init_db
from app.error_utils import error_response_from_exception
from app.exceptions import BandAError
from app.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    if settings.worker_autostart:
        mock_consumer.start()
    yield
    mock_consumer.stop()


app = FastAPI(
    title="Band A Local Emulator",
    description="Sales Lead Qualification — Entry & Control",
    version="1.0.0",
    lifespan=lifespan,
)

_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in _origins else _origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or new_correlation_id()
    set_correlation_id(cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


@app.exception_handler(BandAError)
async def band_a_error_handler(request: Request, exc: BandAError):
    cid = request.headers.get("X-Correlation-ID", "")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response_from_exception(exc, cid),
    )


app.include_router(ingress_router)
app.include_router(leads_router)
app.include_router(runs_router)
app.include_router(events_router)
app.include_router(scheduler_router)
app.include_router(simulators_router)
app.include_router(zoho_mail_router)
app.include_router(teams_router)
app.include_router(invoice_router)

# Optional baked UI (ACA banda image copies frontend dist to /app/ui)
_UI_DIR = Path(os.environ.get("UI_DIST_DIR", "/app/ui"))
if _UI_DIR.is_dir() and (_UI_DIR / "index.html").is_file():
    assets = _UI_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="ui-assets")

    @app.get("/")
    async def ui_index():
        return FileResponse(_UI_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def ui_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = _UI_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_UI_DIR / "index.html")
