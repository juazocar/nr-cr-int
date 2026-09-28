import hmac
from fastapi import APIRouter,Depends,HTTPException,Query,status
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from app.config import settings
from app.models.action import ActionCreate,ActionTransition
from app.services.action_service import ActionService,InvalidActionTransition
router=APIRouter(prefix="/api/actions",tags=["Actions"]); service=ActionService(); bearer=HTTPBearer(auto_error=False)
def auth(c:HTTPAuthorizationCredentials|None=Depends(bearer)):
    expected=settings.DESKTOP_SYNC_TOKEN
    if not expected: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,detail="Actions authentication is not configured.")
    supplied=c.credentials if c and c.scheme.lower()=="bearer" else ""
    if not supplied or not hmac.compare_digest(supplied,expected): raise HTTPException(status_code=401,detail="Unauthorized.")
@router.post("",dependencies=[Depends(auth)])
def create(p:ActionCreate): return {"success":True,"action":service.create(**p.model_dump())}
@router.get("/pending",dependencies=[Depends(auth)])
def pending(target:str=Query(...,pattern="^(WATCH|DESKTOP|CORE|MOBILE|AGENT)$")):
    a=service.pending(target);return {"success":True,"target":target,"count":len(a),"actions":a}
@router.get("/{action_id}",dependencies=[Depends(auth)])
def get(action_id:str):
    a=service.get(action_id)
    if a is None:raise HTTPException(404,"Action not found.")
    return {"success":True,"action":a}
def move(i,s,p):
    try:a=service.transition(i,s,p.actor,p.result,p.error)
    except InvalidActionTransition as e:raise HTTPException(409,str(e)) from e
    if a is None:raise HTTPException(404,"Action not found.")
    return {"success":True,"action":a}
@router.post("/{action_id}/confirm",dependencies=[Depends(auth)])
def confirm(action_id:str,p:ActionTransition):return move(action_id,"CONFIRMED",p)
@router.post("/{action_id}/cancel",dependencies=[Depends(auth)])
def cancel(action_id:str,p:ActionTransition):return move(action_id,"CANCELLED",p)
@router.post("/{action_id}/start",dependencies=[Depends(auth)])
def start(action_id:str,p:ActionTransition):return move(action_id,"EXECUTING",p)
@router.post("/{action_id}/complete",dependencies=[Depends(auth)])
def complete(action_id:str,p:ActionTransition):return move(action_id,"COMPLETED",p)
@router.post("/{action_id}/fail",dependencies=[Depends(auth)])
def fail(action_id:str,p:ActionTransition):return move(action_id,"FAILED",p)
