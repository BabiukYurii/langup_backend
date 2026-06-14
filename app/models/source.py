from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.models.base import Base, TimestampMixin, UUIDMixin


class Source(Base, UUIDMixin, TimestampMixin):
    # A web page / document a word was captured from.
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_source_user_url"),)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    source_type = Column(String(32), nullable=False, server_default="WEB_PAGE")  # SourceType
    url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    domain = Column(String(255), nullable=True, index=True)
    language = Column(String(8), nullable=True)
    raw_html_key = Column(Text, nullable=True)  # object-storage key for captured HTML (optional)
