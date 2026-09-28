import hmac
import time
from collections import defaultdict, deque
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings
from app.models.student_quiz import QuizSessionCreate, StudentJoinRequest, StudentAnswerRequest
from app.services.student_quiz_service import StudentQuizService, StudentQuizError
_attempts=defaultdict(deque)

def _join_rate_limit(email,code):
    key=(email.strip().casefold(),code); now=time.monotonic(); q=_attempts[key]
    while q and now-q[0]>60: q.popleft()
    if len(q)>=5: raise HTTPException(429,"Demasiados intentos. Espera un minuto e intenta nuevamente.")
    q.append(now)

router=APIRouter(prefix="/api/student-quiz",tags=["Student Quiz"]); service=StudentQuizService(); bearer=HTTPBearer(auto_error=False)
def teacher_auth(credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
    expected=settings.DESKTOP_SYNC_TOKEN
    supplied=credentials.credentials if credentials and credentials.scheme.lower()=="bearer" else ""
    if not expected: raise HTTPException(503,"Quiz teacher authentication is not configured.")
    if not supplied or not hmac.compare_digest(supplied,expected): raise HTTPException(401,"Unauthorized.")
def fail(exc): raise HTTPException(status_code=422,detail=str(exc)) from exc
@router.post("/sessions",dependencies=[Depends(teacher_auth)])
def create(payload:QuizSessionCreate):
    try:return {"success":True,"quiz":service.create(payload.course_id,payload.title,[q.model_dump() for q in payload.questions])}
    except StudentQuizError as e:fail(e)
@router.get("/sessions/{session_id}",dependencies=[Depends(teacher_auth)])
def get_status(session_id:str):
    try:return {"success":True,"quiz":service.status(session_id)}
    except StudentQuizError as e:fail(e)
@router.post("/sessions/{session_id}/start",dependencies=[Depends(teacher_auth)])
def start(session_id:str):
    try:return {"success":True,"quiz":service.start(session_id)}
    except StudentQuizError as e:fail(e)
@router.post("/sessions/{session_id}/next",dependencies=[Depends(teacher_auth)])
def next_question(session_id:str):
    try:return {"success":True,"quiz":service.next_question(session_id)}
    except StudentQuizError as e:fail(e)
@router.post("/sessions/{session_id}/results",dependencies=[Depends(teacher_auth)])
def results(session_id:str):
    try:return {"success":True,"quiz":service.results(session_id)}
    except StudentQuizError as e:fail(e)
@router.post("/sessions/{session_id}/close",dependencies=[Depends(teacher_auth)])
def close(session_id:str):
    try:return {"success":True,"quiz":service.close(session_id)}
    except StudentQuizError as e:fail(e)
@router.post("/join")
def join(payload:StudentJoinRequest):
    _join_rate_limit(payload.email,payload.code)
    try:return {"success":True,**service.join(payload.email,payload.code)}
    except StudentQuizError as e: raise HTTPException(403,str(e)) from e
@router.get("/me")
def me(authorization:str|None=Header(default=None)):
    token=authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not token: raise HTTPException(401,"Unauthorized.")
    try:return {"success":True,"quiz":service.get_student(token)}
    except StudentQuizError as e: raise HTTPException(401,str(e)) from e
@router.post("/answer")
def answer(payload:StudentAnswerRequest):
    try:return {"success":True,**service.answer(payload.session_token,payload.question_id,payload.option_index)}
    except StudentQuizError as e:fail(e)
