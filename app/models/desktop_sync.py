from pydantic import BaseModel, Field

class TeacherScheduleBlock(BaseModel):
    day: int = Field(..., ge=0, le=6)
    start: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    subject: str = Field(..., min_length=1, max_length=200)
    section: str = Field(default="", max_length=80)
    enabled: bool = True

class TeacherScheduleSyncRequest(BaseModel):
    classes: list[TeacherScheduleBlock] = Field(..., max_length=100)
