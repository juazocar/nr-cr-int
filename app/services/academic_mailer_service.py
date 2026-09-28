import httpx
import os
from app.config import settings

class AcademicMailerService:
    def __init__(self):
        self.base_url = settings.NOTPROFEJUAN_API_BASE_URL.rstrip('/')

    def _post(self, evaluation_id, action, payload):
        url=f"{self.base_url}/api/evaluations/{int(evaluation_id)}/notification/{action}"
        internal_token = os.getenv("NORA_ACADEMIC_MAILER_TOKEN", "7G8ZyseCjB1s6O800bqZ9lM5HRdItWtMqktnEiTOTYTE22pFLi28A3YJkTD7zKKJ").strip()
        if not internal_token:
            raise RuntimeError("Academic Mailer interno no configurado en NORA Core.")
        headers = {
            "Accept": "application/json",
            "User-Agent": "NORA-Core/AcademicMailer",
            "X-NORA-Academic-Mailer-Token": internal_token,
        }
        try:
            response=httpx.post(url,json=payload,headers=headers,timeout=60.0,follow_redirects=True)
            response.raise_for_status()
            data=response.json()
            if not isinstance(data,dict): raise RuntimeError("#NotProfeJuan entregó una respuesta inesperada.")
            return data
        except (httpx.HTTPError,ValueError) as exc:
            raise RuntimeError("No pude procesar el correo académico en #NotProfeJuan.") from exc

    def preview(self,evaluation_id,payload): return self._post(evaluation_id,'preview',payload)
    def send(self,evaluation_id,payload): return self._post(evaluation_id,'send',payload)
