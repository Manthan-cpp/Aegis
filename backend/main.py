from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from routers.sos import router as sos_router
from routers.companion import router as companion_router
from routers.legal import router as legal_router
from routers.responder import router as responder_router
from routers.voice import router as voice_router
from routers.email import router as email_router
from routers.health import router as health_router
from routers.direct_messages import router as direct_messages_router
from services.email_queue import start_email_queue_worker, stop_email_queue_worker

load_dotenv()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    worker_enabled = os.getenv("EMAIL_QUEUE_WORKER_ENABLED", "true").strip().casefold() not in {"0", "false", "no", "off"}
    if worker_enabled:
        start_email_queue_worker()
    try:
        yield
    finally:
        if worker_enabled:
            stop_email_queue_worker()


app = FastAPI(title="Aegis Backend", version="0.1.0", lifespan=lifespan)

# CORS: allow the Next.js dev server and future deployed frontend.
# Tighten ALLOWED_ORIGINS in .env before deploying past hackathon/demo stage.
configured_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
allowed_origins = (
    [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    if configured_origins
    else ["http://localhost:3000", "http://127.0.0.1:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sos_router)
app.include_router(companion_router)
app.include_router(legal_router)
app.include_router(responder_router)
app.include_router(voice_router)
app.include_router(email_router)
app.include_router(health_router)
app.include_router(direct_messages_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "aegis-backend"}


# Routers are added phase by phase:
# Phase 2: from routers import sos
# Phase 4: legal rights RAG router is active.
# Phase 5: from routers import cases
