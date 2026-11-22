from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth.router import router as auth_router
from app.db import connection
from app.observability import initialize
from app.profile_router import router as profile_router
from app.sources.router import router as sources_router

initialize()

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Knowmivo", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(sources_router)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "mode": "development"})


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    """Checks critical dependency reachability only -- never a paid
    generation call (docs/06-API.md)."""
    try:
        with connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc


# Phase 2+ will add: sources/documents, bot/publication, public visitor
# chat, and conversation-history routers against the new schema from
# docs/13-DB-ENGINEERING-GAP-ANALYSIS.md and docs/18-DATABASE-V2-V3-SCALABLE-SCHEMA.md.
#
# The previous demo routes (/api/documents/*, /api/chat, /api/feedback,
# /api/approvals/*, /api/admin/*) were removed in this phase, along with
# app/demo_context.py, because:
#   1. They authorized every request as a hardcoded admin principal
#      (app.demo_context.principal()) with no real session check -- see
#      docs/17-BACKEND-ARCHITECTURE-GAP.md.
#   2. They operated on the legacy flat demo schema (documents.tenant_id as
#      free text, no company/bot/version model) which Phase 2/3 replaces,
#      not extends.
# They are preserved in git history, not deleted from the record -- only
# from the reachable application surface.
