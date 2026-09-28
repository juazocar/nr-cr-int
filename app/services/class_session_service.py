"""Sesión docente activa de NORA Core."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo
from app.config import settings

class ClassSessionService:
    def __init__(self):
        self._path=Path(settings.CLASS_SESSION_FILE).expanduser()
        self._lock=Lock()

    def _read(self):
        if not self._path.is_file(): return None
        try:
            data=json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data,dict) else None
        except (OSError,json.JSONDecodeError): return None

    def active(self):
        data=self._read()
        return data if data and data.get("status")=="ACTIVE" else None

    def start(self, class_info: dict, source="WATCH"):
        with self._lock:
            current=self.active()
            if current: return {"created":False,"session":current}
            now=datetime.now(ZoneInfo(settings.ACADEMIC_TIMEZONE))
            session={
                "status":"ACTIVE","source":source,
                "course":class_info.get("course"),"section":class_info.get("section"),
                "start_time":class_info.get("start_time"),"end_time":class_info.get("end_time"),
                "room":class_info.get("room"),"campus":class_info.get("campus"),
                "class_date":now.date().isoformat(),
                "started_at":datetime.now(timezone.utc).isoformat(),"ended_at":None,
            }
            self._path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self._path.with_suffix(self._path.suffix+".tmp")
            tmp.write_text(json.dumps(session,ensure_ascii=False,indent=2),encoding="utf-8")
            tmp.replace(self._path)
            return {"created":True,"session":session}

    def finish(self):
        with self._lock:
            session=self.active()
            if not session: return None
            session["status"]="COMPLETED"
            session["ended_at"]=datetime.now(timezone.utc).isoformat()
            tmp=self._path.with_suffix(self._path.suffix+".tmp")
            tmp.write_text(json.dumps(session,ensure_ascii=False,indent=2),encoding="utf-8")
            tmp.replace(self._path)
            return session
