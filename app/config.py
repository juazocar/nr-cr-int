import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")



class Settings:
    APP_NAME = "NORA Core API"
    APP_VERSION = "0.10.0.0"

    OPENAI_API_KEY = os.getenv(
        "OPENAI_API_KEY",
        ""
    ).strip()

    OPENAI_MODEL = os.getenv(
        "NORA_OPENAI_MODEL",
        "gpt-4o-mini"
    ).strip()

    WATCH_MAX_ANSWER_CHARS = int(
        os.getenv(
            "NORA_WATCH_MAX_ANSWER_CHARS",
            "420"
        )
    )

    WATCH_SESSION_TTL_SECONDS = int(os.getenv("NORA_WATCH_SESSION_TTL_SECONDS", "1800"))
    WATCH_MAX_SESSIONS = int(os.getenv("NORA_WATCH_MAX_SESSIONS", "100"))
    ACADEMIC_TIMEZONE = os.getenv("NORA_ACADEMIC_TIMEZONE", "America/Santiago").strip()
    SHARED_CONTEXT_TIMEZONE = os.getenv("NORA_SHARED_CONTEXT_TIMEZONE", ACADEMIC_TIMEZONE).strip()
    TEACHER_SCHEDULE_FILE = os.getenv(
        "NORA_TEACHER_SCHEDULE_FILE",
        str(BASE_DIR / "data" / "class_schedule.json")
    ).strip()
    DESKTOP_SYNC_TOKEN = os.getenv("NORA_DESKTOP_SYNC_TOKEN", "").strip()
    SHARED_CONTEXT_FILE = os.getenv(
        "NORA_SHARED_CONTEXT_FILE",
        str(BASE_DIR / "data" / "shared_context.json")
    ).strip()
    ACTIONS_FILE = os.getenv("NORA_ACTIONS_FILE", str(BASE_DIR / "data" / "actions.json")).strip()
    CLASS_SESSION_FILE = os.getenv("NORA_CLASS_SESSION_FILE", str(BASE_DIR / "data" / "class_session.json")).strip()
    STUDENT_QUIZ_FILE = os.getenv("NORA_STUDENT_QUIZ_FILE", str(BASE_DIR / "data" / "student_quizzes.json")).strip()
    AGENT_STATUS_FILE = os.getenv("NORA_AGENT_STATUS_FILE", str(BASE_DIR / "data" / "agent_status.json")).strip()
    AGENT_STATUS_TTL_SECONDS = int(os.getenv("NORA_AGENT_STATUS_TTL_SECONDS", "35"))
    LOG_FILE = os.getenv("NORA_LOG_FILE", str(BASE_DIR / "logs" / "nora_core.log")).strip()
    LOG_MAX_BYTES = int(os.getenv("NORA_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
    LOG_BACKUP_COUNT = int(os.getenv("NORA_LOG_BACKUP_COUNT", "5"))

    NOTPROFEJUAN_API_BASE_URL = os.getenv(
        "NOTPROFEJUAN_API_BASE_URL",
        "https://tech-solutions.cl/sth.backend"
    ).strip()

    WEATHER_LOCATION = os.getenv(
        "NORA_WEATHER_LOCATION",
        "Puente Alto, Chile"
    ).strip()

    DRESS_CODE_START_HOUR = int(os.getenv("NORA_DRESS_CODE_START_HOUR", "7"))
    DRESS_CODE_END_HOUR = int(os.getenv("NORA_DRESS_CODE_END_HOUR", "20"))


settings = Settings()