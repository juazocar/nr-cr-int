from __future__ import annotations
import hashlib, json, secrets
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from app.config import settings
from app.services.notprofejuan_connector import NotProfeJuanConnector

class StudentQuizError(ValueError): pass

class StudentQuizService:
    def __init__(self, connector=None):
        self._path=Path(settings.STUDENT_QUIZ_FILE).expanduser(); self._lock=Lock()
        self._sth=connector or NotProfeJuanConnector()

    def _read(self):
        if not self._path.is_file(): return {"sessions":[]}
        try:
            data=json.loads(self._path.read_text(encoding="utf-8")); return data if isinstance(data,dict) else {"sessions":[]}
        except (OSError,json.JSONDecodeError): return {"sessions":[]}
    def _write(self,data):
        self._path.parent.mkdir(parents=True,exist_ok=True); tmp=self._path.with_suffix(self._path.suffix+".tmp")
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(self._path)
    @staticmethod
    def _norm_email(v): return (v or "").strip().casefold()
    @staticmethod
    def _token_hash(v): return hashlib.sha256(v.encode()).hexdigest()
    def create(self, course_id:int, title:str, questions:list[dict]):
        # Validate the course against the academic source of truth.
        courses=self._sth.get_courses()
        course=next((c for c in courses if int(c.get("id",-1))==course_id),None)
        if not course: raise StudentQuizError("Curso no encontrado en #NotProfeJuan.")
        clean=[]
        for idx,q in enumerate(questions,1):
            opts=[str(x).strip() for x in q["options"]]
            ci=int(q["correct_index"])
            if ci>=len(opts) or any(not x for x in opts): raise StudentQuizError("Pregunta inválida.")
            clean.append({"id":f"q{idx}","text":q["text"].strip(),"options":opts,"correct_index":ci})
        with self._lock:
            data=self._read(); active={s.get("code") for s in data["sessions"] if s.get("status")=="OPEN"}
            code=None
            for _ in range(50):
                candidate=f"{secrets.randbelow(900000)+100000}"
                if candidate not in active: code=candidate; break
            if not code: raise StudentQuizError("No fue posible generar un código de sesión.")
            session={"id":secrets.token_hex(8),"code":code,"status":"OPEN","title":title.strip(),"course_id":course_id,
                     "course_name":course.get("name"),"section":course.get("section"),"created_at":datetime.now(timezone.utc).isoformat(),
                     "closed_at":None,"mode":"DIRECTED","phase":"LOBBY","active_question_index":None,"questions":clean,"participants":[],"responses":[]}
            data["sessions"].append(session); self._write(data)
        return self._teacher_view(session)
    def _find_code(self,data,code): return next((s for s in reversed(data["sessions"]) if s.get("code")==code and s.get("status")=="OPEN"),None)
    def join(self,email:str,code:str):
        with self._lock:
            data=self._read(); session=self._find_code(data,code)
            if not session: raise StudentQuizError("No fue posible ingresar a esta sesión. Verifica tu correo y el código.")
            students=self._sth.get_students(int(session["course_id"])); needle=self._norm_email(email)
            student=next((s for s in students if s.get("active",True) and self._norm_email(s.get("email"))==needle),None)
            if not student: raise StudentQuizError("No fue posible ingresar a esta sesión. Verifica tu correo y el código.")
            sid=int(student["id"]); existing=next((p for p in session["participants"] if int(p["student_id"])==sid),None)
            token=secrets.token_urlsafe(32); token_hash=self._token_hash(token)
            if existing: existing["token_hash"]=token_hash; existing["last_joined_at"]=datetime.now(timezone.utc).isoformat()
            else: session["participants"].append({"student_id":sid,"full_name":student.get("full_name"),"token_hash":token_hash,"joined_at":datetime.now(timezone.utc).isoformat()})
            self._write(data)
            return {"session_token":token,"student":{"id":sid,"full_name":student.get("full_name")},"quiz":self._student_view(session,sid)}
    def _auth_student(self,session,token):
        h=self._token_hash(token); return next((p for p in session["participants"] if secrets.compare_digest(p.get("token_hash",""),h)),None)
    def start(self, session_id):
        with self._lock:
            data=self._read(); s=next((x for x in data["sessions"] if x["id"]==session_id),None)
            if not s or s.get("status") != "OPEN": raise StudentQuizError("Quiz no encontrado o cerrado.")
            s["phase"]="QUESTION"; s["active_question_index"]=0; self._write(data); return self._teacher_view(s)

    def next_question(self, session_id):
        with self._lock:
            data=self._read(); s=next((x for x in data["sessions"] if x["id"]==session_id),None)
            if not s or s.get("status") != "OPEN": raise StudentQuizError("Quiz no encontrado o cerrado.")
            current=s.get("active_question_index")
            if current is None: s["phase"]="QUESTION"; s["active_question_index"]=0
            elif current + 1 < len(s["questions"]): s["active_question_index"]=current+1; s["phase"]="QUESTION"
            else: s["phase"]="RESULTS"
            self._write(data); return self._teacher_view(s)

    def results(self, session_id):
        with self._lock:
            data=self._read(); s=next((x for x in data["sessions"] if x["id"]==session_id),None)
            if not s: raise StudentQuizError("Quiz no encontrado.")
            s["phase"]="RESULTS"; self._write(data); return self._teacher_view(s)

    def answer(self,token,question_id,option_index):
        with self._lock:
            data=self._read(); session=next((s for s in reversed(data["sessions"]) if s.get("status")=="OPEN" and self._auth_student(s,token)),None)
            if not session: raise StudentQuizError("La sesión no está disponible.")
            participant=self._auth_student(session,token); q=next((x for x in session["questions"] if x["id"]==question_id),None)
            if session.get("mode") == "DIRECTED":
                idx=session.get("active_question_index")
                if session.get("phase") != "QUESTION" or idx is None or idx >= len(session["questions"]) or session["questions"][idx]["id"] != question_id:
                    raise StudentQuizError("Esta pregunta no está activa.")
            if not q or option_index>=len(q["options"]): raise StudentQuizError("Respuesta inválida.")
            if any(r["student_id"]==participant["student_id"] and r["question_id"]==question_id for r in session["responses"]): raise StudentQuizError("Esta pregunta ya fue respondida.")
            correct=option_index==q["correct_index"]
            session["responses"].append({"student_id":participant["student_id"],"question_id":question_id,"option_index":option_index,"is_correct":correct,"answered_at":datetime.now(timezone.utc).isoformat()})
            self._write(data); return {"accepted":True,"is_correct":correct,"quiz":self._student_view(session,participant["student_id"])}
    def get_student(self,token):
        data=self._read(); session=next((s for s in reversed(data["sessions"]) if s.get("status")=="OPEN" and self._auth_student(s,token)),None)
        if not session: raise StudentQuizError("La sesión no está disponible.")
        p=self._auth_student(session,token); return self._student_view(session,p["student_id"])
    def latest_open(self):
        data=self._read(); s=next((x for x in reversed(data["sessions"]) if x.get("status")=="OPEN"),None)
        if not s: raise StudentQuizError("No hay un quiz abierto.")
        return s

    def status(self,session_id):
        data=self._read(); s=next((x for x in data["sessions"] if x["id"]==session_id),None)
        if not s: raise StudentQuizError("Quiz no encontrado.")
        return self._teacher_view(s)
    def close(self,session_id):
        with self._lock:
            data=self._read(); s=next((x for x in data["sessions"] if x["id"]==session_id),None)
            if not s: raise StudentQuizError("Quiz no encontrado.")
            s["status"]="CLOSED"; s["closed_at"]=datetime.now(timezone.utc).isoformat(); self._write(data); return self._teacher_view(s)
    def _student_view(self,s,student_id):
        answered={r["question_id"] for r in s["responses"] if r["student_id"]==student_id}
        active=None
        idx=s.get("active_question_index")
        if s.get("phase")=="QUESTION" and isinstance(idx,int) and 0 <= idx < len(s["questions"]):
            q=s["questions"][idx]
            active={"id":q["id"],"text":q["text"],"options":q["options"],"answered":q["id"] in answered,"number":idx+1,"total":len(s["questions"])}
        return {"id":s["id"],"title":s["title"],"course_name":s.get("course_name"),"section":s.get("section"),"status":s["status"],
                "mode":s.get("mode","AUTONOMOUS"),"phase":s.get("phase","QUESTION"),"active_question":active}

    def _teacher_view(self,s):
        total=len(s["responses"]); correct=sum(1 for r in s["responses"] if r["is_correct"])
        per=[]
        for q in s["questions"]:
            rs=[r for r in s["responses"] if r["question_id"]==q["id"]]; c=sum(1 for r in rs if r["is_correct"])
            per.append({"question_id":q["id"],"responses":len(rs),"correct":c,"incorrect":len(rs)-c})
        idx=s.get("active_question_index")
        active_question=None
        if isinstance(idx,int) and 0 <= idx < len(s["questions"]):
            q=s["questions"][idx]; active_question={"id":q["id"],"number":idx+1,"total":len(s["questions"]),"text":q["text"],"options":q["options"]}
        return {"id":s["id"],"code":s["code"],"status":s["status"],"phase":s.get("phase","LOBBY"),"mode":s.get("mode","DIRECTED"),"title":s["title"],"course_id":s["course_id"],"course_name":s.get("course_name"),"section":s.get("section"),
                "participants":len(s["participants"]),"responses":total,"correct":correct,"incorrect":total-correct,"active_question":active_question,"questions":per}
