from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings


class TheoryClassroomError(ValueError):
    pass


COURSE_KEY = "seguridad-calidad-desarrollo-software"
COURSE_NAME = "Seguridad y calidad en el desarrollo de software"

# El orden es curricular y también define la secuencia válida de avance explícito.
CURRICULUM = [
    {"unit":"1","topic_code":"1.1.1","concepts":["calidad de software","ISO/IEC 25010","CIA","Security by Design","cumplimiento","ISO 27001","PDCA"],"source":{"ppt":"1.1.1","section":"Fundamentos de calidad, seguridad y cumplimiento"},"initial_progress":"TAUGHT"},
    {"unit":"1","topic_code":"1.2.1","concepts":["pruebas unitarias","integración","sistema","aceptación","rendimiento","carga","seguridad","usabilidad","trazabilidad"],"source":{"ppt":"1.2.1","section":"Pruebas funcionales y no funcionales"},"initial_progress":"TAUGHT"},
    {"unit":"1","topic_code":"1.3.1","concepts":["auditoría","ISO 9001","ISO 25010","ISO 27001","IEEE 730","IEEE/ISO 29119","CAPA","evidencia"],"source":{"ppt":"1.3.1","section":"Auditoría de calidad/legal"},"initial_progress":"TAUGHT"},
    {"unit":"1","topic_code":"1.4.1","concepts":["plan de pruebas","objetivos","alcance","recursos","metodología","riesgos","evidencia","aceptación","PDCA"],"source":{"ppt":"1.4.1","section":"Plan integral de pruebas"},"initial_progress":"TAUGHT"},
    {"unit":"2","topic_code":"2.1.1","concepts":["planificación","risk-based testing","SAST","DAST","CI/CD","Shift-Left","Docker"],"source":{"ppt":"2.1.1","section":"Estrategias y enfoques"},"initial_progress":"TAUGHT"},
    {"unit":"2","topic_code":"2.2.1","concepts":["partición de equivalencia","Boundary Value Analysis","tablas de decisión","white-box","paths","coverage","loops","data-flow","complejidad ciclomática"],"source":{"ppt":"2.2.1","section":"Diseño avanzado de casos"},"initial_progress":"TAUGHT"},
    {"unit":"2","topic_code":"2.3.1","concepts":["pruebas estáticas","revisión","SonarQube","evidencia","severidad","trazabilidad"],"source":{"ppt":"2.3.1","section":"Pruebas estáticas"},"initial_progress":"FUTURE"},
    {"unit":"2","topic_code":"2.4.1","concepts":["ISO/IEC 17021-1","ISO/IEC 17065","ISO 19011","hallazgos","no conformidades","evidencia","informe de certificación"],"source":{"ppt":"2.4.1","section":"Informes de certificación"},"initial_progress":"FUTURE"},
    {"unit":"3","topic_code":"3.1.1","concepts":["pentesting","black box","white box","grey box","reconocimiento","escaneo","enumeración","explotación","post-explotación","reporte"],"source":{"ppt":"3.1.1","section":"Pentesting"},"initial_progress":"FUTURE"},
    {"unit":"3","topic_code":"3.2.1","concepts":["CI/CD Security Pipeline","Shift-Left","SAST","DAST","dependencias","secrets","métricas"],"source":{"ppt":"3.2.1","section":"CI/CD Security Pipeline"},"initial_progress":"FUTURE"},
    {"unit":"3","topic_code":"3.3.1","concepts":["Selenium IDE","POM","modularización","login automation","Git","CI/CD"],"source":{"ppt":"3.3.1","section":"Automatización funcional/normativa","source_note":"Existe una anomalía semántica conocida en la fuente sobre ventajas y limitaciones de Selenium IDE; no corregir silenciosamente."},"initial_progress":"FUTURE"},
    {"unit":"3","topic_code":"3.4.1","concepts":["load testing","stress testing","RPO","RTO","resiliencia","JMeter","LoadRunner","Gatling","k6","monitoring","chaos","digital twins"],"source":{"ppt":"3.4.1","section":"Continuous QA / Stress"},"initial_progress":"FUTURE"},
]


class TheoryClassroomService:
    def __init__(self, path: str | Path | None = None):
        self._path = Path(path or settings.THEORY_CLASSROOM_FILE).expanduser()
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _initial_state() -> dict:
        return {
            "version": 1,
            "course": {"key": COURSE_KEY, "name": COURSE_NAME},
            "progress": {item["topic_code"]: item["initial_progress"] for item in CURRICULUM},
            "progress_events": [],
            "activities": [],
        }

    def _read(self) -> dict:
        if not self._path.is_file():
            return self._initial_state()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TheoryClassroomError("No fue posible leer el estado de Theory Classroom.") from exc
        if not isinstance(data, dict):
            raise TheoryClassroomError("El estado de Theory Classroom es inválido.")
        initial = self._initial_state()
        progress = data.get("progress")
        if not isinstance(progress, dict):
            raise TheoryClassroomError("El progreso curricular persistido es inválido.")
        # Los temas nuevos del mapa conservan su estado inicial sin degradar progreso ya persistido.
        for code, state in initial["progress"].items():
            progress.setdefault(code, state)
        data.setdefault("progress_events", [])
        data.setdefault("activities", [])
        data.setdefault("course", initial["course"])
        data.setdefault("version", 1)
        return data

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".theory.", suffix=".tmp", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def curriculum(self) -> dict:
        data = self._read()
        topics = []
        for item in CURRICULUM:
            topic = deepcopy(item)
            topic["progress"] = data["progress"].get(item["topic_code"], item["initial_progress"])
            topic.pop("initial_progress", None)
            topics.append(topic)
        return {"course": deepcopy(data["course"]), "topics": topics}

    def mark_taught(self, topic_code: str, actor: str = "TEACHER") -> dict:
        codes = [item["topic_code"] for item in CURRICULUM]
        if topic_code not in codes:
            raise TheoryClassroomError("Tema curricular no encontrado.")
        with self._lock:
            data = self._read()
            if data["progress"].get(topic_code) == "TAUGHT":
                return {"changed": False, "topic_code": topic_code, "progress": "TAUGHT"}
            index = codes.index(topic_code)
            missing = [code for code in codes[:index] if data["progress"].get(code) != "TAUGHT"]
            if missing:
                raise TheoryClassroomError(f"No se puede avanzar fuera de secuencia. Tema previo pendiente: {missing[0]}.")
            data["progress"][topic_code] = "TAUGHT"
            data["progress_events"].append({"topic_code": topic_code, "from":"FUTURE", "to":"TAUGHT", "actor":actor, "changed_at":self._now()})
            self._write(data)
        return {"changed": True, "topic_code": topic_code, "progress": "TAUGHT"}

    def guard(self, topic_codes: list[str]) -> list[dict]:
        if not topic_codes:
            raise TheoryClassroomError("Debe indicar al menos un tema curricular.")
        data = self._read()
        by_code = {item["topic_code"]: item for item in CURRICULUM}
        allowed = []
        for code in dict.fromkeys(topic_codes):
            item = by_code.get(code)
            if not item:
                raise TheoryClassroomError(f"Tema curricular no encontrado: {code}.")
            if data["progress"].get(code) != "TAUGHT":
                raise TheoryClassroomError(f"El tema {code} todavía está FUTURE y no puede utilizarse.")
            allowed.append(item)
        return allowed

    def context(self, course_id: int) -> dict:
        data = self._read()
        taught = self.guard([item["topic_code"] for item in CURRICULUM if data["progress"].get(item["topic_code"]) == "TAUGHT"])
        return {
            "course_id": int(course_id),
            "course": deepcopy(data["course"]),
            "allowed_topic_codes": [item["topic_code"] for item in taught],
            "allowed_concepts": list(dict.fromkeys(concept for item in taught for concept in item["concepts"])),
            "sources": [deepcopy(item["source"]) for item in taught],
            "activity_types": ["CASO", "DESAFÍO", "REPASO", "ANALIZAR"],
        }

    def create_activity(self, payload: dict) -> dict:
        topics = self.guard(payload["topic_codes"])
        allowed_concepts = {concept.casefold() for item in topics for concept in item["concepts"]}
        invalid = [concept for concept in payload["concepts"] if concept.casefold() not in allowed_concepts]
        if invalid:
            raise TheoryClassroomError(f"Concepto fuera del currículum permitido para los temas seleccionados: {invalid[0]}.")
        canonical_sources = [deepcopy(item["source"]) for item in topics]
        supplied_sources = payload.get("sources")
        if supplied_sources is not None and supplied_sources != canonical_sources:
            raise TheoryClassroomError("Las fuentes de la actividad no coinciden con la trazabilidad curricular.")
        activity = {
            "activity_id": str(uuid.uuid4()),
            "course_id": int(payload["course_id"]),
            "topic_codes": [item["topic_code"] for item in topics],
            "sources": canonical_sources,
            "concepts": list(payload["concepts"]),
            "difficulty": str(payload["difficulty"]),
            "activity_type": str(payload["activity_type"]),
            "title": payload["title"].strip(),
            "prompt": payload["prompt"].strip(),
            "response_type": payload["response_type"],
            "created_at": self._now(),
        }
        with self._lock:
            data = self._read()
            data["activities"].append(activity)
            self._write(data)
        return deepcopy(activity)

    def activity(self, activity_id: str) -> dict:
        data = self._read()
        found = next((item for item in data["activities"] if item.get("activity_id") == activity_id), None)
        if not found:
            raise TheoryClassroomError("Actividad Theory no encontrada.")
        return deepcopy(found)
