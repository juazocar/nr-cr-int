import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import settings


class TeacherScheduleService:
    DAY_ALIASES = {
        0: {"lunes", "monday"}, 1: {"martes", "tuesday"},
        2: {"miercoles", "miércoles", "wednesday"}, 3: {"jueves", "thursday"},
        4: {"viernes", "friday"}, 5: {"sabado", "sábado", "saturday"},
        6: {"domingo", "sunday"},
    }

    def __init__(self) -> None:
        self._path = Path(settings.TEACHER_SCHEDULE_FILE).expanduser()

    def _load(self) -> list[dict]:
        if not self._path.is_file():
            return []
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("classes", "schedule", "items"):
                if isinstance(data.get(key), list):
                    return [x for x in data[key] if isinstance(x, dict)]
        raise ValueError("Formato de horario docente no soportado.")

    @staticmethod
    def _value(item: dict, *keys: str):
        for key in keys:
            if item.get(key) not in (None, ""):
                return item[key]
        return None

    def _matches_date(self, item: dict, target: datetime) -> bool:
        date_value = self._value(item, "date", "class_date", "fecha")
        if date_value:
            return str(date_value)[:10] == target.date().isoformat()
        day_value = self._value(item, "day", "weekday", "dia", "día")
        if day_value is None:
            return False
        if isinstance(day_value, int) and not isinstance(day_value, bool):
            return day_value == target.weekday()
        text_day = str(day_value).strip()
        if text_day.isdigit():
            return int(text_day) == target.weekday()
        return text_day.casefold() in self.DAY_ALIASES[target.weekday()]

    def _normalize_item(self, item: dict) -> dict:
        return {
            "course": self._value(item, "course", "subject", "name", "asignatura", "ramo"),
            "section": self._value(item, "section", "seccion", "sección"),
            "start_time": self._value(item, "start_time", "start", "hora_inicio", "inicio"),
            "end_time": self._value(item, "end_time", "end", "hora_fin", "fin"),
            "room": self._value(item, "room", "classroom", "sala"),
            "campus": self._value(item, "campus", "sede"),
        }

    @staticmethod
    def _enabled(item: dict) -> bool:
        value = item.get("enabled", True)
        if isinstance(value, str):
            return value.strip().casefold() not in {"false", "0", "no", "off"}
        return bool(value)

    @staticmethod
    def _minutes(value) -> int | None:
        try:
            hours, minutes = str(value).strip().split(":", 1)
            return int(hours) * 60 + int(minutes)
        except (TypeError, ValueError):
            return None

    def _time_context(self, items: list[dict], target: datetime) -> dict:
        now_minutes = target.hour * 60 + target.minute
        current = None
        upcoming = None
        for item in items:
            start = self._minutes(item.get("start_time"))
            end = self._minutes(item.get("end_time"))
            if start is None or end is None:
                continue
            if start <= now_minutes < end:
                current = item
                break
            if start > now_minutes and upcoming is None:
                upcoming = item
        if current is not None:
            current_end = self._minutes(current.get("end_time"))
            return {
                "current_class": current,
                "next_class": next(
                    (x for x in items if (self._minutes(x.get("start_time")) or -1) >= (current_end or 10**9)),
                    None,
                ),
                "minutes_until_next": 0,
            }
        next_minutes = self._minutes(upcoming.get("start_time")) if upcoming else None
        return {
            "current_class": None,
            "next_class": upcoming,
            "minutes_until_next": (next_minutes - now_minutes) if next_minutes is not None else None,
        }

    def for_date(self, target: datetime) -> dict:
        if not self._path.is_file():
            return {"available": False, "source": str(self._path), "classes_today": None,
                    "count": None, "items": [],
                    "note": "La fuente del horario docente aún no existe en NORA Core."}
        try:
            raw = self._load()
        except (OSError, ValueError, json.JSONDecodeError):
            return {"available": False, "source": str(self._path), "classes_today": None,
                    "count": None, "items": [],
                    "note": "La fuente del horario docente existe, pero no pudo interpretarse."}
        items = [
            self._normalize_item(x)
            for x in raw
            if self._enabled(x) and self._matches_date(x, target)
        ]
        items.sort(key=lambda x: str(x.get("start_time") or ""))
        result = {
            "available": True,
            "source": str(self._path),
            "classes_today": bool(items),
            "count": len(items),
            "items": items,
            "date": target.date().isoformat(),
            "first_class": items[0] if items else None,
            "last_class": items[-1] if items else None,
        }
        # Only "today" should be interpreted relative to the current clock.
        now = datetime.now(ZoneInfo(settings.ACADEMIC_TIMEZONE))
        if target.date() == now.date():
            result.update(self._time_context(items, now))
        return result

    def today(self) -> dict:
        return self.for_date(datetime.now(ZoneInfo(settings.ACADEMIC_TIMEZONE)))

    def tomorrow(self) -> dict:
        now = datetime.now(ZoneInfo(settings.ACADEMIC_TIMEZONE))
        return self.for_date(now + timedelta(days=1))
