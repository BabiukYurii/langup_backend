# SQLAlchemy 2.0 declarative base + reusable mixins.
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# UUID PostgreSQL-native type, with a portable variant so the test suite can
# run the same models on sqlite. The Postgres server-side gen_random_uuid()
# default is applied in migrations; the ORM always sets it client-side too.
UUIDType = PGUUID(as_uuid=True).with_variant(Uuid(), "sqlite")

# JSONB on Postgres, generic JSON on sqlite (so the test suite can run on sqlite).
JSONType = JSONB().with_variant(JSON(), "sqlite")


class UUIDMixin:
    uuid = Column(UUIDType, primary_key=True, default=uuid4, index=True)


class TimestampMixin:
    # created_at / updated_at audit timestamps.
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now())
