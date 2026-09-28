from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CurriculumProgress(str, Enum):
    FUTURE = "FUTURE"
    TAUGHT = "TAUGHT"


class TheoryActivityType(str, Enum):
    CASE = "CASO"
    CHALLENGE = "DESAFÍO"
    REVIEW = "REPASO"
    ANALYZE = "ANALIZAR"


class TheoryDifficulty(str, Enum):
    BASIC = "BASIC"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class MarkTopicTaughtRequest(BaseModel):
    topic_code: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class TheoryContextRequest(BaseModel):
    course_id: int = Field(gt=0)


class TheoryActivityCreate(BaseModel):
    course_id: int = Field(gt=0)
    topic_codes: list[str] = Field(min_length=1, max_length=12)
    concepts: list[str] = Field(min_length=1, max_length=40)
    activity_type: TheoryActivityType
    difficulty: TheoryDifficulty = TheoryDifficulty.INTERMEDIATE
    title: str = Field(min_length=1, max_length=180)
    prompt: str = Field(min_length=3, max_length=6000)
    response_type: Literal["MULTIPLE_CHOICE", "SHORT_TEXT", "OPEN_TEXT", "CLASSIFICATION"]
    sources: list[dict] | None = None

    @model_validator(mode="after")
    def normalize_unique_values(self):
        self.topic_codes = list(dict.fromkeys(code.strip() for code in self.topic_codes))
        self.concepts = list(dict.fromkeys(value.strip() for value in self.concepts if value.strip()))
        if not self.concepts:
            raise ValueError("Debe existir al menos un concepto.")
        return self
