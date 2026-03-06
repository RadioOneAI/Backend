from datetime import datetime
from enum import Enum

from app.extensions import db


class ScanImageStatus(str, Enum):
    PENDING = "pending"


class ScannedImage(db.Model):
    __tablename__ = "scanned_images"

    id = db.Column(db.Integer, primary_key=True)

    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id"), nullable=False)
    scan_req_id = db.Column(db.String(50), nullable=False)

    radiographer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    file_path = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False, default=ScanImageStatus.PENDING.value)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)