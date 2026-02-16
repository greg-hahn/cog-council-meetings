# ==========================================================================
# Council Meetings API — main.py
# ==========================================================================
#
# Setup & Usage
# -------------
# 1. DATABASE: Set the DATABASE_URL environment variable to your Postgres
#    connection string. Default: postgresql://postgres:postgres@localhost:5432/council_meetings
#
#    Create the database first:
#      createdb council_meetings
#
# 2. MIGRATIONS: Run Alembic to create all tables:
#      alembic upgrade head
#
# 3. SEED DATA: The Guelph municipality row is auto-seeded on app startup.
#
# 4. INGEST A MEETING: Use the admin endpoint or CLI:
#      # Via API (server must be running):
#      curl -X POST "http://localhost:8000/admin/ingest?url=https://pub-guelph.escribemeetings.com/Meeting.aspx?Id=5b29247b-3757-48cf-a510-a9a979085a2e%26Agenda=Agenda%26lang=English"
#
#      # Via CLI:
#      python -m backend.cli ingest "https://pub-guelph.escribemeetings.com/Meeting.aspx?Id=5b29247b-3757-48cf-a510-a9a979085a2e&Agenda=Agenda&lang=English"
#
# 5. START THE SERVER:
#      uvicorn backend.main:app --reload
#
# 6. ENDPOINTS:
#      GET  /api/guelph/meetings/today       - Today's meetings with agenda items
#      GET  /api/guelph/meetings/now-next     - Current + next agenda item
#      POST /admin/ingest?url=...             - Ingest a meeting from eScribe URL
#      GET  /guelph                           - Resident-facing web UI
#
# ==========================================================================

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

from backend.api.routes.meetings import router as meetings_router
from backend.db.session import SessionLocal
from backend.db.seed import seed_guelph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(
    title="Council Meetings API",
    description="Civic engagement API for municipal council meeting agendas",
    version="0.1.0",
)

app.include_router(meetings_router)

# Serve static frontend assets
app.mount("/static", StaticFiles(directory="frontend"), name="static")

templates = Jinja2Templates(directory="frontend")


@app.on_event("startup")
def on_startup():
    """Seed municipality data on startup."""
    db = SessionLocal()
    try:
        seed_guelph(db)
    finally:
        db.close()


@app.get("/{slug}", response_class=HTMLResponse)
def resident_page(request: Request, slug: str):
    """Serve the resident-facing UI for a municipality."""
    return templates.TemplateResponse("index.html", {"request": request, "slug": slug})
