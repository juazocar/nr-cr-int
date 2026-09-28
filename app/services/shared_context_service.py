from __future__ import annotations
from datetime import datetime, timezone as dt_timezone
import json, os, tempfile, threading, uuid
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.config import settings


class SharedContextService:
    def __init__(self) -> None:
        self.path = Path(settings.SHARED_CONTEXT_FILE).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw.get("items", []) if isinstance(raw, dict) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save(self, items: list[dict]) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=".shared_context.", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"version": 2, "items": items}, handle, ensure_ascii=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)

    @staticmethod
    def _normalize_remind_at(remind_at: datetime | str | None) -> str | None:
        if remind_at is None or remind_at == "":
            return None
        value = remind_at if isinstance(remind_at, datetime) else datetime.fromisoformat(str(remind_at))
        if value.tzinfo is None:
            raise ValueError("remind_at must include timezone information")
        return value.astimezone(dt_timezone.utc).isoformat()

    @staticmethod
    def _timezone_name(name: str | None) -> str:
        candidate = (name or settings.SHARED_CONTEXT_TIMEZONE).strip()
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Invalid reminder timezone") from exc
        return candidate

    def create(self, source: str, target: str, kind: str, content: str,
               remind_at: datetime | str | None = None, timezone: str | None = None) -> dict:
        now = datetime.now(dt_timezone.utc).isoformat()
        # timezone is descriptive/localization metadata; remind_at is persisted canonically in UTC.
        tz_name = self._timezone_name(timezone) if remind_at is not None else None
        item = {
            "id": str(uuid.uuid4()), "source": source, "target": target,
            "kind": kind.strip().upper(), "content": content.strip(),
            "status": "PENDING", "created_at": now,
            "remind_at": self._normalize_remind_at(remind_at),
            "timezone": tz_name,
            "completed_at": None, "completed_by": None,
        }
        with self._lock:
            items = self._load(); items.append(item); self._save(items)
        return item

    def pending(self, target: str) -> list[dict]:
        with self._lock:
            items = self._load()
        return [x for x in items if x.get("target") == target and x.get("status") == "PENDING"]

    def due(self, target: str, now: datetime | None = None) -> list[dict]:
        reference = (now or datetime.now(dt_timezone.utc)).astimezone(dt_timezone.utc)
        result = []
        for item in self.pending(target):
            raw = item.get("remind_at")
            if not raw:
                continue
            try:
                when = datetime.fromisoformat(raw)
                if when.tzinfo is not None and when.astimezone(dt_timezone.utc) <= reference:
                    result.append(item)
            except (TypeError, ValueError):
                continue
        return result

    def complete(self, item_id: str, completed_by: str) -> dict | None:
        with self._lock:
            items = self._load()
            for item in items:
                if item.get("id") == item_id:
                    if item.get("status") == "PENDING":
                        item["status"] = "COMPLETED"
                        item["completed_at"] = datetime.now(dt_timezone.utc).isoformat()
                        item["completed_by"] = completed_by
                        self._save(items)
                    return item
        return None
