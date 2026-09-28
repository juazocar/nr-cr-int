from fastapi import APIRouter, Depends, HTTPException

from app.api.student_quiz import teacher_auth
from app.models.theory import MarkTopicTaughtRequest, TheoryActivityCreate, TheoryActivityGenerateRequest, TheoryContextRequest
from app.services.theory_classroom_service import TheoryClassroomError, TheoryClassroomService

router = APIRouter(prefix="/api/theory", tags=["Theory Classroom"], dependencies=[Depends(teacher_auth)])
service = TheoryClassroomService()


def fail(exc: TheoryClassroomError):
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/curriculum")
def curriculum():
    return {"success": True, "curriculum": service.curriculum()}


@router.post("/progress/taught")
def mark_taught(payload: MarkTopicTaughtRequest):
    try:
        return {"success": True, "progress": service.mark_taught(payload.topic_code)}
    except TheoryClassroomError as exc:
        fail(exc)


@router.post("/context")
def context(payload: TheoryContextRequest):
    try:
        return {"success": True, "context": service.context(payload.course_id)}
    except TheoryClassroomError as exc:
        fail(exc)


@router.post("/activities/generate")
def generate_activity(payload: TheoryActivityGenerateRequest):
    try:
        return {"success": True, "activity": service.generate_activity(payload.model_dump(mode="json"))}
    except TheoryClassroomError as exc:
        fail(exc)


@router.post("/activities")
def create_activity(payload: TheoryActivityCreate):
    try:
        return {"success": True, "activity": service.create_activity(payload.model_dump(mode="json"))}
    except TheoryClassroomError as exc:
        fail(exc)


@router.get("/activities/{activity_id}")
def get_activity(activity_id: str):
    try:
        return {"success": True, "activity": service.activity(activity_id)}
    except TheoryClassroomError as exc:
        fail(exc)
