"""
MedTrigger — FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import router

app = FastAPI(
    title="MedTrigger API",
    description="Drag & Drop Medical Workflow Automation Backend",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — allow local Next.js dev server and any deployed frontend
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://frontend-amber-xi-26.vercel.app",
        "https://useclarus.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}