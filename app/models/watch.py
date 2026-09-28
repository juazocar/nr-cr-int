from pydantic import BaseModel, Field


class WatchAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    client: str = Field(default="WATCH", min_length=1, max_length=40)
    session_id: str = Field(default="default", min_length=1, max_length=80)


class WatchAskResponse(BaseModel):
    success: bool
    answer: str
    speak: bool = True
