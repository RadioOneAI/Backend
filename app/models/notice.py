from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class NoticePriority(str, Enum):
    CRITICAL = "critical"
    URGENT = "urgent"
    ROUTINE = "routine"


class Notice(db.Model):
    __tablename__ = "notices"

    id = db.Column(db.Integer, primary_key=True)

    prescription_id = db.Column(
        db.Integer,
        db.ForeignKey("prescriptions.id"),
        nullable=False,
    )
    scan_req_id = db.Column(db.String(50), nullable=False)

    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    radiologist_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    radiographer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    priority = db.Column(db.String(20), nullable=False)

    diagnosis = db.Column(db.Text, nullable=True)
    reply_message = db.Column(db.Text, nullable=True)
    read_back_verification = db.Column(db.Boolean, nullable=True)

    # Target receivers
    send_to_radiologist = db.Column(db.Boolean, nullable=False, default=False)
    send_to_doctor = db.Column(db.Boolean, nullable=False, default=False)

    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "prescription_id": self.prescription_id,
            "scan_req_id": self.scan_req_id,
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "radiologist_id": self.radiologist_id,
            "radiographer_id": self.radiographer_id,
            "priority": self.priority,
            "diagnosis": self.diagnosis,
            "reply_message": self.reply_message,
            "read_back_verification": self.read_back_verification,
            "send_to_radiologist": self.send_to_radiologist,
            "send_to_doctor": self.send_to_doctor,
            "updated_by": self.updated_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }