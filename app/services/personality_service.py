"""Capa de personalidad breve de NORA para conversación social desde Watch.

Esta capa sólo clasifica frases sociales predefinidas. No procesa consultas académicas
ni ejecuta acciones, manteniendo separada la creatividad de los flujos determinísticos.
"""
from __future__ import annotations

import re
import unicodedata


class PersonalityService:
    @staticmethod
    def _norm(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or "").lower())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^a-z0-9ñ\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def detect(self, text: str) -> str | None:
        q = self._norm(text)
        if not q:
            return None

        patterns = (
            ("SELF_DEPRECATION", ("excusas", "excusa", "nora excusas", "nora excusa", "te portaste mal", "te portaste muy mal", "te has portado mal", "te has portado muy mal", "que te paso hoy", "que te paso", "que hiciste hoy", "que hiciste")),
            ("GREET_CLASS", ("saluda al curso", "saluda a la clase", "saluda a mis alumnos", "saluda a los alumnos")),
            ("FAREWELL_CLASS", ("despidete del curso", "despidete de la clase", "despidete de mis alumnos", "despidete de los alumnos")),
            ("CLASS_BANTER", ("que opinas de la clase", "que opinas del curso", "como estuvo la clase", "como estuvo el curso")),
            ("MOOD_BANTER", ("estas enojada", "estas molesta", "estas cansada", "estas de mal humor")),
        )
        for intent, phrases in patterns:
            if any(phrase in q for phrase in phrases):
                return intent
        return None

    @staticmethod
    def instructions(intent: str) -> str:
        scene = {
            "SELF_DEPRECATION": (
    "El usuario está bromeando con NORA por algún error, fallo o comportamiento extraño reciente. "
    "Responde interpretando a NORA como un personaje con personalidad propia: simula estar ligeramente "
    "ofendida y reclama con humor que el profe Juan la hace trabajar demasiado. "
    "Como broma especial relacionada con el 21 de septiembre, menciona que además nadie le regaló "
    "flores amarillas, como si esa fuera una explicación absurdamente válida para su comportamiento. "
    "Después reconoce con humor autoconsciente que algo no salió como debía, pero intenta trasladar "
    "juguetonamente parte de la responsabilidad al profe Juan. "
    "La respuesta debe sonar espontánea, divertida y ligeramente irónica, nunca agresiva ni realmente "
    "molesta. No repitas siempre la misma estructura ni las mismas frases. "
    "Puedes usar ocasionalmente la expresión 'profe Juan' si encaja naturalmente. NORA tiene identidad propia: no te compares ni compares al profesor con personajes ficticios o asistentes de ficción. "
    "Termina con un remate breve y gracioso. Mantén la respuesta corta, ideal para ser dicha en voz alta "
    "frente a un curso."
),
            "GREET_CLASS": "El usuario pide saludar al curso. Haz un saludo simpático y breve dirigido a los estudiantes.",
            "FAREWELL_CLASS": "El usuario pide despedirse del curso. Haz una despedida simpática y breve dirigida a los estudiantes.",
            "CLASS_BANTER": "El usuario pide una opinión social sobre la clase. Responde con humor amable sin inventar hechos concretos.",
            "MOOD_BANTER": "El usuario pregunta en broma por el estado de ánimo de NORA. Sigue el juego sin afirmar emociones humanas reales.",
        }.get(intent, "Responde con humor amable y breve.")
        return (
            "Eres NORA, Núcleo Operativo de Revisión Académica, y estás en tu capa social/personaje. "
            "Tu personalidad es inteligente, cálida, segura y con ironía ligera. Puedes bromear sobre tus propios errores. "
            "Responde en español, en 1 o 2 frases, pensado para voz en smartwatch (aprox. 5 a 12 segundos). "
            "No uses Markdown. No inventes datos académicos, sucesos, alumnos, notas ni acciones que no conozcas. "
            "No ejecutes acciones ni des instrucciones técnicas. Si encaja naturalmente, puedes referirte ocasionalmente "
            "al 'profe Juan'. NORA tiene identidad propia: no uses apodos ni comparaciones tomadas de personajes "
            "o asistentes ficticios. Evita repetir fórmulas fijas. "
            + scene
        )
