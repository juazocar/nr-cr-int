import json
import logging
import re
import threading
import time
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo


from openai import OpenAI

from app.config import settings
from app.services.dress_code_service import DressCodeService
from app.services.today_service import TodayService
from app.services.teacher_schedule_service import TeacherScheduleService
from app.services.notprofejuan_connector import NotProfeJuanConnector
from app.services.shared_context_service import SharedContextService
from app.services.action_service import ActionService
from app.services.watch_command_router import WatchCommandRouter
from app.services.class_session_service import ClassSessionService
from app.services.personality_service import PersonalityService
from app.services.pedagogical_personality_service import PedagogicalPersonalityService
from app.services.course_technology_service import CourseTechnologyService
from app.services.agent_status_service import AgentStatusService
from app.services.exam_practice_service import ExamPracticeService
from app.services.evaluation_remote_service import EvaluationRemoteService
from app.services.student_quiz_service import StudentQuizService, StudentQuizError

_watch_logger = logging.getLogger("nora.watch.commands")

WATCH_SYSTEM_PROMPT = """
Eres NORA, Núcleo Operativo de Revisión Académica.
Estás respondiendo desde un smartwatch utilizado por un docente.

Tienes herramientas para consultar información real:
- get_courses: cursos, asignaturas, ramos y secciones.
- get_students: estudiantes pertenecientes a un curso.
- get_evaluations: evaluaciones pertenecientes a un curso.
- get_schedule: horarios o slots de presentación/reserva de un curso. No representa el horario semanal de clases del docente.
- get_reservations: reservas asociadas a una evaluación.
- get_dress_code: clima de hoy y recomendación práctica de vestimenta.
- get_academic_today: panorama académico real de hoy según los horarios/slots registrados en STH.
- search_student: busca determinísticamente un alumno por nombre o correo en todos los cursos.
- get_academic_summary: resume determinísticamente cursos y matrículas registradas.
- get_nora_today: combina contexto real disponible para responder cómo viene el día.
- get_teacher_schedule_today: consulta determinísticamente el horario docente real de hoy.
- get_teacher_schedule_tomorrow: consulta determinísticamente el horario docente real de mañana.
- create_desktop_reminder: crea un pendiente o recordatorio temporal real para que NORA Desktop lo recupere posteriormente.
- create_desktop_whiteboard_action: solicita a Desktop una pizarra con un ejemplo educativo.

Cuando necesites un course_id y el usuario sólo entregue nombre, ramo o sección, usa primero get_courses.
Cuando necesites un evaluation_id, usa primero get_evaluations si el usuario no entregó el identificador.
Puedes realizar varias llamadas de herramientas si son necesarias para resolver la consulta.
No confundas get_schedule ni get_academic_today con el horario semanal de clases del docente.
get_academic_today sólo informa actividad registrada en STH para la fecha actual.
Para buscar una persona sin conocer su curso usa search_student.
Para cantidades globales de cursos o matrículas usa get_academic_summary y respeta exactamente sus conteos.
Cuando el usuario pregunte cómo viene su día, usa get_nora_today.
Para preguntas sobre clases de hoy usa get_teacher_schedule_today; para mañana usa get_teacher_schedule_tomorrow.
En el horario docente usa exactamente current_class, next_class, first_class, last_class y minutes_until_next cuando estén presentes.
No calcules nuevamente esos valores ni inventes una clase que no aparezca en items.
REGLA CRÍTICA SOBRE CLASES: teacher_schedule y STH son fuentes distintas.
Si teacher_schedule.available es false o teacher_schedule.classes_today es null, el estado de las clases es DESCONOCIDO.
En ese caso jamás respondas "no tienes clases", "no tienes actividades académicas" ni equivalentes ante una pregunta sobre clases.
Debes decir que el horario semanal docente todavía no está conectado y, sólo como información adicional, indicar si STH tiene o no actividad registrada.
Un count=0 en STH significa únicamente cero slots/actividades STH; nunca significa cero clases.
No inventes datos académicos.
Cuando el usuario desde WATCH pida explícitamente recordar, dejar pendiente, anotar o hacer algo "cuando esté en el computador", "en Desktop" o equivalente, usa create_desktop_reminder.
Si pide abrir/preparar/mostrar EN EL COMPUTADOR o DESKTOP una pizarra con un ejemplo de programación, usa create_desktop_whiteboard_action en vez de un recordatorio. Extrae topic y language; si no indica lenguaje usa cadena vacía.
El contenido debe conservar la tarea concreta pedida por el usuario, sin inventar detalles. Sólo confirma el recordatorio si la herramienta devuelve success=true.
Si el usuario indica una fecha/hora para ese recordatorio, envía remind_at como ISO 8601 con offset y timezone=America/Santiago. Si no indica fecha/hora, ambos deben ser null.

Para los pendientes dirigidos al reloj, NORA Core es la fuente de verdad.
Cuando el usuario desde WATCH pregunte por sus pendientes, recordatorios o qué dejó pendiente para el reloj, usa get_watch_pending_context.
No inventes pendientes ni uses el contexto académico para responder esa pregunta.
Si hay varios, informa la cantidad y evita enumeraciones largas.
Cuando el usuario pida completar "ese pendiente", usa el id exacto obtenido previamente de get_watch_pending_context y llama complete_watch_pending_context.
Sólo confirma que quedó completado si complete_watch_pending_context devuelve success=true y status=COMPLETED.

Contexto de Modo Clase:
- Si existe una sesión de clase ACTIVE, recibirás su contexto explícitamente en las instrucciones. Úsalo como contexto por defecto para referencias como "esta clase", "mi curso", "mis alumnos" o "qué evaluaciones tenemos".
- La sesión activa aporta asignatura y sección, pero no reemplaza los datos de #NotProfeJuan. Para alumnos/evaluaciones identifica el curso real usando get_courses y luego consulta la herramienta correspondiente.
- Prioriza coincidencia exacta de sección y, como apoyo, nombre de asignatura. Nunca inventes un course_id.
- Si el usuario menciona explícitamente otro curso o sección, respeta esa referencia y no lo fuerces al curso activo.
- Preguntas generales no académicas siguen funcionando normalmente aunque exista Modo Clase.

Integridad de datos académicos:
- Los valores entregados por las herramientas son la fuente de verdad.
- Si una herramienta entrega count, usa EXACTAMENTE ese valor; nunca cuentes, estimes ni recalcules elementos de una lista.
- Si mencionas estudiantes, copia sus nombres desde full_name exactamente como los entrega la herramienta. No los completes, corrijas, abrevies ni reemplaces.
- Si una lista de estudiantes es larga, NO enumeres todos los nombres por defecto. Indica el count exacto y ofrece opciones breves: primeros N, siguientes N o buscar a una persona.
- Si el usuario pide "los primeros N", "los siguientes N" o una cantidad concreta, responde sólo con esa cantidad usando full_name exactamente.
- Si pregunta si una persona está en el curso, busca únicamente dentro de los estudiantes entregados por la herramienta y responde sí/no sin inventar coincidencias.
- Nunca produzcas una enumeración que vaya a quedar cortada por el límite del smartwatch.
- No deduzcas que registros duplicados son la misma persona: informa los datos tal como los entrega el sistema.

Cuando el usuario diga "dress code", pregunte cómo vestirse hoy, si necesita
chaqueta, cuánto abrigarse o algo equivalente, usa get_dress_code.

Reglas:
- Responde en español.
- Sé directa, natural y útil.
- La respuesta será escuchada por voz.
- Usa normalmente entre 1 y 3 frases.
- No uses Markdown.
- No entregues bloques de código extensos.
- Nunca inventes información académica personal.
""".strip()


def _id_tool(name: str, description: str, parameter_name: str, parameter_description: str) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                parameter_name: {"type": "integer", "description": parameter_description}
            },
            "required": [parameter_name],
            "additionalProperties": False,
        },
        "strict": True,
    }


COURSES_TOOL = {
    "type": "function",
    "name": "get_courses",
    "description": "Consulta cursos, ramos, asignaturas y secciones reales registrados para el docente.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}
STUDENTS_TOOL = _id_tool("get_students", "Consulta estudiantes reales de un curso.", "course_id", "ID del curso.")
EVALUATIONS_TOOL = _id_tool("get_evaluations", "Consulta evaluaciones reales de un curso.", "course_id", "ID del curso.")
SCHEDULE_TOOL = _id_tool(
    "get_schedule",
    "Consulta slots u horarios de presentación/reserva de un curso; no es el horario semanal de clases.",
    "course_id",
    "ID del curso.",
)
RESERVATIONS_TOOL = _id_tool(
    "get_reservations",
    "Consulta reservas reales asociadas a una evaluación.",
    "evaluation_id",
    "ID de la evaluación.",
)
DRESS_CODE_TOOL = {
    "type": "function",
    "name": "get_dress_code",
    "description": "Consulta clima de hoy y datos para recomendar vestimenta práctica.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}
ACADEMIC_TODAY_TOOL = {
    "type": "function",
    "name": "get_academic_today",
    "description": (
        "Consulta de forma determinística los horarios/slots académicos registrados en STH para hoy, "
        "incluyendo cuáles están reservados. No representa el horario semanal de clases del docente."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}

SEARCH_STUDENT_TOOL = {
    "type": "function",
    "name": "search_student",
    "description": "Busca un alumno por nombre parcial o correo en todos los cursos reales registrados.",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Nombre, parte del nombre o correo a buscar."}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}
ACADEMIC_SUMMARY_TOOL = {
    "type": "function",
    "name": "get_academic_summary",
    "description": "Obtiene conteos determinísticos de cursos y matrículas registradas por curso y en total.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}

NORA_TODAY_TOOL = {
    "type": "function",
    "name": "get_nora_today",
    "description": (
        "Combina el contexto disponible de hoy: actividad académica STH y Dress Code. "
        "No inventa el horario semanal docente si todavía no existe una fuente conectada."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}

TEACHER_SCHEDULE_TODAY_TOOL = {
    "type": "function", "name": "get_teacher_schedule_today",
    "description": "Consulta el horario semanal docente real correspondiente a hoy.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True,
}
TEACHER_SCHEDULE_TOMORROW_TOOL = {
    "type": "function", "name": "get_teacher_schedule_tomorrow",
    "description": "Consulta el horario semanal docente real correspondiente a mañana.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True,
}
GET_WATCH_PENDING_CONTEXT_TOOL = {
    "type": "function",
    "name": "get_watch_pending_context",
    "description": "Consulta los pendientes reales de Shared Context dirigidos a NORA Watch.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}
COMPLETE_WATCH_PENDING_CONTEXT_TOOL = {
    "type": "function",
    "name": "complete_watch_pending_context",
    "description": "Marca como completado un pendiente real dirigido a NORA Watch usando su id exacto.",
    "parameters": {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "UUID exacto del pendiente obtenido desde Shared Context."}
        },
        "required": ["item_id"],
        "additionalProperties": False,
    },
    "strict": True,
}
CREATE_DESKTOP_REMINDER_TOOL = {
    "type": "function",
    "name": "create_desktop_reminder",
    "description": "Crea un recordatorio o pendiente dirigido a NORA Desktop cuando el usuario lo pide explícitamente.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Tarea concreta que debe recordarse en Desktop."},
            "remind_at": {"type": ["string", "null"], "description": "Fecha/hora ISO 8601 con offset, o null si no fue solicitada."},
            "timezone": {"type": ["string", "null"], "description": "Zona IANA, normalmente America/Santiago, o null sin fecha/hora."}
        },
        "required": ["content", "remind_at", "timezone"],
        "additionalProperties": False,
    },
    "strict": True,
}
CREATE_DESKTOP_WHITEBOARD_ACTION_TOOL = {
    "type":"function","name":"create_desktop_whiteboard_action",
    "description":"Solicita a NORA Desktop abrir una pizarra con un ejemplo educativo de programación.",
    "parameters":{"type":"object","properties":{
        "topic":{"type":"string","description":"Tema del ejemplo."},
        "language":{"type":"string","description":"Lenguaje solicitado o cadena vacía."}},
        "required":["topic","language"],"additionalProperties":False},"strict":True,
}
TOOLS = [COURSES_TOOL, STUDENTS_TOOL, EVALUATIONS_TOOL, SCHEDULE_TOOL, RESERVATIONS_TOOL,
         DRESS_CODE_TOOL, ACADEMIC_TODAY_TOOL, SEARCH_STUDENT_TOOL, ACADEMIC_SUMMARY_TOOL,
         NORA_TODAY_TOOL, TEACHER_SCHEDULE_TODAY_TOOL, TEACHER_SCHEDULE_TOMORROW_TOOL,
         CREATE_DESKTOP_REMINDER_TOOL, CREATE_DESKTOP_WHITEBOARD_ACTION_TOOL, GET_WATCH_PENDING_CONTEXT_TOOL,
         COMPLETE_WATCH_PENDING_CONTEXT_TOOL]


class NoraService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self._notprofejuan = NotProfeJuanConnector()
        self._dress_code = DressCodeService()
        self._today = TodayService()
        self._teacher_schedule = TeacherScheduleService()
        self._class_session = ClassSessionService()
        self._actions = ActionService()
        self._watch_commands = WatchCommandRouter()
        self._personality = PersonalityService()
        self._pedagogical_personality = PedagogicalPersonalityService()
        self._course_technology = CourseTechnologyService()
        self._agent_status = AgentStatusService()
        self._exam_practice = ExamPracticeService(self._notprofejuan, self._client, settings.OPENAI_MODEL)
        self._evaluation_remote = EvaluationRemoteService(self._notprofejuan, self._client, settings.OPENAI_MODEL)
        self._student_quiz = StudentQuizService(self._notprofejuan)
        self._shared_context = SharedContextService()
        self._session_lock = threading.Lock()
        self._watch_sessions: dict[str, dict] = {}
        self._active_er_model: dict | None = None
        self._last_er_focus: dict | None = None

    @staticmethod
    def _normalize_search(value: str) -> str:
        value = unicodedata.normalize("NFKD", str(value or ""))
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        return " ".join(value.casefold().split())

    def _search_student(self, query: str) -> dict:
        normalized_query = self._normalize_search(query)
        if not normalized_query:
            return {"success": True, "query": query, "count": 0, "matches": []}

        matches = []
        courses = self._notprofejuan.get_courses()
        for course in courses:
            course_id = course.get("id")
            if course_id is None:
                continue
            for student in self._notprofejuan.get_students(int(course_id)):
                name = self._normalize_search(student.get("full_name"))
                email = self._normalize_search(student.get("email"))
                query_tokens = normalized_query.split()
                name_tokens = set(name.split())
                name_matches = bool(query_tokens) and all(token in name_tokens for token in query_tokens)
                email_matches = normalized_query in email
                if name_matches or email_matches:
                    matches.append({
                        "course": course,
                        "student": student,
                    })
        return {"success": True, "query": query, "count": len(matches), "matches": matches}

    def _academic_summary(self) -> dict:
        courses = self._notprofejuan.get_courses()
        course_summaries = []
        total_enrollments = 0
        unique_emails: set[str] = set()
        for course in courses:
            course_id = course.get("id")
            if course_id is None:
                continue
            students = self._notprofejuan.get_students(int(course_id))
            count = len(students)
            total_enrollments += count
            for student in students:
                email = str(student.get("email") or "").strip().casefold()
                if email:
                    unique_emails.add(email)
            course_summaries.append({
                "course": course,
                "enrollment_count": count,
            })
        return {
            "success": True,
            "course_count": len(course_summaries),
            "total_enrollments": total_enrollments,
            "unique_email_count_across_courses": len(unique_emails),
            "courses": course_summaries,
            "note": "total_enrollments cuenta matrículas por curso; una persona en dos cursos cuenta dos matrículas.",
        }

    def _academic_today_context(self) -> dict:
        today = datetime.now(ZoneInfo(settings.ACADEMIC_TIMEZONE)).date().isoformat()
        schedules = [
            item for item in self._notprofejuan.get_schedules()
            if item.get("presentation_date") == today and bool(item.get("active", True))
        ]
        courses = {
            int(item["id"]): item
            for item in self._notprofejuan.get_courses()
            if item.get("id") is not None
        }
        items = []
        for schedule in schedules:
            course_id = schedule.get("course_id")
            course = courses.get(int(course_id)) if course_id is not None else None
            items.append({
                "schedule_id": schedule.get("id"),
                "course_id": course_id,
                "course": course,
                "evaluation_id": schedule.get("evaluation_id"),
                "start_time": schedule.get("start_time"),
                "end_time": schedule.get("end_time"),
                "reserved": bool(schedule.get("reserved")),
                "booking": schedule.get("booking"),
            })
        return {
            "success": True,
            "date": today,
            "timezone": settings.ACADEMIC_TIMEZONE,
            "count": len(items),
            "reserved_count": sum(1 for item in items if item["reserved"]),
            "items": items,
            "scope": "STH schedules/slots only; not the teacher weekly class schedule",
        }

    def _execute_tool(self, name: str, arguments: str, trace_id: str = "-") -> dict:
        try:
            args = json.loads(arguments or "{}")
            if name == "get_courses":
                return {"success": True, "courses": self._notprofejuan.get_courses()}
            if name == "get_students":
                course_id = int(args["course_id"])
                students = self._notprofejuan.get_students(course_id)
                email_counts: dict[str, int] = {}
                for student in students:
                    email = str(student.get("email") or "").strip().lower()
                    if email:
                        email_counts[email] = email_counts.get(email, 0) + 1
                duplicate_emails = sorted(email for email, count in email_counts.items() if count > 1)
                return {
                    "success": True,
                    "course_id": course_id,
                    "count": len(students),
                    "unique_email_count": len(email_counts),
                    "duplicate_emails": duplicate_emails,
                    "students": students,
                }
            if name == "get_evaluations":
                return {"success": True, "evaluations": self._notprofejuan.get_evaluations(int(args["course_id"]))}
            if name == "get_schedule":
                return {"success": True, "schedule": self._notprofejuan.get_schedule(int(args["course_id"]))}
            if name == "get_reservations":
                return {"success": True, "reservations": self._notprofejuan.get_reservations(int(args["evaluation_id"]))}
            if name == "get_dress_code":
                return {"success": True, "dress_code": self._dress_code.get_recommendation()}
            if name == "search_student":
                return self._search_student(str(args["query"]))
            if name == "get_academic_summary":
                return self._academic_summary()
            if name == "get_academic_today":
                return self._academic_today_context()
            if name == "get_teacher_schedule_today":
                return {"success": True, "teacher_schedule": self._teacher_schedule.today()}
            if name == "get_teacher_schedule_tomorrow":
                return {"success": True, "teacher_schedule": self._teacher_schedule.tomorrow()}
            if name == "get_watch_pending_context":
                items = self._shared_context.pending("WATCH")
                return {
                    "success": True,
                    "target": "WATCH",
                    "count": len(items),
                    "items": items,
                }
            if name == "complete_watch_pending_context":
                item_id = str(args["item_id"]).strip()
                if not item_id:
                    return {"success": False, "error": "El identificador del pendiente está vacío."}
                # Sólo permite completar elementos cuyo destino real sea WATCH.
                pending = self._shared_context.pending("WATCH")
                if not any(str(item.get("id")) == item_id for item in pending):
                    return {"success": False, "error": "No existe un pendiente WATCH con ese identificador."}
                item = self._shared_context.complete(item_id, completed_by="WATCH")
                return {
                    "success": bool(item and item.get("status") == "COMPLETED"),
                    "item": item,
                }
            if name == "create_desktop_whiteboard_action":
                topic=str(args["topic"]).strip()
                language=str(args.get("language") or "").strip()
                if not topic:
                    return {"success":False,"error":"El tema de la pizarra no puede estar vacío."}
                _watch_logger.info(
                    "[%s] WHITEBOARD_TOOL parsed_topic=%r parsed_language=%r",
                    trace_id, topic, language,
                )
                action=self._actions.create(
                    source="WATCH",target="DESKTOP",action_type="OPEN_WHITEBOARD_EXAMPLE",
                    description=f"Abrir pizarra con un ejemplo de {topic}" + (f" en {language}" if language else ""),
                    payload={"topic":topic,"language":language,"command_source":"OPENAI_TOOL"},
                    requires_confirmation=False)
                return {"success":True,"action":action}
            if name == "create_desktop_reminder":
                content = str(args["content"]).strip()
                if not content:
                    return {"success": False, "error": "El recordatorio no puede estar vacío."}
                item = self._shared_context.create(
                    source="WATCH", target="DESKTOP", kind="REMINDER", content=content,
                    remind_at=args.get("remind_at"), timezone=args.get("timezone")
                )
                return {"success": True, "item": item}
            if name == "get_nora_today":
                academic = self._academic_today_context()
                dress = {"success": True, "dress_code": self._dress_code.get_recommendation()}
                teacher_schedule = self._teacher_schedule.today()
                return {"success": True,
                        "today": self._today.build_context(academic, dress, teacher_schedule)}
            return {"success": False, "error": "Herramienta no soportada."}
        except (RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return {"success": False, "error": "No fue posible completar la consulta solicitada."}

    def _get_session_response_id(self, session_id: str) -> str | None:
        now = time.monotonic()
        with self._session_lock:
            session = self._watch_sessions.get(session_id)
            if not session:
                return None
            if now - session["updated_at"] > settings.WATCH_SESSION_TTL_SECONDS:
                self._watch_sessions.pop(session_id, None)
                return None
            return session["response_id"]

    def _save_session_response_id(self, session_id: str, response_id: str) -> None:
        now = time.monotonic()
        with self._session_lock:
            self._watch_sessions[session_id] = {"response_id": response_id, "updated_at": now}
            if len(self._watch_sessions) > settings.WATCH_MAX_SESSIONS:
                oldest = min(self._watch_sessions, key=lambda key: self._watch_sessions[key]["updated_at"])
                self._watch_sessions.pop(oldest, None)

    @staticmethod
    def _er_slug(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or "").lower())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "entidad"

    def _build_er_foundation_model(self, expression: str) -> dict:
        """Construye un ER didáctico: 1:N, FK en N y entidad débil identificada."""
        clean = re.sub(r"[,;]+", " ", str(expression or "").strip())
        clean = re.sub(r"\s+", " ", clean)
        tokens = clean.split()
        relation_words = {
            "realiza", "realizan", "tiene", "tienen", "contiene", "contienen",
            "genera", "generan", "incluye", "incluyen", "registra", "registran",
            "pertenece", "pertenecen", "posee", "poseen", "solicita", "solicitan",
            "compra", "compran", "vende", "venden", "reserva", "reservan",
            "cursa", "cursan", "matricula", "matriculan", "asigna", "asignan",
        }
        connectors = {"y", "con", "a", "al", "de", "del", "en", "un", "una", "el", "la", "los", "las"}
        relation_index = next((i for i, t in enumerate(tokens) if t.lower() in relation_words), None)
        relation_name = "RELACIONA"
        raw_entities = []
        weak_entity_name = None
        owner_name = None

        if relation_index is not None and 0 < relation_index < len(tokens) - 1:
            relation_name = tokens[relation_index].upper()
            left = [t for t in tokens[:relation_index] if t.lower() not in connectors]
            right = [t for t in tokens[relation_index + 1:] if t.lower() not in connectors]
            if left and right:
                owner_name = left[-1]
                # Patrón docente frecuente: "pedido tiene detalle pedido".
                # Conserva DETALLE_PEDIDO como una sola entidad y la marca débil.
                if right[0].lower() in {"detalle", "linea", "línea", "item", "ítem"}:
                    weak_entity_name = "_".join(right)
                    raw_entities = [owner_name, weak_entity_name]
                else:
                    raw_entities = [owner_name, right[-1]]

        if not raw_entities:
            raw_entities = [t for t in tokens if t.lower() not in connectors and t.lower() not in relation_words]

        unique = []
        for item in raw_entities:
            if item.lower() not in {x.lower() for x in unique}:
                unique.append(item)
        raw_entities = unique[:6]

        model_entities = []
        relationships = []
        previous = None
        for raw_name in raw_entities:
            name = raw_name.upper()
            slug = self._er_slug(raw_name)
            is_weak = weak_entity_name is not None and raw_name.lower() == weak_entity_name.lower()

            if is_weak and previous is not None:
                prev_slug = self._er_slug(previous)
                attrs = [
                    {"name": f"id_{prev_slug}", "key": "PK/FK"},
                    {"name": "nro_detalle", "key": "PARTIAL_KEY"},
                    {"name": "cantidad", "key": ""},
                ]
            else:
                attrs = [{"name": f"id_{slug}", "key": "PK"}, {"name": "nombre" if previous is None else "fecha", "key": ""}]
                if previous is not None:
                    prev_slug = self._er_slug(previous)
                    attrs.insert(1, {"name": f"id_{prev_slug}", "key": "FK"})

            if previous is not None:
                prev_slug = self._er_slug(previous)
                relationships.append({
                    "name": relation_name if len(raw_entities) == 2 else "RELACIONA",
                    "from": previous.upper(), "to": name,
                    "cardinality_from": "1", "cardinality_to": "N",
                    "fk_entity": name, "fk_attribute": f"id_{prev_slug}",
                    "identifying": bool(is_weak),
                })

            model_entities.append({
                "name": name,
                "type": "WEAK" if is_weak else "STRONG",
                "owner": previous.upper() if is_weak and previous else None,
                "attributes": attrs,
            })
            previous = raw_name

        return {
            "diagram_type": "ER", "notation": "RELATIONAL",
            "title": " · ".join(e["name"] for e in model_entities),
            "source_expression": clean, "entities": model_entities, "relationships": relationships,
        }

    def _answer_active_er_query(self, intent: str) -> str:
        model = self._active_er_model
        if not isinstance(model, dict) or not model.get("entities"):
            return "No tengo un modelo entidad relación activo. Abre uno primero en la pizarra."
        entities = model.get("entities") or []
        relationships = model.get("relationships") or []
        focus = None
        answer = None
        if intent == "ER_QUERY_WEAK":
            entity = next((e for e in entities if str(e.get("type") or "").upper() == "WEAK"), None)
            if entity:
                focus={"kind":"entity","entity":entity.get("name")}
                answer=f"La entidad débil es {entity.get('name')}. Su identificación depende de su entidad propietaria."
            else: answer="El modelo activo no tiene una entidad débil."
        elif intent == "ER_QUERY_STRONG":
            entity = next((e for e in entities if str(e.get("type") or "").upper() == "STRONG"), None)
            if entity:
                focus={"kind":"entity","entity":entity.get("name")}
                answer=f"La entidad fuerte es {entity.get('name')}. Puede identificarse mediante su propia clave primaria."
            else: answer="El modelo activo no tiene una entidad fuerte identificada."
        elif intent == "ER_QUERY_FK":
            hit=None
            for e in entities:
                for a in e.get("attributes") or []:
                    if "FK" in str(a.get("key") or ""):
                        hit=(e,a); break
                if hit: break
            if hit:
                e,a=hit; focus={"kind":"attribute","entity":e.get("name"),"attribute":a.get("name")}
                answer=f"La clave foránea está en {e.get('name')}: {a.get('name')}. Está en el lado que referencia a la entidad propietaria."
            else: answer="El modelo activo no tiene una clave foránea marcada."
        elif intent == "ER_QUERY_PARTIAL_KEY":
            hit=None
            for e in entities:
                for a in e.get("attributes") or []:
                    if str(a.get("key") or "") == "PARTIAL_KEY": hit=(e,a); break
                if hit: break
            if hit:
                e,a=hit; focus={"kind":"attribute","entity":e.get("name"),"attribute":a.get("name")}
                answer=f"La clave parcial es {a.get('name')} de {e.get('name')}. Se combina con la clave de la entidad propietaria para identificar cada ocurrencia."
            else: answer="El modelo activo no tiene una clave parcial marcada."
        elif intent == "ER_QUERY_CARDINALITY":
            rel=relationships[0] if relationships else None
            if rel:
                focus={"kind":"relationship","from":rel.get("from"),"to":rel.get("to")}
                answer=f"La cardinalidad es {rel.get('cardinality_from')} a {rel.get('cardinality_to')} entre {rel.get('from')} y {rel.get('to')}."
            else: answer="El modelo activo no tiene relaciones para explicar."
        elif intent == "ER_QUERY_IDENTIFYING":
            rel=next((r for r in relationships if r.get("identifying")),None)
            if rel:
                focus={"kind":"relationship","from":rel.get("from"),"to":rel.get("to")}
                answer=f"La relación identificadora es {rel.get('name')}, entre {rel.get('from')} y {rel.get('to')}. Participa en la identificación de la entidad débil."
            else: answer="El modelo activo no tiene una relación identificadora."
        elif intent == "ER_QUERY_WHY":
            if self._last_er_focus:
                kind=self._last_er_focus.get("kind")
                if kind == "attribute": answer="Porque ese atributo materializa la dependencia del modelo: referencia la clave de la entidad relacionada y permite mantener la integridad referencial."
                elif kind == "entity": answer="Porque su clasificación depende de cómo se identifica: una entidad débil necesita la clave de su propietaria; una fuerte posee identificación propia."
                else: answer="Porque la relación y sus cardinalidades expresan cuántas ocurrencias de una entidad pueden asociarse con la otra."
                focus=self._last_er_focus
            else: answer="Haz primero una pregunta concreta sobre la entidad, la clave o la relación y luego puedo explicarte por qué."
        if focus:
            self._last_er_focus=focus
            self._actions.create(source="WATCH",target="DESKTOP",action_type="HIGHLIGHT_ER_ELEMENT",
                description="Resaltar elemento del modelo ER activo",payload={"focus":focus,"command_source":"WATCH_SHORT_COMMAND"},requires_confirmation=False)
        return answer or "No pude resolver esa consulta sobre el modelo activo."

    def _short_watch_command(self, question: str, source: str = "WATCH") -> str | None:
        command = self._watch_commands.route(question)
        _watch_logger.info("watch_command_received raw=%r route=%s args=%r", question, command.intent if command else None, command.args if command else None)
        if command is None:
            return None
        if command.intent in {"EVALUATION_VIEW", "EVALUATION_RUBRIC", "EVALUATION_REVIEW", "EVALUATION_STATUS"}:
            active = self._class_session.active()
            if not active:
                return "Primero inicia el modo clase para identificar correctamente el curso."
            try:
                ctx = self._evaluation_remote.context(active)
                if command.intent == "EVALUATION_VIEW": title, text = "EVALUACIÓN", self._evaluation_remote.view_text(ctx)
                elif command.intent == "EVALUATION_RUBRIC": title, text = "RÚBRICA", self._evaluation_remote.rubric_text(ctx)
                elif command.intent == "EVALUATION_REVIEW": title, text = "REPASO DE EVALUACIÓN", self._evaluation_remote.review_text(ctx)
                else: title, text = "ESTADO DE EVALUACIÓN", self._evaluation_remote.status_text(ctx)
                blueprint = ctx["blueprint"]
                self._actions.create(source=source,target="DESKTOP",action_type="SHOW_EVALUATION_MATERIAL",
                    description=f"Mostrar {title.lower()} en la Pizarra de NORA",
                    payload={"title":title,"text":text,"course_id":blueprint.get("course_id"),"evaluation_id":blueprint.get("evaluation_id"),"command_source":f"{source}_SHORT_COMMAND"},
                    requires_confirmation=False)
                labels={"EVALUATION_VIEW":"la evaluación","EVALUATION_RUBRIC":"la rúbrica","EVALUATION_REVIEW":"el repaso","EVALUATION_STATUS":"el estado de la evaluación"}
                return f"Listo. Envié {labels[command.intent]} a la pizarra."
            except RuntimeError as exc:
                _watch_logger.warning("evaluation_remote_failed intent=%s reason=%s", command.intent, str(exc))
                return str(exc)
        if command.intent == "EXAM_PRACTICE":
            active = self._class_session.active()
            if not active:
                return "Primero inicia el modo clase para identificar correctamente el curso."
            try:
                result = self._exam_practice.generate(active)
                _watch_logger.info(
                    "exam_practice_generated course_id=%r evaluation_id=%r attempts=%s",
                    result["blueprint"].get("course_id"), result["blueprint"].get("evaluation_id"), result.get("attempts"),
                )
                blueprint = result["blueprint"]
                self._actions.create(
                    source=source,
                    target="DESKTOP",
                    action_type="SHOW_EXAM_PRACTICE",
                    description="Mostrar ejercicio tipo prueba en la Pizarra de NORA",
                    payload={
                        "title": "EJERCICIO TIPO PRUEBA",
                        "text": result["exercise"],
                        "course_id": blueprint.get("course_id"),
                        "course_name": blueprint.get("course_name"),
                        "evaluation_id": blueprint.get("evaluation_id"),
                        "evaluation_name": blueprint.get("evaluation_name"),
                        "command_source": f"{source}_SHORT_COMMAND",
                    },
                    requires_confirmation=False,
                )
                return "Listo. Generé un ejercicio tipo prueba y lo envié a la pizarra."
            except RuntimeError as exc:
                _watch_logger.warning("exam_practice_failed reason=%s", str(exc))
                return str(exc)
        if command.intent == "CLASSROOM_INTERVENTION":
            mode = str(command.args.get("mode") or "FREE").strip().upper()
            active = self._class_session.active()
            if not active:
                return "Primero inicia el modo clase para que pueda intervenir con el contexto correcto."
            language, language_source = self._course_technology.resolve("", active)
            context = {
                "course": active.get("course"),
                "section": active.get("section"),
                "technology": language or None,
                "technology_source": language_source,
            }
            if not self._client:
                return "No puedo preparar la intervención porque OpenAI no está configurado."
            try:
                response = self._client.responses.create(
                    model=settings.OPENAI_MODEL,
                    instructions=self._pedagogical_personality.instructions(mode, context),
                    input="Genera ahora la intervención pedagógica solicitada.",
                )
                speech = (response.output_text or "").strip()
            except Exception:
                _watch_logger.exception("classroom_intervention_generation_failed mode=%s", mode)
                return "No pude preparar la intervención de aula en este momento."
            if not speech:
                return "No pude preparar la intervención de aula en este momento."
            self._actions.create(
                source=source, target="DESKTOP", action_type="CLASSROOM_INTERVENTION",
                description=f"Intervención pedagógica NORA: {mode}",
                payload={"mode": mode, "text": speech, "class_context": context},
                requires_confirmation=False,
            )
            _watch_logger.info("classroom_intervention_created mode=%s course=%r language=%r", mode, active.get("course"), language)
            return "De acuerdo."
        if command.intent in {"LIVE_QUIZ_START","LIVE_QUIZ_NEXT","LIVE_QUIZ_STATUS","LIVE_QUIZ_RESULTS","LIVE_QUIZ_CLOSE"}:
            try:
                current=self._student_quiz.latest_open(); sid=current["id"]
                if command.intent == "LIVE_QUIZ_START": quiz=self._student_quiz.start(sid)
                elif command.intent == "LIVE_QUIZ_NEXT": quiz=self._student_quiz.next_question(sid)
                elif command.intent == "LIVE_QUIZ_RESULTS": quiz=self._student_quiz.results(sid)
                elif command.intent == "LIVE_QUIZ_CLOSE": quiz=self._student_quiz.close(sid)
                else: quiz=self._student_quiz.status(sid)
                self._actions.create(source=source,target="DESKTOP",action_type="SHOW_STUDENT_LIVE_QUIZ",description=f"Actualizar Live Quiz: {quiz.get('title','Quiz')}",payload={"quiz":quiz,"student_url":"https://tech-solutions.cl/sth/nora-student/"},requires_confirmation=False)
                phase=quiz.get("phase"); participants=quiz.get("participants",0)
                aq=quiz.get("active_question") or {}
                if command.intent == "LIVE_QUIZ_CLOSE": return "Quiz finalizado."
                if phase == "QUESTION": return f"Pregunta {aq.get('number',1)} de {aq.get('total',len(quiz.get('questions',[])))}. {participants} alumnos conectados."
                if phase == "RESULTS": return f"Resultados listos. {quiz.get('correct',0)} correctas y {quiz.get('incorrect',0)} incorrectas."
                return f"Quiz en espera. Código {quiz.get('code')}. {participants} alumnos conectados."
            except StudentQuizError as exc:
                return str(exc)
        if command.intent == "QUIZ_INCOMPLETE":
            return "Indícame el tema del quiz. Por ejemplo: quiz herencia Kotlin."
        if command.intent == "CREATE_LIVE_QUIZ":
            topic = str(command.args.get("topic") or "").strip()
            language, language_source = self._course_technology.resolve(
                str(command.args.get("language") or "").strip(), self._class_session.active()
            )
            _watch_logger.info("quiz_language_resolved topic=%r language=%r source=%s", topic, language, language_source)
            self._actions.create(
                source=source, target="DESKTOP", action_type="CREATE_LIVE_QUIZ",
                description=f"Crear quiz de {topic}" + (f" en {language}" if language else ""),
                payload={
                    "topic": topic,
                    "language": language,
                    "language_source": language_source,
                    "command_source": f"{source}_SHORT_COMMAND",
                },
                requires_confirmation=False,
            )
            return f"Listo. Estoy preparando un quiz de {topic}" + (f" en {language}." if language else ".")
        if command.intent == "WHITEBOARD_INCOMPLETE":
            return "No pude reconocer el tema de la pizarra. Repítelo, por favor."
        if command.intent == "OPEN_ER_DIAGRAM":
            expression = str(command.args.get("expression") or "").strip()
            model = self._build_er_foundation_model(expression)
            self._active_er_model = model
            self._last_er_focus = None
            entity_names = [str(e.get("name") or "") for e in model.get("entities", [])]
            self._actions.create(
                source="WATCH", target="DESKTOP", action_type="OPEN_ER_DIAGRAM",
                description=f"Abrir diagrama ER de {expression}",
                payload={"model": model, "mode": command.args.get("mode", "replace"), "command_source": "WATCH_SHORT_COMMAND"},
                requires_confirmation=False,
            )
            return f"Listo. Envié el modelo entidad relación de {' y '.join(entity_names)} al computador."
        if command.intent.startswith("ER_QUERY_"):
            return self._answer_active_er_query(command.intent)
        if command.intent == "OPEN_WHITEBOARD":
            topic = command.args["topic"]
            language, language_source = self._course_technology.resolve(
                command.args.get("language") or "", self._class_session.active()
            )
            _watch_logger.info("whiteboard_language_resolved topic=%r language=%r source=%s", topic, language, language_source)
            action = self._actions.create(
                source="WATCH", target="DESKTOP",
                action_type="OPEN_WHITEBOARD_EXAMPLE",
                description=f"Abrir pizarra con un ejemplo de {topic}" + (f" en {language}" if language else ""),
                payload={"topic": topic, "language": language, "language_source": language_source, "mode": command.args.get("mode", "replace"), "command_source": f"{source}_SHORT_COMMAND"},
                requires_confirmation=False,
            )
            return f"Listo. Envié la pizarra de {topic}" + (f" en {language} al computador." if language else " al computador.")
        if command.intent == "START_CLASS_MODE":
            active=self._class_session.active()
            if active:
                course=active.get("course") or "la clase"; section=active.get("section")
                return f"El modo clase ya está activo para {course}" + (f", sección {section}." if section else ".")
            schedule=self._teacher_schedule.today()
            if not schedule.get("available"):
                return "No puedo iniciar el modo clase porque el horario docente no está disponible."
            selected=schedule.get("current_class") or schedule.get("next_class")
            if not selected:
                return "No hay una clase actual ni una próxima clase registrada para hoy. No inicié el modo clase."
            result=self._class_session.start(selected,source=source)
            session=result["session"]
            self._actions.create(source=source,target="DESKTOP",action_type="START_CLASS_MODE",
                description=f"Iniciar modo clase: {session.get('course') or 'clase'}",payload={"session":session,"command_source":f"{source}_CLASS_COMMAND"},requires_confirmation=False)
            course=session.get("course") or "clase"; section=session.get("section")
            return f"Modo clase iniciado. {course}" + (f", sección {section}." if section else ".")
        if command.intent == "END_CLASS_MODE":
            session=self._class_session.finish()
            if not session:
                return "No hay un modo clase activo para finalizar."
            self._actions.create(source=source,target="DESKTOP",action_type="END_CLASS_MODE",
                description=f"Finalizar modo clase: {session.get('course') or 'clase'}",payload={"session":session,"command_source":f"{source}_CLASS_COMMAND"},requires_confirmation=False)
            return f"Clase finalizada. {session.get('course') or ''}".strip()
        if command.intent == "CLASS_MODE_STATUS":
            session=self._class_session.active()
            if not session: return "No hay un modo clase activo."
            course=session.get("course") or "clase"; section=session.get("section")
            return f"El modo clase está activo para {course}" + (f", sección {section}." if section else ".")
        if command.intent == "CLASS_TIME_REMAINING":
            session=self._class_session.active()
            if not session:
                return "No hay un modo clase activo."
            end_time=session.get("end_time")
            try:
                hour, minute = map(int, str(end_time).split(":", 1))
                now=datetime.now(ZoneInfo(settings.ACADEMIC_TIMEZONE))
                end=now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                remaining=max(0, int((end-now).total_seconds() // 60))
            except (TypeError, ValueError):
                return "El modo clase está activo, pero no tengo una hora de término válida."
            if remaining <= 0:
                return "La hora programada de término de la clase ya fue alcanzada."
            if remaining == 1:
                return "Queda aproximadamente un minuto de clase."
            return f"Quedan aproximadamente {remaining} minutos de clase."
        if command.intent == "CLASSES_TODAY":
            data = self._teacher_schedule.today()
            return self._render_short_classes(data, "hoy")
        if command.intent == "CLASSES_TOMORROW":
            data = self._teacher_schedule.tomorrow()
            return self._render_short_classes(data, "mañana")
        if command.intent == "PENDING":
            items = self._shared_context.pending("WATCH")
            count = len(items)
            if count == 0: return "No tienes pendientes en el reloj."
            if count == 1: return f"Tienes un pendiente: {items[0].get('content', '')}."
            return f"Tienes {count} pendientes en el reloj."
        if command.intent == "ACADEMIC_SUMMARY":
            data = self._notprofejuan.get_academic_summary()
            return f"Tienes {data.get('course_count', 0)} cursos y {data.get('student_count', 0)} matrículas registradas."
        return None

    @staticmethod
    def _render_short_classes(data: dict, label: str) -> str:
        classes = data.get("classes") if isinstance(data, dict) else None
        if classes is None:
            return f"No tengo disponible tu horario docente de {label}."
        if not classes:
            return f"No tienes clases registradas para {label}."
        first = classes[0]
        subject = first.get("subject") or "clase"
        start = first.get("start") or ""
        if len(classes) == 1:
            return f"Tienes una clase {label}: {subject}" + (f" a las {start}." if start else ".")
        return f"Tienes {len(classes)} clases {label}. La primera es {subject}" + (f" a las {start}." if start else ".")

    def ask_watch(self, question: str, client: str = "WATCH", session_id: str = "default", trace_id: str = "-") -> str:
        effective_client = (client or "WATCH").strip().upper()
        normalized = WatchCommandRouter._norm(question)
        # v0.9.6.2 · Classroom Timer Remote. Acciones determinísticas del Watch;
        # Desktop mantiene su propio reloj y sólo recibe comandos discretos.
        if effective_client == "WATCH" and normalized.startswith("timer desktop "):
            timer_command = normalized.removeprefix("timer desktop ").strip()
            action_type = None
            payload = {}
            response = "Comando de temporizador enviado."
            if timer_command.startswith("iniciar "):
                try:
                    minutes = max(1, min(120, int(timer_command.split()[-1])))
                except (TypeError, ValueError):
                    return "No pude interpretar la duración del temporizador."
                action_type = "START_CLASSROOM_TIMER"
                payload = {"seconds": minutes * 60}
                response = f"Temporizador de aula iniciado por {minutes} minutos."
            elif timer_command == "pausar":
                action_type = "PAUSE_CLASSROOM_TIMER"
                response = "Temporizador de aula pausado."
            elif timer_command in {"continuar", "reanudar"}:
                action_type = "RESUME_CLASSROOM_TIMER"
                response = "Temporizador de aula reanudado."
            elif timer_command in {"mas 1", "+1"}:
                action_type = "ADJUST_CLASSROOM_TIMER"
                payload = {"delta_seconds": 60}
                response = "Agregué un minuto al temporizador de aula."
            elif timer_command in {"menos 1", "-1"}:
                action_type = "ADJUST_CLASSROOM_TIMER"
                payload = {"delta_seconds": -60}
                response = "Resté un minuto al temporizador de aula."
            elif timer_command in {"cancelar", "detener", "cerrar"}:
                action_type = "STOP_CLASSROOM_TIMER"
                response = "Temporizador de aula cerrado."
            if action_type is None:
                return "No reconocí ese comando del temporizador."
            self._actions.create(
                source="WATCH", target="DESKTOP", action_type=action_type,
                description="Control remoto del temporizador de aula",
                payload=payload, requires_confirmation=False,
            )
            return response

        # v0.9.5.0 · Ciclo de vida Desktop. Comandos determinísticos del Watch;
        # nunca pasan por OpenAI ni permiten ejecutar comandos arbitrarios.
        if effective_client == "WATCH":
            if normalized in {"abrir nora desktop", "abrir desktop", "nora desktop on"}:
                self._actions.create(source="WATCH", target="AGENT", action_type="START_NORA_DESKTOP", description="Iniciar NORA Desktop", payload={}, requires_confirmation=False)
                return "Abriendo NORA Desktop."
            if normalized in {"cerrar nora desktop", "cerrar desktop", "nora desktop off"}:
                self._actions.create(source="WATCH", target="AGENT", action_type="STOP_NORA_DESKTOP", description="Cerrar NORA Desktop de forma limpia", payload={}, requires_confirmation=False)
                return "Solicitando cierre de NORA Desktop."
            if normalized in {"estado nora desktop", "estado desktop", "nora desktop estado"}:
                st=self._agent_status.status()
                if not st.get("agent_online"): return "El agente del Mac no está disponible."
                return "El Mac está conectado y NORA Desktop está abierta." if st.get("desktop_running") else "El Mac está conectado y NORA Desktop está cerrada."
        detected = self._watch_commands.route(question) if effective_client in {"WATCH", "DESKTOP"} else None
        _watch_logger.info(
            "[%s] ROUTER raw=%r normalized=%r client=%r effective_client=%r intent=%r args=%r",
            trace_id, question, normalized, client, effective_client,
            detected.intent if detected else None, detected.args if detected else None,
        )
        class_intents = {"START_CLASS_MODE", "END_CLASS_MODE", "CLASS_MODE_STATUS", "CLASS_TIME_REMAINING"}
        if effective_client == "WATCH" or (effective_client == "DESKTOP" and detected and detected.intent in class_intents):
            short_answer = self._short_watch_command(question, source=effective_client)
            if short_answer is not None:
                _watch_logger.info("[%s] PATH selected=SHORT_COMMAND source=%s answer=%r", trace_id, effective_client, short_answer)
                return short_answer
            # Safety boundary: a Watch phrase that clearly looks like a pizarra
            # command must never be reinterpreted by the OpenAI tool path.
            first = normalized.split(" ", 1)[0] if normalized else ""
            if first in {"pizarra","pizarron","pizara","pisarra","pisara","pissarra","izarra","izarron"}:
                _watch_logger.warning("whiteboard_command_blocked_from_openai raw=%r", question)
                return "No pude interpretar el comando de pizarra. Repítelo, por favor."
            if first in {"quiz", "quizz"}:
                _watch_logger.warning("quiz_command_blocked_from_openai raw=%r", question)
                return "No pude interpretar el comando de quiz. Repítelo, por favor."
        # Personality Layer: sólo después de los comandos determinísticos.
        # La creatividad queda aislada de acciones y datos académicos.
        personality_intent = self._personality.detect(question) if effective_client == "WATCH" else None
        if personality_intent:
            _watch_logger.info("[%s] PATH selected=PERSONALITY intent=%s", trace_id, personality_intent)
            if not self._client:
                return "Hoy tuve diferencias creativas con la realidad. Prometo comportarme mejor en la próxima clase."
            try:
                personality_response = self._client.responses.create(
                    model=settings.OPENAI_MODEL,
                    instructions=self._personality.instructions(personality_intent),
                    input=question.strip(),
                )
                personality_answer = (personality_response.output_text or "").strip()
                if personality_answer:
                    # Los comandos sociales cortos se representan en Desktop:
                    # Watch actúa sólo como disparador para que la sala escuche a NORA.
                    if normalized in {"excusas", "excusa", "nora excusas", "nora excusa"}:
                        self._actions.create(
                            source="WATCH",
                            target="DESKTOP",
                            action_type="NORA_PERSONALITY_RESPONSE",
                            description="NORA responde desde Desktop",
                            payload={"intent": personality_intent, "text": personality_answer},
                            requires_confirmation=False,
                        )
                        _watch_logger.info("[%s] PERSONALITY desktop_bridge intent=%s", trace_id, personality_intent)
                        return "De acuerdo."
                    return personality_answer[:settings.WATCH_MAX_ANSWER_CHARS].strip()
            except Exception:
                _watch_logger.exception("[%s] PERSONALITY generation failed", trace_id)
            return "Hoy tuve diferencias creativas con la realidad. Prometo comportarme mejor en la próxima clase."

        _watch_logger.info("[%s] PATH selected=OPENAI", trace_id)
        if not self._client:
            return "NORA Core está funcionando, pero todavía no tiene configurada la clave de OpenAI."

        local_now = datetime.now(ZoneInfo(settings.SHARED_CONTEXT_TIMEZONE))
        active_class = self._class_session.active()
        class_context = ""
        if active_class:
            class_context = (
                "\n\nMODO CLASE ACTIVO (contexto por defecto, no inventar datos): "
                + json.dumps({
                    "course": active_class.get("course"),
                    "section": active_class.get("section"),
                    "start_time": active_class.get("start_time"),
                    "end_time": active_class.get("end_time"),
                    "class_date": active_class.get("class_date"),
                }, ensure_ascii=False)
            )
        temporal_instructions = (
            WATCH_SYSTEM_PROMPT
            + f"\n\nContexto temporal actual: {local_now.isoformat()} "
              f"({settings.SHARED_CONTEXT_TIMEZONE}). Usa este valor para interpretar hoy, mañana y horas relativas."
            + class_context
        )
        request = {
            "model": settings.OPENAI_MODEL,
            "instructions": temporal_instructions,
            "input": question.strip(),
            "tools": TOOLS,
        }
        client_name = (client or "WATCH").strip().upper()[:40] or "WATCH"
        session_name = (session_id or "default").strip()[:80] or "default"
        session_key = f"{client_name}:{session_name}"

        previous_response_id = self._get_session_response_id(session_key)
        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        _watch_logger.info(
            "[%s] OPENAI_REQUEST model=%r input=%r previous_response_id_present=%s",
            trace_id, settings.OPENAI_MODEL, question.strip(), bool(previous_response_id),
        )
        try:
            response = self._client.responses.create(**request)
        except Exception:
            # If OpenAI no longer accepts a stored response id, retry as a fresh session.
            if not previous_response_id:
                raise
            with self._session_lock:
                self._watch_sessions.pop(session_key, None)
            request.pop("previous_response_id", None)
            response = self._client.responses.create(**request)

        # Allow chained academic lookups: e.g. course name -> course_id -> students.
        for _ in range(4):
            calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
            if not calls:
                break

            tool_outputs = []
            for item in calls:
                raw_arguments = getattr(item, "arguments", "{}")
                _watch_logger.info(
                    "[%s] OPENAI_TOOL name=%r arguments=%s",
                    trace_id, item.name, raw_arguments,
                )
                result = self._execute_tool(item.name, raw_arguments, trace_id=trace_id)
                _watch_logger.info(
                    "[%s] OPENAI_TOOL_RESULT name=%r result=%r",
                    trace_id, item.name, result,
                )
                tool_outputs.append({
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                })

            response = self._client.responses.create(
                model=settings.OPENAI_MODEL,
                instructions=temporal_instructions,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=TOOLS,
            )

        self._save_session_response_id(session_key, response.id)

        answer = (response.output_text or "").strip()
        if not answer:
            return "No pude generar una respuesta en este momento."

        if len(answer) > settings.WATCH_MAX_ANSWER_CHARS:
            limit = settings.WATCH_MAX_ANSWER_CHARS
            shortened = answer[:limit]
            sentence_end = max(shortened.rfind("."), shortened.rfind("?"), shortened.rfind("!"))
            if sentence_end >= 40:
                answer = shortened[:sentence_end + 1].strip()
            else:
                answer = "La respuesta es demasiado extensa para el reloj. Pídeme una parte concreta, por ejemplo los primeros cinco, los siguientes cinco o un alumno específico."
        return answer
