from datetime import datetime
from enum import Enum

from app.extensions import db


class ReportStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)

    scan_req_id = db.Column(db.String(50), nullable=False)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id"), nullable=False, unique=True)

    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    radiographer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    radiologist_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    content = db.Column(db.Text, nullable=False)
    radiologist_text = db.Column(db.Text, nullable=True)  # ✅ keep this

    status = db.Column(db.String(30), nullable=False, default=ReportStatus.PENDING.value)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ReportImage(db.Model):
    __tablename__ = "report_images"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)