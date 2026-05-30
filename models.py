from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import uuid

class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source       = Column(String)
    scan_type    = Column(String)
    status       = Column(String, default="pending")
    created_at   = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    files = relationship("ScannedFile", back_populates="job")


class ScannedFile(Base):
    __tablename__ = "scanned_files"

    id             = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id         = Column(String, ForeignKey("scan_jobs.id"))
    file_name      = Column(String)
    file_path      = Column(String)
    file_hash      = Column(String, nullable=True)
    last_modified  = Column(String, nullable=True)
    owner_email    = Column(String, nullable=True)
    master_of_data = Column(String, nullable=True)
    status         = Column(String, default="pending")

    job      = relationship("ScanJob", back_populates="files")
    findings = relationship("Finding", back_populates="file")


class Finding(Base):
    __tablename__ = "findings"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    file_id    = Column(String, ForeignKey("scanned_files.id"))
    risk_level = Column(String)
    category   = Column(String)
    pii_types  = Column(Text)
    regex_hits = Column(Text, nullable=True)
    reason     = Column(Text)

    reviewer_action = Column(String, nullable=True)
    reviewed_by     = Column(String, nullable=True)
    reviewed_at     = Column(DateTime, nullable=True)

    file = relationship("ScannedFile", back_populates="findings")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    file_id    = Column(String, ForeignKey("scanned_files.id"))
    action     = Column(String)
    actor      = Column(String)
    detail     = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)