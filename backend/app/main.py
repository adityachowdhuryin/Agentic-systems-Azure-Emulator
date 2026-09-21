from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from app.exceptions import BandAError
from app.logging_config import setup_logging
from app.error_utils import error_response_from_exception


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    # No stub seed on startup — only real inbound / simulator-created data appears in the UI.
    # Worker starts OFF — turn on via Queue panel so runs stay QUEUED for resend/rejection demos.
    yield
    mock_consumer.stop()


app = FastAPI(
    title="Band A Local Emulator",
    description="Sales Lead Qualification — Entry & Control",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
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
