import httpx

from app.config import settings


class NotProfeJuanConnector:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.NOTPROFEJUAN_API_BASE_URL).rstrip("/")

    def get_courses(self) -> list[dict]:
        return self._get_list("/api/courses")

    def get_students(self, course_id: int) -> list[dict]:
        return self._get_list(f"/api/courses/{course_id}/students")

    def get_evaluations(self, course_id: int) -> list[dict]:
        return self._get_list(f"/api/evaluations/course/{course_id}")

    def get_evaluation(self, evaluation_id: int) -> dict:
        return self._get_dict(f"/api/evaluations/{evaluation_id}")

    def get_evaluation_exercises(self, evaluation_id: int) -> dict:
        return self._get_dict(f"/api/evaluation-exercises/evaluation/{evaluation_id}")

    def get_evaluation_rubric(self, evaluation_id: int) -> dict:
        return self._get_dict(f"/api/rubrics/evaluation/{evaluation_id}")

    def get_schedule(self, course_id: int) -> list[dict]:
        return self._get_list(f"/api/schedules/course/{course_id}")

    def get_schedules(self) -> list[dict]:
        return self._get_list("/api/schedules")

    def get_reservations(self, evaluation_id: int) -> list[dict]:
        return self._get_list(f"/api/bookings/evaluation/{evaluation_id}")

    def _get_dict(self, path: str) -> dict:
        data = self._get_json(path)
        if not isinstance(data, dict):
            raise RuntimeError("#NotProfeJuan entregó una respuesta inesperada.")
        return data

    def _get_list(self, path: str) -> list[dict]:
        data = self._get_json(path)
        if not isinstance(data, list):
            raise RuntimeError("#NotProfeJuan entregó una respuesta inesperada.")
        return data

    def _get_json(self, path: str):
        url = f"{self.base_url}{path}"
        try:
            response = httpx.get(
                url,
                headers={"Accept": "application/json", "User-Agent": "NORA-Core/0.7.1"},
                timeout=10.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("No pude consultar #NotProfeJuan.") from exc
