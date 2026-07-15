import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from cc_crm.models.enums import JobStatus, TaskPriority
from cc_crm.schemas.base import EntityRead


class JobMandateBase(BaseModel):
    client_company_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    status: JobStatus = JobStatus.DRAFT
    priority: TaskPriority = TaskPriority.NORMAL
    location: str | None = Field(default=None, max_length=240)
    search_radius_km: int = Field(default=30, ge=0, le=500)
    work_model: str | None = Field(default=None, max_length=120)
    qualifications: str | None = None
    experience: str | None = None
    description: str | None = None
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    fee_percentage: Decimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_salary_range(self) -> "JobMandateBase":
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min must not exceed salary_max")
        return self


class JobMandateCreate(JobMandateBase):
    pass


class JobMandateUpdate(BaseModel):
    client_company_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=240)
    status: JobStatus | None = None
    priority: TaskPriority | None = None
    location: str | None = Field(default=None, max_length=240)
    search_radius_km: int | None = Field(default=None, ge=0, le=500)
    work_model: str | None = Field(default=None, max_length=120)
    qualifications: str | None = None
    experience: str | None = None
    description: str | None = None
    must_have: list[str] | None = None
    nice_to_have: list[str] | None = None
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    fee_percentage: Decimal | None = Field(default=None, ge=0, le=100)


class JobMandateRead(JobMandateBase, EntityRead):
    pass
