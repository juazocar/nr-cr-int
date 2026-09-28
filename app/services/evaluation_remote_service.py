"""Material de evaluación para control remoto desde NORA Watch."""
from __future__ import annotations
import json
from app.services.exam_practice_service import ExamPracticeService

class EvaluationRemoteService:
    def __init__(self, connector, openai_client, model: str) -> None:
        self._connector = connector; self._client = openai_client; self._model = model
        self._practice = ExamPracticeService(connector, openai_client, model)

    def context(self, session: dict) -> dict:
        course = self._practice._resolve_course(session)
        evaluation = self._practice._latest_evaluation(int(course["id"]))
        eid = int(evaluation["id"])
        detail = self._connector.get_evaluation(eid)
        exercises = self._connector.get_evaluation_exercises(eid)
        rubric = self._connector.get_evaluation_rubric(eid)
        blueprint = self._practice._build_blueprint(course, detail, exercises, rubric)
        return {"course": course, "evaluation": detail, "rubric": rubric, "blueprint": blueprint}

    def view_text(self, ctx: dict) -> str:
        b=ctx["blueprint"]; e=ctx["evaluation"]
        dims=" · ".join(b.get("dimensions") or []) or "Sin dimensiones registradas"
        return (f"EVALUACIÓN\n\n{e.get('name') or 'Evaluación'}\n\n"
                f"Curso: {b.get('course_name') or '-'}\n"
                f"Descripción: {e.get('description') or '-'}\n"
                f"Ejercicios: {b.get('exercise_count', 0)}\nPuntaje total: {b.get('total_points', 0):g}\n"
                f"Modalidad de revisión: {e.get('review_mode') or '-'}\n\nCOMPETENCIAS / DIMENSIONES\n{dims}")

    def rubric_text(self, ctx: dict) -> str:
        r=ctx["rubric"]; lines=["RÚBRICA", "", str(r.get("name") or "Rúbrica de evaluación"), ""]
        for item in r.get("items") or []:
            weight=item.get("weight_percent")
            suffix=f" ({weight:g}%)" if isinstance(weight,(int,float)) else ""
            lines.append(f"{item.get('code') or ''} · {item.get('title') or item.get('dimension') or 'Criterio'}{suffix}")
            lines.append(str(item.get("description") or "")); lines.append("")
        lines.append("Nota: las ponderaciones se muestran exactamente como las registra #NotProfeJuan; NORA no las reinterpreta.")
        return "\n".join(lines).strip()

    def status_text(self, ctx: dict) -> str:
        b=ctx["blueprint"]; e=ctx["evaluation"]
        active="ACTIVA" if bool(e.get("active", True)) else "INACTIVA"
        return (f"ESTADO DE EVALUACIÓN\n\n{e.get('name') or 'Evaluación'}\nCurso: {b.get('course_name') or '-'}\n"
                f"Estado en sistema: {active}\nID: {e.get('id')}\nRevisión: {e.get('review_mode') or '-'}\n"
                f"Intentos IA permitidos registrados: {e.get('max_ai_attempts') if e.get('max_ai_attempts') is not None else '-'}\n\n"
                "#NotProfeJuan no entrega en este contrato una ventana de inicio/fin de rendición; NORA no infiere que la prueba esté en curso.")

    def review_text(self, ctx: dict) -> str:
        if not self._client: raise RuntimeError("OpenAI no está configurado para generar el repaso.")
        b=ctx["blueprint"]
        safe={k:v for k,v in b.items() if k not in {"source_exercises"}}
        instructions=("Eres NORA. Crea un REPASO PREVIO breve y didáctico para una clase, basado exclusivamente en las competencias y criterios del blueprint. "
                      "No reveles, reconstruyas ni imites el enunciado de la evaluación. No entregues respuestas de una prueba. "
                      "Organiza: Objetivos de repaso, conceptos clave, errores frecuentes y mini preguntas de comprobación sin solución. Español claro, apto para pizarra.")
        response=self._client.responses.create(model=self._model,instructions=instructions,input="ASSESSMENT_BLUEPRINT:\n"+json.dumps(safe,ensure_ascii=False))
        text=(response.output_text or "").strip()
        if not text: raise RuntimeError("No pude generar el repaso de la evaluación.")
        return text
