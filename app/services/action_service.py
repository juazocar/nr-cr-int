from datetime import datetime,timezone
import json,os,tempfile,threading,uuid
from pathlib import Path
from app.config import settings
import logging
logger=logging.getLogger("nora.actions")
class InvalidActionTransition(ValueError): pass
class ActionService:
    ALLOWED={"PROPOSED":{"CONFIRMED","CANCELLED"},"CONFIRMED":{"EXECUTING","CANCELLED"},"EXECUTING":{"COMPLETED","FAILED"},"COMPLETED":set(),"FAILED":set(),"CANCELLED":set()}
    def __init__(self):
        self.path=Path(settings.ACTIONS_FILE).expanduser(); self.path.parent.mkdir(parents=True,exist_ok=True); self._lock=threading.Lock()
    def _load(self):
        if not self.path.is_file(): return []
        try:
            raw=json.loads(self.path.read_text(encoding="utf-8")); return raw.get("actions",[]) if isinstance(raw,dict) else []
        except (OSError,json.JSONDecodeError): return []
    def _save(self,items):
        fd,tmp=tempfile.mkstemp(prefix=".actions.",suffix=".tmp",dir=str(self.path.parent))
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as h:
                json.dump({"version":1,"actions":items},h,ensure_ascii=False,indent=2); h.flush(); os.fsync(h.fileno())
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    def create(self,source,target,action_type,description,payload=None,requires_confirmation=True):
        now=datetime.now(timezone.utc).isoformat(); state="PROPOSED" if requires_confirmation else "CONFIRMED"
        x={"id":str(uuid.uuid4()),"source":source,"target":target,"action_type":action_type.strip().upper(),"description":description.strip(),"payload":dict(payload or {}),"requires_confirmation":bool(requires_confirmation),"status":state,"created_at":now,"updated_at":now,"confirmed_at":now if state=="CONFIRMED" else None,"started_at":None,"completed_at":None,"cancelled_at":None,"actor":source if state=="CONFIRMED" else None,"result":None,"error":None}
        with self._lock:
            a=self._load(); a.append(x); self._save(a)
        logger.info(
            "ACTION_CREATE id=%s source=%s target=%s type=%s status=%s payload=%r",
            x.get("id"), x.get("source"), x.get("target"), x.get("action_type"),
            x.get("status"), x.get("payload"),
        )
        return x
    def get(self,i):
        with self._lock: return next((x for x in self._load() if x.get("id")==i),None)
    def pending(self,target):
        with self._lock: a=self._load()
        return [x for x in a if x.get("target")==target and x.get("status") in {"PROPOSED","CONFIRMED","EXECUTING"}]
    def transition(self,i,new,actor,result=None,error=None):
        new=new.upper()
        with self._lock:
            a=self._load(); x=next((v for v in a if v.get("id")==i),None)
            if x is None:return None
            old=x.get("status")
            if new not in self.ALLOWED.get(old,set()): raise InvalidActionTransition(f"Invalid action transition: {old} -> {new}")
            now=datetime.now(timezone.utc).isoformat(); x["status"]=new;x["updated_at"]=now;x["actor"]=actor
            if new=="CONFIRMED":x["confirmed_at"]=now
            elif new=="EXECUTING":x["started_at"]=now
            elif new in {"COMPLETED","FAILED"}:x["completed_at"]=now
            elif new=="CANCELLED":x["cancelled_at"]=now
            if result is not None:x["result"]=result
            if error is not None:x["error"]=error
            self._save(a);return x
