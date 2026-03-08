from datetime import datetime, timezone, UTC
from enum import Enum

from app.extensions import db


class ReportStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


def utc_now():
    return datetime.now(timezone.utc)


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)

    scan_req_id = db.Column(db.String(50), nullable=False)

    prescription_id = db.Column(
        db.Integer,
        db.ForeignKey("prescriptions.id"),
        nullable=False,
        unique=True,
    )

    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    radiographer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    radiologist_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=True, unique=True)

    scan_type = db.Column(db.String(50), nullable=True)
    organ = db.Column(db.String(100), nullable=True)
    analysis_time_ms = db.Column(db.Integer, nullable=True)

    radiologist_text = db.Column(db.Text, nullable=True)

    summary = db.Column(db.JSON, nullable=True)
    classification = db.Column(db.JSON, nullable=True)
    detection = db.Column(db.JSON, nullable=True)
    segmentation = db.Column(db.JSON, nullable=True)
    images = db.Column(db.JSON, nullable=True)

    status = db.Column(
        db.String(30),
        nullable=False,
        default=ReportStatus.PENDING.value,
    )

    report_images = db.relationship(
        "ReportImage",
        backref="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy=True,
    )

    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "scan_request_id": self.scan_req_id,
            "scan_req_id": self.scan_req_id,
            "prescription_id": self.prescription_id,
            "patient_id": self.patient_id,
            "radiographer_id": self.radiographer_id,
            "radiologist_id": self.radiologist_id,
            "doctor_id": self.doctor_id,
            "scan_type": self.scan_type,
            "organ": self.organ,
            "analysis_time_ms": self.analysis_time_ms,
            "radiologist_text": self.radiologist_text,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "summary": self.summary or {},
            "classification": self.classification or {},
            "detection": self.detection or {},
            "segmentation": self.segmentation or {},
            "images": self.images or {},
            "report_images": [img.to_dict() for img in self.report_images],
        }

    @staticmethod
    def from_payload(data):
        created_at_value = None
        if data.get("created_at"):
            try:
                created_at_value = datetime.fromisoformat(data["created_at"])
                if created_at_value.tzinfo is None:
                    created_at_value = created_at_value.replace(tzinfo=timezone.utc)
            except ValueError:
                created_at_value = utc_now()

        report = Report(
            scan_req_id=data.get("scan_request_id") or data.get("scan_req_id"),
            prescription_id=data.get("prescription_id"),
            patient_id=data.get("patient_id"),
            radiographer_id=data.get("radiographer_id"),
            radiologist_id=data.get("radiologist_id"),
            doctor_id=data.get("doctor_id"),
            scan_type=data.get("scan_type"),
            organ=data.get("organ"),
            analysis_time_ms=data.get("analysis_time_ms"),
            radiologist_text=data.get("radiologist_text"),
            summary=data.get("summary"),
            classification=data.get("classification"),
            detection=data.get("detection"),
            segmentation=data.get("segmentation"),
            images=data.get("images"),
            status=data.get("status", ReportStatus.PENDING.value),
        )

        if created_at_value:
            report.created_at = created_at_value
            report.updated_at = created_at_value

        return report

    def update_from_payload(self, data):
        if "scan_request_id" in data or "scan_req_id" in data:
            self.scan_req_id = data.get("scan_request_id") or data.get("scan_req_id")

        if "prescription_id" in data:
            self.prescription_id = data.get("prescription_id")
        if "patient_id" in data:
            self.patient_id = data.get("patient_id")
        if "radiographer_id" in data:
            self.radiographer_id = data.get("radiographer_id")
        if "radiologist_id" in data:
            self.radiologist_id = data.get("radiologist_id")
        if "doctor_id" in data:
            self.doctor_id = data.get("doctor_id")

        if "scan_type" in data:
            self.scan_type = data.get("scan_type")
        if "organ" in data:
            self.organ = data.get("organ")
        if "analysis_time_ms" in data:
            self.analysis_time_ms = data.get("analysis_time_ms")
        if "radiologist_text" in data:
            self.radiologist_text = data.get("radiologist_text")

        if "summary" in data:
            self.summary = data.get("summary")
        if "classification" in data:
            self.classification = data.get("classification")
        if "detection" in data:
            self.detection = data.get("detection")
        if "segmentation" in data:
            self.segmentation = data.get("segmentation")
        if "images" in data:
            self.images = data.get("images")

        if "status" in data:
            self.status = data.get("status")

        if data.get("created_at"):
            try:
                created_at_value = datetime.fromisoformat(data["created_at"])
                if created_at_value.tzinfo is None:
                    created_at_value = created_at_value.replace(tzinfo=timezone.utc)
                self.created_at = created_at_value
            except ValueError:
                pass


class ReportImage(db.Model):
    __tablename__ = "report_images"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path = db.Column(db.String(255), nullable=False)
    image_type = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "report_id": self.report_id,
            "file_path": self.file_path,
            "image_type": self.image_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }