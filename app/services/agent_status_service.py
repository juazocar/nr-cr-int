from __future__ import annotations
import json, os, tempfile, time
from pathlib import Path
from app.config import settings

class AgentStatusService:
    def __init__(self):
        self.path=Path(settings.AGENT_STATUS_FILE); self.path.parent.mkdir(parents=True,exist_ok=True)
    def heartbeat(self, payload:dict)->dict:
        data={"updated_at_epoch":time.time(),"agent_version":str(payload.get("agent_version") or ""),"desktop_running":bool(payload.get("desktop_running")),"desktop_pid":payload.get("desktop_pid")}
        fd,tmp=tempfile.mkstemp(prefix=".agent-status.",suffix=".tmp",dir=str(self.path.parent))
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as h: json.dump(data,h,ensure_ascii=False); h.flush(); os.fsync(h.fileno())
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return self.status()
    def status(self)->dict:
        try: data=json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: data={}
        age=max(0.0,time.time()-float(data.get("updated_at_epoch") or 0)) if data else 10**9
        online=bool(data) and age <= settings.AGENT_STATUS_TTL_SECONDS
        return {"agent_online":online,"desktop_running":bool(data.get("desktop_running")) if online else False,"desktop_pid":data.get("desktop_pid") if online else None,"agent_version":data.get("agent_version") if online else None,"age_seconds":round(age,1) if data else None}
