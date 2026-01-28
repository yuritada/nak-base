"""
nak-base Phase 1 FastAPI メインアプリケーション
RAG基盤対応版
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, papers
from .services.queue_service import get_queue_length
from .diagnostics import run_diagnostics


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events"""
    # Startup
    run_diagnostics()
    yield
    # Shutdown
    print("Shutting down nak-base backend...")


app = FastAPI(
    title="nak-base API (Phase 1)",
    description="論文フィードバックシステム Phase 1 - RAG基盤対応版",
    version="2.0.0",
    lifespan=lifespan
)

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(papers.router)


@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "service": "nak-base API (Phase 1)",
        "status": "running",
        "version": "2.0.0"
    }


@app.get("/health")
def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "queue_length": get_queue_length()
    }
