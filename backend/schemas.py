from typing import Literal

from pydantic import BaseModel, Field


class CriterionEval(BaseModel):
    criterion_id: str = Field(description="ID criterion from the supplied rubric")
    passed: bool = Field(description="Whether the student's work satisfies this criterion")
    points_awarded: float = Field(ge=0, description="Points awarded for this criterion")
    comment: str = Field(description="Short explanation in Russian")
    status: Literal["awarded", "not_awarded", "uncertain"] = "uncertain"
    evidence: list[str] = Field(default_factory=list, description="Evidence observed in the student's work")


class GradingResult(BaseModel):
    transcribed_latex: str = Field(
        description="Faithful transcription of the handwritten solution using LaTeX for formulas"
    )
    criteria_results: list[CriterionEval]
    total_score: float = Field(ge=0)
    overall_feedback: str = Field(description="Overall feedback for the student in Russian")
    uncertainty: float = Field(default=0, ge=0, le=1)
    requires_human_attention: bool = False
    attention_reasons: list[str] = Field(default_factory=list)
    transcription_notes: list[str] = Field(default_factory=list)
