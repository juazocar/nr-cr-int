"""Enrutador determinístico de comandos cortos de NORA Watch."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class WatchCommand:
    intent: str
    args: dict

class WatchCommandRouter:
    LANGUAGES = {
        "java":"Java","python":"Python","kotlin":"Kotlin","javascript":"JavaScript",
        "typescript":"TypeScript","csharp":"C#","c#":"C#","php":"PHP","sql":"SQL",
    }

    @staticmethod
    def _norm(value: str) -> str:
        text=unicodedata.normalize("NFKD",str(value or "").lower())
        text="".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"\s+"," ",text).strip(" .,;:!?¿¡")

    def route(self, text: str) -> WatchCommand | None:
        q=self._norm(text)
        if not q: return None
        words=q.split()

        if q in {"ejercicio tipo prueba", "tipo prueba", "practica tipo prueba"}:
            return WatchCommand("EXAM_PRACTICE", {})

        evaluation_commands = {
            "evaluacion ver": "EVALUATION_VIEW",
            "evaluacion practica": "EXAM_PRACTICE",
            "evaluacion rubrica": "EVALUATION_RUBRIC",
            "evaluacion repaso": "EVALUATION_REVIEW",
            "evaluacion estado": "EVALUATION_STATUS",
        }
        if q in evaluation_commands:
            return WatchCommand(evaluation_commands[q], {})

        quiz_controls = {
            "quiz iniciar": "LIVE_QUIZ_START",
            "quiz siguiente": "LIVE_QUIZ_NEXT",
            "quiz estado": "LIVE_QUIZ_STATUS",
            "quiz resultados": "LIVE_QUIZ_RESULTS",
            "quiz finalizar": "LIVE_QUIZ_CLOSE",
        }
        if q in quiz_controls:
            return WatchCommand(quiz_controls[q], {})

        # Quiz <tópico> [lenguaje]. Comando corto pensado para voz en Watch.
        # El lenguaje sólo se interpreta como sufijo para permitir tópicos libres
        # de varias palabras: "quiz try catch java", "quizz herencia kotlin".
        if words[0] in {"quiz", "quizz"}:
            rest=" ".join(words[1:]).strip()
            language=""
            for token,label in sorted(self.LANGUAGES.items(), key=lambda item: len(item[0]), reverse=True):
                match=re.search(rf"(?:^|\s){re.escape(token)}$",rest)
                if match:
                    language=label
                    rest=rest[:match.start()].strip()
                    break
            if rest:
                return WatchCommand("CREATE_LIVE_QUIZ", {"topic":rest, "language":language})
            return WatchCommand("QUIZ_INCOMPLETE", {})

        # Pizarra <tema> [lenguaje]. Tolera "ejemplo de" y "array list".
        if words[0] in {"pizarra","pizarron","pizara","pisarra","pisara","pissarra","izarra","izarron"}:
            rest=" ".join(words[1:]).strip()
            rest=re.sub(r"^(?:con )?(?:un )?ejemplo(?: de)?\s+","",rest)
            language=""
            # El lenguaje se interpreta sólo como sufijo. Así el tema queda
            # completamente libre: "try catch", "Spring Boot", "RecyclerView", etc.
            for token,label in sorted(self.LANGUAGES.items(), key=lambda item: len(item[0]), reverse=True):
                match=re.search(rf"(?:^|\s){re.escape(token)}$",rest)
                if match:
                    language=label
                    rest=rest[:match.start()].strip()
                    break
            rest=re.sub(r"\barray\s+list\b","ArrayList",rest,flags=re.I)
            # Visual Teaching Board v0.1: "Pizarra ER cliente pedido ..."
            # se enruta antes que la pizarra de código y conserva entidades libres.
            er_match = re.match(r"^(?:er|entidad relacion|entidad-relacion)\s+(.+)$", rest, flags=re.I)
            if er_match:
                expression = er_match.group(1).strip()
                if expression:
                    # Conserva la expresión completa. Core v0.8.6 la interpreta
                    # como entidades + relación, sin convertir verbos en entidades.
                    return WatchCommand("OPEN_ER_DIAGRAM", {"expression": expression, "mode": "replace"})
            if rest:
                return WatchCommand("OPEN_WHITEBOARD",{"topic":rest.strip(),"language":language,"mode":"replace"})
            return WatchCommand("WHITEBOARD_INCOMPLETE",{})

        classroom_interventions = {
            "consejo de clase": "ADVICE",
            "animo de clase": "ENCOURAGEMENT",
            "reflexion de clase": "REFLECTION",
            "nora interviene": "FREE",
        }
        if q in classroom_interventions:
            return WatchCommand("CLASSROOM_INTERVENTION", {"mode": classroom_interventions[q]})

        # Consultas determinísticas sobre el modelo ER activo.
        if q in {"cual es la entidad debil","que entidad es debil","entidad debil"}:
            return WatchCommand("ER_QUERY_WEAK",{})
        if q in {"cual es la entidad fuerte","que entidad es fuerte","entidad fuerte"}:
            return WatchCommand("ER_QUERY_STRONG",{})
        if q in {"quien lleva la fk","donde esta la fk","cual lleva la fk","cual es la fk"}:
            return WatchCommand("ER_QUERY_FK",{})
        if q in {"cual es la clave parcial","muestra la clave parcial","muestrame la clave parcial","clave parcial"}:
            return WatchCommand("ER_QUERY_PARTIAL_KEY",{})
        if q in {"explica la cardinalidad","cual es la cardinalidad","cardinalidad"}:
            return WatchCommand("ER_QUERY_CARDINALITY",{})
        if q in {"resalta la relacion identificadora","cual es la relacion identificadora","relacion identificadora"}:
            return WatchCommand("ER_QUERY_IDENTIFYING",{})
        if q in {"por que","porque","por que es asi","explicame por que"}:
            return WatchCommand("ER_QUERY_WHY",{})

        if q in {"iniciar clase","inicia clase","comenzar clase","comienza clase","modo clase"}:
            return WatchCommand("START_CLASS_MODE",{})
        if q in {"finalizar clase","finaliza clase","terminar clase","termina clase","cerrar clase","salir modo clase"}:
            return WatchCommand("END_CLASS_MODE",{})
        if q in {"que clase estoy haciendo","cual es mi clase actual","clase actual","estado clase"}:
            return WatchCommand("CLASS_MODE_STATUS",{})
        if q in {"cuanto queda de clase","cuanto falta para terminar la clase","cuanto falta de clase","tiempo restante de clase"}:
            return WatchCommand("CLASS_TIME_REMAINING",{})

        if q in {"clases hoy","clase hoy","mis clases hoy"}:
            return WatchCommand("CLASSES_TODAY",{})
        if q in {"clases manana","clase manana","mis clases manana"}:
            return WatchCommand("CLASSES_TOMORROW",{})
        if q in {"pendientes","mis pendientes","ver pendientes"}:
            return WatchCommand("PENDING",{})
        if q in {"resumen academico","resumen cursos","mis cursos"}:
            return WatchCommand("ACADEMIC_SUMMARY",{})
        return None
