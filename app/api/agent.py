import hmac
from fastapi import APIRouter,Depends,HTTPException,status
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from pydantic import BaseModel
from app.config import settings
from app.services.agent_status_service import AgentStatusService
router=APIRouter(prefix="/api/agent",tags=["Agent"]); bearer=HTTPBearer(auto_error=False); service=AgentStatusService()
def auth(c:HTTPAuthorizationCredentials|None=Depends(bearer)):
    expected=settings.DESKTOP_SYNC_TOKEN; supplied=c.credentials if c and c.scheme.lower()=="bearer" else ""
    if not expected: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,detail="Agent authentication is not configured.")
    if not supplied or not hmac.compare_digest(supplied,expected): raise HTTPException(status_code=401,detail="Unauthorized.")
class Heartbeat(BaseModel):
    agent_version:str=""; desktop_running:bool=False; desktop_pid:int|None=None
@router.post("/heartbeat",dependencies=[Depends(auth)])
def heartbeat(p:Heartbeat): return {"success":True,"status":service.heartbeat(p.model_dump())}
@router.get("/status",dependencies=[Depends(auth)])
def get_status(): return {"success":True,"status":service.status()}
