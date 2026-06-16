from typing import Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic async data-access layer over a SQLAlchemy model."""

    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        self.session = session
        self.model = model

    async def create_one(self, data: dict) -> ModelType:
        row = self.model(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_one(self, **filters) -> ModelType | None:
        result = await self.session.execute(select(self.model).filter_by(**filters))
        return result.scalar_one_or_none()

    async def get_many(
        self,
        page: int = 1,
        limit: int = 20,
        order_by: list | None = None,
        **filters,
    ) -> tuple[list[ModelType], int]:
        offset = (page - 1) * limit
        query = select(self.model).filter_by(**filters).offset(offset).limit(limit)
        if order_by:
            query = query.order_by(*order_by)
        total_query = select(func.count()).select_from(self.model).filter_by(**filters)

        rows = (await self.session.execute(query)).scalars().all()
        total = (await self.session.execute(total_query)).scalar() or 0
        return list(rows), total

    async def update_one(self, obj: ModelType, data: dict) -> ModelType:
        for key, value in data.items():
            setattr(obj, key, value)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete_one(self, obj: ModelType) -> None:
        await self.session.delete(obj)
        await self.session.commit()

    async def delete_by(self, **filters) -> None:
        await self.session.execute(delete(self.model).filter_by(**filters))
        await self.session.commit()
