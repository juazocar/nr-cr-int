from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings


class TodayService:
    """Builds deterministic non-AI context for NORA Today."""

    def build_context(self, academic_today: dict, dress_code: dict, teacher_schedule: dict) -> dict:
        now = datetime.now(ZoneInfo(settings.ACADEMIC_TIMEZONE))
        return {
            "date": now.date().isoformat(),
            "local_time": now.strftime("%H:%M"),
            "timezone": settings.ACADEMIC_TIMEZONE,
            "academic": academic_today,
            "dress_code": dress_code,
            "teacher_schedule": teacher_schedule,
        }
