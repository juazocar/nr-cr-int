"""Resolución determinística de tecnología por contexto de Modo Clase."""
from __future__ import annotations
import re
import unicodedata


class CourseTechnologyService:
    """Completa el lenguaje sólo cuando el usuario no lo indicó explícitamente."""

    COURSE_DEFAULTS = {
        "desarrollo de aplicaciones moviles": "Kotlin",
        "aplicaciones moviles": "Kotlin",
        "desarrollo orientado a objetos": "Java",
        "programacion orientada a objetos": "Java",
    }

    @staticmethod
    def _norm(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or "").casefold())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", text).strip()

    def resolve(self, explicit_language: str, active_session: dict | None) -> tuple[str, str]:
        explicit = str(explicit_language or "").strip()
        if explicit:
            return explicit, "EXPLICIT"
        if not active_session:
            return "", "NONE"

        course = self._norm(active_session.get("course"))
        if not course:
            return "", "NONE"

        exact = self.COURSE_DEFAULTS.get(course)
        if exact:
            return exact, "CLASS_CONTEXT"

        # Permite que el horario incluya prefijos/sufijos sin volver ambigua la regla.
        for name, language in self.COURSE_DEFAULTS.items():
            if name in course:
                return language, "CLASS_CONTEXT"
        return "", "NONE"
