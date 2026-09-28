from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.api.student_quiz import teacher_auth
from app.services.academic_mailer_service import AcademicMailerService

router=APIRouter(prefix="/api/academic-mailer",tags=["Academic Mailer"],dependencies=[Depends(teacher_auth)])
service=AcademicMailerService()

class MailPayload(BaseModel):
    blackboard_location:str
    available_from:str
    submission_deadline:str
    test_recipient:str|None=None

@router.post('/evaluations/{evaluation_id}/preview')
def preview(evaluation_id:int,payload:MailPayload):
    try:return {"success":True,"notification":service.preview(evaluation_id,payload.model_dump())}
    except RuntimeError as exc: raise HTTPException(502,str(exc)) from exc

@router.post('/evaluations/{evaluation_id}/send')
def send(evaluation_id:int,payload:MailPayload):
    try:return {"success":True,"result":service.send(evaluation_id,payload.model_dump())}
    except RuntimeError as exc: raise HTTPException(502,str(exc)) from exc
