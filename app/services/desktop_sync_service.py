import json
import os
import tempfile
from pathlib import Path
from app.config import settings

class DesktopSyncService:
    def __init__(self) -> None:
        self._schedule_path = Path(settings.TEACHER_SCHEDULE_FILE).expanduser()

    @staticmethod
    def _minutes(value: str) -> int:
        h, m = value.split(":", 1)
        return int(h) * 60 + int(m)

    def sync_teacher_schedule(self, classes: list[dict]) -> dict:
        for index, item in enumerate(classes):
            if self._minutes(item["end"]) <= self._minutes(item["start"]):
                raise ValueError(f"Bloque {index + 1}: end debe ser posterior a start.")
        payload = {"classes": classes}
        self._schedule_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".class_schedule.", suffix=".tmp",
                                         dir=str(self._schedule_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self._schedule_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return {"success": True, "count": len(classes),
                "enabled_count": sum(1 for x in classes if x.get("enabled", True))}
