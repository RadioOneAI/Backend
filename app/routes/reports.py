import os
from datetime import datetime, timezone

from flask import Blueprint, request, send_file
from flask_jwt_extended import current_user

from app.extensions import db
from app.models import (
    Report,
    ReportImage,
    ReportStatus,
    ReportFeedback,
    Prescription,
    PrescriptionStatus,
    User,
    Role,
)
from app.utils.responses import ok, fail
from app.utils.decorators import active_required, radiographer_required, radiologist_required
from app.utils.upload import delete_file_if_exists

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def user_brief(u):
    if not u:
        return None
    return {
        "id": u.id,
        "name": u.name,
        "role": u.role,
        "username": u.username,
    }


def patient_brief(u):
    if not u:
        return None
    return {
        "id": u.id,
        "name": u.name,
        "username": u.username,
        "email": u.email,
        "phone": u.phone,
        "gender": u.gender,
        "date_of_birth": u.date_of_birth.isoformat() if u.date_of_birth else None,
        "age": u.age,
    }


def report_image_url(img: ReportImage):
    return f"/api/reports/{img.report_id}/images/{img.id}/file"


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def can_view_report(r: Report) -> bool:
    if current_user.role == Role.RADIOLOGIST.value:
        return True

    if current_user.role == Role.RADIOGRAPHER.value and r.radiographer_id == current_user.id:
        return True

    if current_user.role == Role.DOCTOR.value:
        return r.doctor_id == current_user.id

    if current_user.role == Role.PATIENT.value:
        return r.patient_id == current_user.id and r.status == ReportStatus.APPROVED.value

    return False


def feedback_response(f: ReportFeedback):
    u = f.user
    return {
        "id": f.id,
        "report_id": f.report_id,
        "user_id": f.user_id,
        "user_name": u.name if u else None,
        "user_role": u.role if u else None,
        "message": f.message,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def report_response(r: Report):
    doctor = User.query.get(r.doctor_id) if r.doctor_id else None
    patient = User.query.get(r.patient_id) if r.patient_id else None
    radiographer = User.query.get(r.radiographer_id) if r.radiographer_id else None
    radiologist = User.query.get(r.radiologist_id) if r.radiologist_id else None

    report_images = ReportImage.query.filter_by(report_id=r.id).order_by(ReportImage.id.asc()).all()
    feedbacks = ReportFeedback.query.filter_by(report_id=r.id).order_by(ReportFeedback.id.asc()).all()

    return {
        "id": r.id,
        "scan_request_id": r.scan_req_id,
        "scan_req_id": r.scan_req_id,
        "prescription_id": r.prescription_id,

        "patient_id": r.patient_id,
        "patient": patient_brief(patient),

        "radiographer_id": r.radiographer_id,
        "radiographer": user_brief(radiographer),

        "radiologist_id": r.radiologist_id,
        "radiologist": user_brief(radiologist),

        "doctor_id": r.doctor_id,
        "doctor": user_brief(doctor),

        "scan_type": r.scan_type,
        "organ": r.organ,
        "analysis_time_ms": r.analysis_time_ms,

        "radiologist_text": r.radiologist_text,

        "summary": r.summary or {},
        "classification": r.classification or {},
        "detection": r.detection or {},
        "segmentation": r.segmentation or {},
        "images": r.images or {},

        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,

        "report_images": [
            {
                "id": img.id,
                "file_path": img.file_path,
                "image_type": img.image_type,
                "url": report_image_url(img),
                "created_at": img.created_at.isoformat() if img.created_at else None,
            }
            for img in report_images
        ],

        "feedbacks": [
            feedback_response(f)
            for f in feedbacks
        ],
    }


def can_add_feedback(report: Report) -> bool:
    if not report:
        return False

    prescription = Prescription.query.get(report.prescription_id) if report.prescription_id else None

    if current_user.role == Role.PATIENT.value:
        return report.patient_id == current_user.id

    if current_user.role == Role.DOCTOR.value:
        return report.doctor_id == current_user.id

    if current_user.role == Role.RADIOGRAPHER.value:
        return report.radiographer_id == current_user.id

    if current_user.role == Role.RADIOLOGIST.value:
        return (
            report.radiologist_id == current_user.id or
            (prescription and prescription.radiologist_id == current_user.id)
        )

    return False


# -------------------------
# CREATE REPORT
# radiographer only
# JSON payload
# -------------------------
@reports_bp.post("")
@radiographer_required
def create_report():
    data = request.get_json(silent=True) or {}

    prescription_id = data.get("prescription_id")
    if not prescription_id:
        return fail("prescription_id is required.", code=400)

    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return fail("Prescription not found.", code=404)

    existing = Report.query.filter_by(prescription_id=prescription_id).first()
    if existing:
        return fail("Report already exists for this prescription.", code=409)

    patient_id = data.get("patient_id")
    radiographer_id = data.get("radiographer_id")

    if patient_id != prescription.patient_id:
        return fail("patient_id does not match the prescription.", code=400)

    if radiographer_id != current_user.id:
        return fail("radiographer_id must be the current logged-in radiographer.", code=403)

    if data.get("doctor_id") and prescription.doctor_id and data.get("doctor_id") != prescription.doctor_id:
        return fail("doctor_id does not match the prescription.", code=400)

    if data.get("radiologist_id") and prescription.radiologist_id and data.get("radiologist_id") != prescription.radiologist_id:
        return fail("radiologist_id does not match the prescription.", code=400)

    scan_req_id = data.get("scan_request_id") or data.get("scan_req_id") or prescription.scan_req_id
    if not scan_req_id:
        return fail("scan_request_id is required.", code=400)

    report = Report(
        scan_req_id=scan_req_id,
        prescription_id=prescription.id,
        patient_id=prescription.patient_id,
        radiographer_id=current_user.id,
        radiologist_id=prescription.radiologist_id,
        doctor_id=prescription.doctor_id,
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

    created_at_value = parse_iso_datetime(data.get("created_at"))
    if created_at_value:
        report.created_at = created_at_value
        report.updated_at = created_at_value

    try:
        db.session.add(report)
        prescription.status = PrescriptionStatus.REPORTED.value
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        return fail(f"Failed to create report. {str(e)}", code=500)

    return ok(report_response(report), "Report created", 201)


# -------------------------
# UPDATE REPORT
# radiologist only
# -------------------------
@reports_bp.patch("/<int:report_id>")
@radiologist_required
def update_report(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    data = request.get_json(silent=True) or {}
    if not data:
        return fail("JSON body is required.", code=400)

    allowed_fields = {
        "scan_request_id",
        "scan_req_id",
        "scan_type",
        "organ",
        "analysis_time_ms",
        "radiologist_text",
        "summary",
        "classification",
        "detection",
        "segmentation",
        "images",
        "status",
    }

    invalid_fields = [k for k in data.keys() if k not in allowed_fields]
    if invalid_fields:
        return fail(f"Invalid fields: {', '.join(invalid_fields)}", code=400)

    if "scan_request_id" in data or "scan_req_id" in data:
        report.scan_req_id = data.get("scan_request_id") or data.get("scan_req_id")

    if "scan_type" in data:
        report.scan_type = data.get("scan_type")

    if "organ" in data:
        report.organ = data.get("organ")

    if "analysis_time_ms" in data:
        report.analysis_time_ms = data.get("analysis_time_ms")

    if "radiologist_text" in data:
        report.radiologist_text = data.get("radiologist_text")

    if "summary" in data:
        report.summary = data.get("summary")

    if "classification" in data:
        report.classification = data.get("classification")

    if "detection" in data:
        report.detection = data.get("detection")

    if "segmentation" in data:
        report.segmentation = data.get("segmentation")

    if "images" in data:
        report.images = data.get("images")

    if "status" in data:
        report.status = data.get("status")

    report.radiologist_id = current_user.id

    db.session.commit()

    return ok(report_response(report), "Report updated")


# -------------------------
# APPROVE REPORT
# radiologist only
# -------------------------
@reports_bp.patch("/<int:report_id>/status")
@radiologist_required
def update_report_status(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip().lower()

    allowed_statuses = {
        ReportStatus.APPROVED.value,
        ReportStatus.DECLINED.value,
    }

    if status not in allowed_statuses:
        return fail("status must be 'approved' or 'declined'.", code=400)

    report.status = status
    report.radiologist_id = current_user.id

    db.session.commit()

    message = "Report approved" if status == ReportStatus.APPROVED.value else "Report declined"
    return ok(report_response(report), message)


# -------------------------
# LIST REPORTS
# -------------------------
@reports_bp.get("")
@active_required
def list_reports():
    q = Report.query

    patient_id = request.args.get("patient_id", type=int)
    doctor_id = request.args.get("doctor_id", type=int)
    prescription_id = request.args.get("prescription_id", type=int)
    status = request.args.get("status")

    if prescription_id:
        q = q.filter(Report.prescription_id == prescription_id)
    if status:
        q = q.filter(Report.status == status)

    if current_user.role == Role.RADIOLOGIST.value:
        if patient_id:
            q = q.filter(Report.patient_id == patient_id)
        if doctor_id:
            q = q.filter(Report.doctor_id == doctor_id)

        items = q.order_by(Report.id.desc()).all()
        return ok([report_response(r) for r in items], "Reports list")

    if current_user.role == Role.RADIOGRAPHER.value:
        q = q.filter(Report.radiographer_id == current_user.id)
        if patient_id:
            q = q.filter(Report.patient_id == patient_id)
        items = q.order_by(Report.id.desc()).all()
        return ok([report_response(r) for r in items], "My reports list")

    if current_user.role == Role.DOCTOR.value:
        q = q.filter(
            Report.doctor_id == current_user.id,
            Report.status == ReportStatus.APPROVED.value
        )
        if patient_id:
            q = q.filter(Report.patient_id == patient_id)
        items = q.order_by(Report.id.desc()).all()
        return ok([report_response(r) for r in items], "My reports list")

    if current_user.role == Role.PATIENT.value:
        q = q.filter(
            Report.patient_id == current_user.id,
            Report.status == ReportStatus.APPROVED.value
        )
        items = q.order_by(Report.id.desc()).all()
        return ok([report_response(r) for r in items], "My reports list")

    return fail("Access denied.", code=403)


# -------------------------
# GET SINGLE REPORT
# -------------------------
@reports_bp.get("/<int:report_id>")
@active_required
def get_report(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    if not can_view_report(report):
        return fail("Access denied.", code=403)

    return ok(report_response(report), "Report details")


# -------------------------
# GET REPORT IMAGE FILE
# optional extra attached file images
# -------------------------
@reports_bp.get("/<int:report_id>/images/<int:image_id>/file")
@active_required
def get_report_image_file(report_id: int, image_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    if not can_view_report(report):
        return fail("Access denied.", code=403)

    img = ReportImage.query.filter_by(id=image_id, report_id=report_id).first()
    if not img:
        return fail("Report image not found.", code=404)

    abs_path = os.path.join(os.getcwd(), img.file_path)
    if not os.path.exists(abs_path):
        return fail("Image file missing on server.", code=404)

    return send_file(abs_path)


# -------------------------
# DELETE REPORT
# radiologist only
# -------------------------
@reports_bp.delete("/<int:report_id>")
@radiologist_required
def delete_report(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    prescription = Prescription.query.get(report.prescription_id)

    imgs = ReportImage.query.filter_by(report_id=report.id).all()
    for img in imgs:
        delete_file_if_exists(img.file_path)
        db.session.delete(img)

    db.session.delete(report)
    db.session.flush()

    db.session.commit()

    return ok(None, "Report deleted")


# -------------------------
# ADD REPORT FEEDBACK
# patient / doctor / radiographer / radiologist
# -------------------------
@reports_bp.post("/<int:report_id>/feedbacks")
@active_required
def add_report_feedback(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    if not can_add_feedback(report):
        return fail("Access denied.", code=403)

    data = request.get_json() or {}
    message = (data.get("message") or "").strip()

    if not message:
        return fail("message is required.", code=400)

    feedback = ReportFeedback(
        report_id=report.id,
        user_id=current_user.id,
        message=message,
    )

    db.session.add(feedback)
    db.session.commit()

    return ok(feedback_response(feedback), "Feedback added", 201)


# -------------------------
# LIST REPORT FEEDBACKS
# -------------------------
@reports_bp.get("/<int:report_id>/feedbacks")
@active_required
def list_report_feedbacks(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    if not can_add_feedback(report) and not can_view_report(report):
        return fail("Access denied.", code=403)

    items = ReportFeedback.query.filter_by(report_id=report.id).order_by(ReportFeedback.id.asc()).all()
    return ok([feedback_response(f) for f in items], "Report feedbacks")

# -------------------------
# GET REPORT BY PRESCRIPTION ID
# -------------------------
@reports_bp.get("/prescription/<int:prescription_id>")
@active_required
def get_report_by_prescription_id(prescription_id: int):
    report = Report.query.filter_by(prescription_id=prescription_id).first()
    if not report:
        return fail("Report not found for this prescription.", code=404)

    if not can_view_report(report):
        return fail("Access denied.", code=403)

    return ok(report_response(report), "Report details")


# -------------------------
# UPDATE OWN FEEDBACK
# -------------------------
@reports_bp.patch("/<int:report_id>/feedbacks/<int:feedback_id>")
@active_required
def update_report_feedback(report_id: int, feedback_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    feedback = ReportFeedback.query.filter_by(
        id=feedback_id,
        report_id=report_id
    ).first()
    if not feedback:
        return fail("Feedback not found.", code=404)

    if feedback.user_id != current_user.id:
        return fail("You can update only your own feedback.", code=403)

    data = request.get_json() or {}
    message = (data.get("message") or "").strip()

    if not message:
        return fail("message is required.", code=400)

    feedback.message = message
    db.session.commit()

    return ok(feedback_response(feedback), "Feedback updated")


# -------------------------
# DELETE OWN FEEDBACK
# -------------------------
@reports_bp.delete("/<int:report_id>/feedbacks/<int:feedback_id>")
@active_required
def delete_report_feedback(report_id: int, feedback_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    feedback = ReportFeedback.query.filter_by(
        id=feedback_id,
        report_id=report_id
    ).first()
    if not feedback:
        return fail("Feedback not found.", code=404)

    if feedback.user_id != current_user.id:
        return fail("You can delete only your own feedback.", code=403)

    db.session.delete(feedback)
    db.session.commit()

    return ok(None, "Feedback deleted")