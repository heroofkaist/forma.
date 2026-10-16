from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class EvidenceAnchor(Strict):
    page_number: int = Field(ge=1, le=50, strict=True)
    observation: str = Field(min_length=1, max_length=2000)

class CardUse(Strict):
    card_id: str = Field(min_length=1, max_length=36)
    evidence: EvidenceAnchor
