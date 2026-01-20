from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import users, papers, feedbacks, dashboard
from .services.queue_service import get_queue_length

app = FastAPI(
    title="nak-base API",
    description="論文フィードバックシステム - 研究室の『集合知』で、最高の一本を。",
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
app.include_router(users.router)
app.include_router(papers.router)
app.include_router(feedbacks.router)
app.include_router(dashboard.router)


@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "service": "nak-base API",
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
