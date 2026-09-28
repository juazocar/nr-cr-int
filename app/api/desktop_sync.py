import hmac
from fastapi import APIRouter, Header, HTTPException, status
from app.config import settings
from app.models.desktop_sync import TeacherScheduleSyncRequest
from app.services.desktop_sync_service import DesktopSyncService

router = APIRouter(prefix="/api/desktop", tags=["Desktop Sync"])
service = DesktopSyncService()

@router.put("/teacher-schedule")
def sync_teacher_schedule(payload: TeacherScheduleSyncRequest,
                          authorization: str | None = Header(default=None)):
    expected = settings.DESKTOP_SYNC_TOKEN
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Desktop sync is not configured.")
    prefix = "Bearer "
    supplied = authorization[len(prefix):] if authorization and authorization.startswith(prefix) else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")
    try:
        return service.sync_teacher_schedule([x.model_dump() for x in payload.classes])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=str(exc)) from exc
