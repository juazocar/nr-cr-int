from app.api.agent import router as agent_router
from app.api.student_quiz import router as student_quiz_router
from app.api.academic_mailer import router as academic_mailer_router
from app.api.actions import router as actions_router
from app.api.shared_context import router as shared_context_router
from app.api.desktop_sync import router as desktop_sync_router
from fastapi import FastAPI

from app.api.watch import router as watch_router
from app.config import settings
from app.core_logging import configure_logging

configure_logging()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend central de NORA. Primera versión orientada a NORA Smart Watch.",
)

@app.get("/")
def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "ok",
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "model": settings.OPENAI_MODEL,
    }

app.include_router(watch_router)

app.include_router(desktop_sync_router)

app.include_router(shared_context_router)

app.include_router(actions_router)

app.include_router(agent_router)

app.include_router(student_quiz_router)
app.include_router(academic_mailer_router)
