import re
import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

# Erlaubte Platzhalter in Betreff/Text (einfache {wort}-Tokens wie bei den
# E-Mail-Vorlagen, siehe services/operational.py::PLACEHOLDER_RE). Unbekannte
# Platzhalter werden beim Speichern abgelehnt, damit nie ein rohes "{foo}"
# in einer versendeten Mail landet.
ALLOWED_PLACEHOLDERS = frozenset({"first_name", "last_name", "full_name", "sender_name"})
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

Channel = Literal["email", "linkedin", "phone", "other"]
EnrollmentStatus = Literal["active", "paused_reply", "completed", "stopped"]


class SequenceStepInput(BaseModel):
    day_offset: int = Field(ge=0, le=365)
    channel: Channel
    subject: str = Field(min_length=1, max_length=240)
    body_template: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.channel == "email" and not (self.body_template or "").strip():
            raise ValueError("E-Mail-Schritte brauchen einen Text.")
        for text in (self.subject, self.body_template or ""):
            unknown = set(_PLACEHOLDER_RE.findall(text)) - ALLOWED_PLACEHOLDERS
            if unknown:
                raise ValueError(
                    f"Unbekannte Platzhalter: {', '.join(sorted(unknown))} "
                    f"(erlaubt: {', '.join(sorted(ALLOWED_PLACEHOLDERS))})"
                )
        return self


def _validate_steps(steps: list[SequenceStepInput]) -> list[SequenceStepInput]:
    if not steps:
        raise ValueError("Eine Sequenz braucht mindestens einen Schritt.")
    offsets = [step.day_offset for step in steps]
    if offsets != sorted(offsets):
        raise ValueError("Die Schritte muessen nach Tagesabstand aufsteigend geordnet sein.")
    return steps


class SequenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    is_active: bool = True
    steps: list[SequenceStepInput]

    _steps = field_validator("steps")(_validate_steps)


class SequenceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_active: bool | None = None
    # Ersetzt die komplette Schrittliste (laufende Einschreibungen behalten
    # ihren Schrittindex).
    steps: list[SequenceStepInput] | None = None

    @field_validator("steps")
    @classmethod
    def _steps(cls, value: list[SequenceStepInput] | None) -> list[SequenceStepInput] | None:
        return None if value is None else _validate_steps(value)


class SequenceStepRead(BaseModel):
    step_index: int
    day_offset: int
    channel: str
    subject: str
    body_template: str | None


class SequenceRead(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    steps: list[SequenceStepRead]
    created_at: datetime


class EnrollmentCreate(BaseModel):
    sequence_id: uuid.UUID
    candidate_id: uuid.UUID


class EnrollmentRead(BaseModel):
    id: uuid.UUID
    sequence_id: uuid.UUID
    sequence_name: str
    candidate_id: uuid.UUID
    owner_user_id: uuid.UUID | None
    status: str
    stopped_reason: str | None
    started_at: datetime
    current_step_index: int
    total_steps: int
    # Naechster Schritt (None bei beendeten Einschreibungen) und das Datum,
    # ab dem er faellig ist (Europe/Berlin-Kalendertag).
    next_step_channel: str | None
    next_step_subject: str | None
    next_step_due_on: date | None


class EnrollmentStop(BaseModel):
    reason: str | None = Field(default=None, max_length=200)
