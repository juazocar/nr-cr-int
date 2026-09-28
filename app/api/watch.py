import logging
import time
import uuid
from fastapi import APIRouter, HTTPException

from app.models.watch import WatchAskRequest, WatchAskResponse
from app.services.nora_service import NoraService

router = APIRouter(prefix="/api/watch", tags=["NORA Watch"])
service = NoraService()
logger = logging.getLogger("nora.watch")

@router.post("/ask", response_model=WatchAskResponse)
def ask_watch(payload: WatchAskRequest) -> WatchAskResponse:
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    logger.info(
        "[%s] REQUEST question=%r client=%r session_id=%r",
        request_id, payload.question, payload.client, payload.session_id,
    )
    try:
        answer = service.ask_watch(
            payload.question,
            client=payload.client,
            session_id=payload.session_id,
            trace_id=request_id,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "[%s] RESPONSE success=true answer=%r elapsed_ms=%s",
            request_id, answer, elapsed_ms,
        )
        return WatchAskResponse(success=True, answer=answer, speak=True)
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.exception(
            "[%s] RESPONSE success=false error_type=%s elapsed_ms=%s",
            request_id, type(e).__name__, elapsed_ms,
        )
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")
