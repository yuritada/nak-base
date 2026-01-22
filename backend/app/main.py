"""
nak-base MVP版 FastAPI メインアプリケーション
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, papers
from .services.queue_service import get_queue_length

app = FastAPI(
    title="nak-base API (MVP)",
    description="論文フィードバックシステム MVP版 - PDFを投げたらAIが感想を返す",
    version="1.0.0"
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
        "service": "nak-base API (MVP)",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "queue_length": get_queue_length()
    }
