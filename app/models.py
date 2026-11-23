from datetime import datetime
from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    is_approved = Column(Integer, nullable=False, default=0)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chits = relationship("Chit", back_populates="owner", cascade="all, delete-orphan")


class Chit(Base):
    __tablename__ = "chits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    chit_amount = Column(Numeric(12, 2), nullable=False)
    start_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="chits")
    transactions = relationship("Transaction", back_populates="chit", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chit_id = Column(UUID(as_uuid=True), ForeignKey("chits.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_date = Column(Date, nullable=True)
    amount_transferred = Column(Numeric(12, 2), nullable=True)
    transaction_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="needs_review")
    source_file_name = Column(String(255), nullable=True)
    ocr_text = Column(Text, nullable=True)
    ocr_confidence = Column(Numeric(5, 2), nullable=True)
    notes = Column(Text, nullable=True)
    image_data = Column(LargeBinary, nullable=True)
    image_content_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    chit = relationship("Chit", back_populates="transactions")

    __table_args__ = (
        UniqueConstraint("owner_id", "chit_id", "transaction_id", name="uq_owner_chit_transaction"),
    )
