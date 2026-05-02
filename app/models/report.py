from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class ReportStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


def utc_now():
    return datetime.now(timezone.utc)


def normalize_status(value):
    if not value:
        return ReportStatus.PENDING.value

    value = str(value).strip().lower()

    if value == "approve":
        return ReportStatus.APPROVED.value

    if value == "decline":
        return ReportStatus.DECLINED.value

    if value in [s.value for s in ReportStatus]:
        return value

    return ReportStatus.PENDING.value


def build_report_package(data):
    """
    Stores all AI report details inside Report.summary JSON column.

    Final DB shape:
    {
        "overview": {...},
        "diagnoses": {
            "patient": {...},
            "clinical": {...},
            "technical": {...},
            "status": "success"
        },
        "tumors": [...],
        "original_image": "base64..."
    }
    """

    raw_summary = data.get("summary") or {}

    # Case 1: already stored in final package format
    if isinstance(raw_summary, dict) and (
        "overview" in raw_summary
        or "diagnoses" in raw_summary
        or "tumors" in raw_summary
        or "original_image" in raw_summary
    ):
        return {
            "overview": raw_summary.get("overview") or {},
            "diagnoses": (
                data.get("diagnoses")
                or raw_summary.get("diagnoses")
                or {}
            ),
            "tumors": (
                data.get("tumors")
                or raw_summary.get("tumors")
                or []
            ),
            "original_image": (
                data.get("original_image")
                or raw_summary.get("original_image")
            ),
        }

    # Case 2: normal AI server response format
    return {
        "overview": raw_summary if isinstance(raw_summary, dict) else {},
        "diagnoses": data.get("diagnoses") or {},
        "tumors": data.get("tumors") or [],
        "original_image": data.get("original_image"),
    }


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

    scan_type = db.Column(db.String(50), nullable=True)
    organ = db.Column(db.String(100), nullable=True)
    analysis_time_ms = db.Column(db.Integer, nullable=True)
    radiologist_text = db.Column(db.Text, nullable=True)

    summary = db.Column(db.JSON, nullable=True)
    classification = db.Column(db.JSON, nullable=True)
    detection = db.Column(db.JSON, nullable=True)
    segmentation = db.Column(db.JSON, nullable=True)
    images = db.Column(db.JSON, nullable=True)

    diagnosis_patient = db.Column(db.Text, nullable=True)
    diagnosis_clinical = db.Column(db.Text, nullable=True)
    diagnosis_technical = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.String(30),
        nullable=False,
        default=ReportStatus.PENDING.value,
    )

    prescription = db.relationship(
        "Prescription",
        back_populates="report",
        lazy=True,
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
        package = self.summary or {}

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
            "summary": package.get("overview", {}),
            "diagnosis_patient": self.diagnosis_patient,
            "diagnosis_clinical": self.diagnosis_clinical,
            "diagnosis_technical": self.diagnosis_technical,
            "diagnoses": (
                {
                    "patient": self.diagnosis_patient,
                    "clinical": self.diagnosis_clinical,
                    "technical": self.diagnosis_technical,
                }
                if (
                    self.diagnosis_patient
                    or self.diagnosis_clinical
                    or self.diagnosis_technical
                )
                else package.get("diagnoses", {})
            ),
            "tumors": package.get("tumors", []),
            "original_image": package.get("original_image"),
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
            summary=build_report_package(data),
            classification=data.get("classification") or {},
            detection=data.get("detection") or {},
            segmentation=data.get("segmentation") or {},
            images=data.get("images") or {},
            status=normalize_status(data.get("status")),
        )

        if created_at_value:
            report.created_at = created_at_value
            report.updated_at = created_at_value

        return report

    def update_from_payload(self, data):
        if "scan_request_id" in data or "scan_req_id" in data:
            self.scan_req_id = data.get("scan_request_id") or data.get("scan_req_id")

        if "scan_type" in data:
            self.scan_type = data.get("scan_type")

        if "organ" in data:
            self.organ = data.get("organ")

        if "analysis_time_ms" in data:
            self.analysis_time_ms = data.get("analysis_time_ms")

        if "radiologist_text" in data:
            self.radiologist_text = data.get("radiologist_text")

        if (
            "summary" in data
            or "diagnoses" in data
            or "tumors" in data
            or "original_image" in data
        ):
            self.summary = build_report_package(data)

        if "classification" in data:
            self.classification = data.get("classification") or {}

        if "detection" in data:
            self.detection = data.get("detection") or {}

        if "segmentation" in data:
            self.segmentation = data.get("segmentation") or {}

        if "images" in data:
            self.images = data.get("images") or {}

        if "status" in data:
            self.status = normalize_status(data.get("status"))


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