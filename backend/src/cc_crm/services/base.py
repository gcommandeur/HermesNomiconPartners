import uuid
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cc_crm.core.errors import ConflictError, EntityNotFoundError
from cc_crm.models.base import Base
from cc_crm.repositories.base import SQLAlchemyRepository


class CrudService[ModelT: Base, CreateT: BaseModel, UpdateT: BaseModel]:
    def __init__(
        self,
        session: Session,
        repository: SQLAlchemyRepository[ModelT],
        entity_name: str,
    ) -> None:
        self.session = session
        self.repository = repository
        self.entity_name = entity_name

    # "candidate" | "client" | "contact": aktiviert die Pruefung von `custom_fields`
    # (services/custom_fields.py). None = Objekt hat keine eigenen Felder.
    custom_field_entity: str | None = None

    def _checked_custom_fields(
        self, values: dict[str, Any], existing: dict[str, Any] | None
    ) -> None:
        if self.custom_field_entity is None or values.get("custom_fields") is None:
            return
        from cc_crm.services.custom_fields import CustomFieldService

        values["custom_fields"] = CustomFieldService(self.session).validate_values(
            self.custom_field_entity, values["custom_fields"], existing
        )

    def get(self, entity_id: uuid.UUID) -> ModelT:
        entity = self.repository.get(entity_id)
        if entity is None:
            raise EntityNotFoundError(f"{self.entity_name} not found")
        return entity

    def list(self, *, offset: int = 0, limit: int = 100) -> Sequence[ModelT]:
        return self.repository.list(offset=offset, limit=limit)

    def create(self, payload: CreateT) -> ModelT:
        try:
            values = payload.model_dump(exclude_none=True)
            self._checked_custom_fields(values, None)
            entity = self.repository.create(values)
            self.session.commit()
            return entity
        except IntegrityError as exception:
            self.session.rollback()
            raise ConflictError(f"{self.entity_name} conflicts with existing data") from exception
        except Exception:
            self.session.rollback()
            raise

    def update(self, entity_id: uuid.UUID, payload: UpdateT) -> ModelT:
        entity = self.get(entity_id)
        values = payload.model_dump(exclude_unset=True)
        self._checked_custom_fields(values, getattr(entity, "custom_fields", None))
        try:
            updated = self.repository.update(entity, values)
            self.session.commit()
            return updated
        except IntegrityError as exception:
            self.session.rollback()
            raise ConflictError(f"{self.entity_name} conflicts with existing data") from exception
        except Exception:
            self.session.rollback()
            raise

    def delete(self, entity_id: uuid.UUID) -> None:
        entity = self.get(entity_id)
        try:
            self.repository.delete(entity)
            self.session.commit()
        except IntegrityError as exception:
            self.session.rollback()
            raise ConflictError(f"{self.entity_name} is still referenced") from exception
        except Exception:
            self.session.rollback()
            raise
