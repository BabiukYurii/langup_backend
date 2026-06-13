# SQLAlchemy 2.0 declarative base + reusable mixins.
from uuid import uuid4

from sqlalchemy import Column, DateTime, func, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class UUIDMixin:
    # UUID primary key (server-side gen_random_uuid()).
    uuid = Column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
        index=True,
    )


class TimestampMixin:
    # created_at / updated_at audit timestamps.
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now())
