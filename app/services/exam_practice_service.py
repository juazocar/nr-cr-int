"""Generación de ejercicios de práctica basados en la huella pedagógica de una evaluación real."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher


logger = logging.getLogger("nora.exam_practice")


class ExamPracticeService:
    def __init__(self, connector, openai_client, model: str) -> None:
        self._connector = connector
        self._client = openai_client
        self._model = model

    @staticmethod
    def _norm(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or "").casefold())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return " ".join(re.findall(r"[a-z0-9+#]+", text))

    def _resolve_course(self, session: dict) -> dict:
        wanted = self._norm(session.get("course"))
        section = self._norm(session.get("section"))
        if not wanted:
            raise RuntimeError("La sesión activa no identifica la asignatura.")
        courses = [c for c in self._connector.get_courses() if c.get("id") is not None and bool(c.get("active", True))]
        exact, partial = [], []
        for course in courses:
            names = [course.get(k) for k in ("name", "course_name", "subject", "title", "code")]
            normalized = [self._norm(v) for v in names if v]
            course_section = self._norm(course.get("section"))
            if wanted in normalized:
                (exact if not section or not course_section or section == course_section else partial).append(course)
            elif any(wanted in value or value in wanted for value in normalized if value):
                partial.append(course)
        candidates = exact or partial
        if section:
            section_matches = [c for c in candidates if self._norm(c.get("section")) == section]
            if section_matches:
                candidates = section_matches
        if len(candidates) != 1:
            logger.warning(
                "course_resolution_failed session_course=%r session_section=%r candidates=%s",
                session.get("course"),
                session.get("section"),
                [
                    {
                        "id": c.get("id"),
                        "name": c.get("name") or c.get("course_name") or c.get("subject"),
                        "section": c.get("section"),
                    }
                    for c in candidates
                ],
            )
            raise RuntimeError("No pude identificar de forma inequívoca el curso activo en #NotProfeJuan.")
        return candidates[0]

    def _latest_evaluation(self, course_id: int) -> dict:
        evaluations = [e for e in self._connector.get_evaluations(course_id) if e.get("id") is not None and bool(e.get("active", True))]
        if not evaluations:
            raise RuntimeError("El curso activo no tiene evaluaciones disponibles para generar práctica.")
        return max(evaluations, key=lambda e: int(e.get("id") or 0))

    @staticmethod
    def _build_blueprint(course: dict, evaluation: dict, exercise_bundle: dict, rubric: dict) -> dict:
        exercises = exercise_bundle.get("exercises") if isinstance(exercise_bundle, dict) else []
        exercises = exercises if isinstance(exercises, list) else []
        items = rubric.get("items") if isinstance(rubric, dict) else []
        items = items if isinstance(items, list) else []
        dimensions = []
        for item in items:
            dimension = str(item.get("dimension") or "").strip()
            if dimension and dimension not in dimensions:
                dimensions.append(dimension)
        return {
            "course_id": course.get("id"),
            "course_name": course.get("name") or course.get("course_name") or course.get("subject"),
            "evaluation_id": evaluation.get("id"),
            "evaluation_name": evaluation.get("name"),
            "evaluation_description": evaluation.get("description"),
            "review_mode": evaluation.get("review_mode"),
            "exercise_count": len(exercises),
            "total_points": sum(float(e.get("points") or 0) for e in exercises),
            "dimensions": dimensions,
            "criteria": [
                {
                    "code": item.get("code"), "dimension": item.get("dimension"),
                    "title": item.get("title"),
                    "description": re.sub(
                        r"(?i)(interfaz\s+)[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúÑñ0-9_]+",
                        r"\1[interfaz requerida]", str(item.get("description") or ""),
                    ),
                    "weight": item.get("weight_percent"),
                }
                for item in items
            ],
            "source_exercises": [
                {"title": e.get("title"), "description": e.get("description"), "points": e.get("points")}
                for e in exercises
            ],
        }

    @staticmethod
    def _too_similar(candidate: str, blueprint: dict) -> bool:
        normalized = ExamPracticeService._norm(candidate)
        # Guard específico de dominio: no reutilizar términos distintivos del caso fuente conocido.
        source = " ".join(str(e.get("title") or "") + " " + str(e.get("description") or "") for e in blueprint.get("source_exercises", []))
        source_norm = ExamPracticeService._norm(source)
        distinctive = ["bicicleta", "bicicletas", "bic e01", "bic e02", "bic m01", "bic m02", "congarantiaextendida"]
        if any(term in normalized for term in distinctive if term in source_norm):
            return True
        # Comparación global conservadora para evitar una paráfrasis casi literal.
        return SequenceMatcher(None, source_norm[:6000], normalized[:6000]).ratio() >= 0.72

    def generate(self, session: dict) -> dict:
        if not self._client:
            raise RuntimeError("OpenAI no está configurado para generar el ejercicio de práctica.")
        course = self._resolve_course(session)
        evaluation = self._latest_evaluation(int(course["id"]))
        evaluation_id = int(evaluation["id"])
        detail = self._connector.get_evaluation(evaluation_id)
        exercise_bundle = self._connector.get_evaluation_exercises(evaluation_id)
        rubric = self._connector.get_evaluation_rubric(evaluation_id)
        blueprint = self._build_blueprint(course, detail, exercise_bundle, rubric)

        instructions = """Eres el generador pedagógico de NORA. Crea UN ejercicio de práctica nuevo para preparar una evaluación de programación.
Usa exclusivamente el ASSESSMENT_BLUEPRINT como huella de competencias y dificultad.
REGLAS OBLIGATORIAS:
- No copies ni parafrasees el caso original.
- Usa un dominio de negocio completamente distinto, con entidades, nombres, datos y reglas concretas nuevas.
- Conserva las competencias técnicas, estructura y exigencia pedagógica representadas por los criterios.
- No menciones la evaluación original, su dominio, IDs ni respuestas.
- No entregues solución, código resuelto ni pauta de respuestas.
- Entrega un enunciado autosuficiente en español, apto para mostrar en una pizarra de clase.
- Mantén Java cuando los criterios evidencien explícitamente Java.
- No inventes criterios que no estén en el blueprint.
Formato: título, contexto, requerimientos, validaciones y resultado esperado. Sin Markdown complejo."""
        payload = json.dumps({k: v for k, v in blueprint.items() if k != "source_exercises"}, ensure_ascii=False)
        # Los criterios estructurados guían la generación; el caso fuente no se entrega al modelo.
        for attempt in range(2):
            response = self._client.responses.create(model=self._model, instructions=instructions, input=f"ASSESSMENT_BLUEPRINT:\n{payload}")
            text = (response.output_text or "").strip()
            if text and not self._too_similar(text, blueprint):
                return {"exercise": text, "blueprint": blueprint, "attempts": attempt + 1}
        raise RuntimeError("No pude generar una variante suficientemente distinta de la evaluación original.")
