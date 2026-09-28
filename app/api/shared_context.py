import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.models.shared_context import SharedContextCreate, SharedContextComplete
from app.services.shared_context_service import SharedContextService

router = APIRouter(prefix="/api/context", tags=["Shared Context"])
service = SharedContextService()
bearer_scheme = HTTPBearer(auto_error=False)


def _authorize(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    expected = settings.DESKTOP_SYNC_TOKEN

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Shared context authentication is not configured.",
        )

    supplied = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""

    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized.",
        )


@router.post("/items", dependencies=[Depends(_authorize)])
def create_item(payload: SharedContextCreate):
    return {"success": True, "item": service.create(**payload.model_dump())}


@router.get("/pending", dependencies=[Depends(_authorize)])
def pending(target: str = Query(..., pattern="^(WATCH|DESKTOP|CORE|MOBILE)$")):
    items = service.pending(target)
    return {"success": True, "target": target, "count": len(items), "items": items}


@router.get("/due", dependencies=[Depends(_authorize)])
def due(target: str = Query(..., pattern="^(WATCH|DESKTOP|CORE|MOBILE)$")):
    items = service.due(target)
    return {"success": True, "target": target, "count": len(items), "items": items}


@router.post("/items/{item_id}/complete", dependencies=[Depends(_authorize)])
def complete(item_id: str, payload: SharedContextComplete):
    item = service.complete(item_id, payload.completed_by)
    if item is None:
        raise HTTPException(status_code=404, detail="Shared context item not found.")
    return {"success": True, "item": item}
