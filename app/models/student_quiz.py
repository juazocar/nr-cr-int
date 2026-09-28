from pydantic import BaseModel, Field

class QuizQuestionCreate(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_index: int = Field(ge=0)

class QuizSessionCreate(BaseModel):
    title: str = Field(default="Quiz NORA", min_length=1, max_length=160)
    course_id: int = Field(gt=0)
    questions: list[QuizQuestionCreate] = Field(min_length=1, max_length=30)

class StudentJoinRequest(BaseModel):
    email: str = Field(min_length=3, max_length=180)
    code: str = Field(pattern=r"^\d{6}$")

class StudentAnswerRequest(BaseModel):
    session_token: str = Field(min_length=20, max_length=200)
    question_id: str = Field(min_length=1, max_length=80)
    option_index: int = Field(ge=0, le=5)
