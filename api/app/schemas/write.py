from pydantic import BaseModel, Field, model_validator

from app.domain.enums import InputMode
from app.schemas.extraction import ExtractedApplication


class SubmissionCreate(BaseModel):
    input_mode: InputMode
    raw_input: str | None = Field(default=None, min_length=1)
    application: ExtractedApplication | None = None

    @model_validator(mode="after")
    def check_the_mode_carries_its_payload(self) -> "SubmissionCreate":
        if self.input_mode is InputMode.FORM:
            if self.application is None:
                raise ValueError("form submissions must carry an application")
        elif self.raw_input is None:
            raise ValueError(f"{self.input_mode.value} submissions must carry raw_input")
        return self


class DeclineRequest(BaseModel):
    reason: str = Field(min_length=1)
