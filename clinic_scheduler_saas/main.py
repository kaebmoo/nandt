from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from api import auth, bookings, organizations
from core.config import settings

app = FastAPI(title="Clinic Scheduler SaaS")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CLIENT_ORIGIN_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include API routers
app.include_router(auth.router, prefix="/api")
app.include_router(bookings.router, prefix="/api")
app.include_router(organizations.router, prefix="/api")

# Frontend Routes
@app.get("/")
def serve_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard")
def serve_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})