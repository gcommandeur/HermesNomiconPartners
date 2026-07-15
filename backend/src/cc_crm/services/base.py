import uuid
from collections.abc import Sequence

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

    def get(self, entity_id: uuid.UUID) -> ModelT:
        entity = self.repository.get(entity_id)
        if entity is None:
            raise EntityNotFoundError(f"{self.entity_name} not found")
        return entity

    def list(self, *, offset: int = 0, limit: int = 100) -> Sequence[ModelT]:
        return self.repository.list(offset=offset, limit=limit)

    def create(self, payload: CreateT) -> ModelT:
        try:
            entity = self.repository.create(payload.model_dump(exclude_none=True))
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
