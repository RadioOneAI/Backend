import os
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
    ScannedImage,
    User,
    Role,
)
from app.utils.responses import ok, fail
from app.utils.decorators import active_required, radiographer_required, radiologist_required
from app.utils.upload import save_report_image, delete_file_if_exists

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


def can_view_report(r: Report) -> bool:
    if current_user.role == Role.RADIOLOGIST.value:
        return True

    if current_user.role == Role.RADIOGRAPHER.value and r.radiographer_id == current_user.id:
        return True

    if current_user.role == Role.DOCTOR.value:
        return r.doctor_id == current_user.id and r.status == ReportStatus.APPROVED.value

    if current_user.role == Role.PATIENT.value:
        return r.patient_id == current_user.id and r.status == ReportStatus.APPROVED.value

    return False


def report_response(r: Report):
    doctor = User.query.get(r.doctor_id) if r.doctor_id else None
    patient = User.query.get(r.patient_id) if r.patient_id else None
    radiographer = User.query.get(r.radiographer_id) if r.radiographer_id else None
    radiologist = User.query.get(r.radiologist_id) if r.radiologist_id else None

    imgs = ReportImage.query.filter_by(report_id=r.id).order_by(ReportImage.id.asc()).all()
    feedbacks = ReportFeedback.query.filter_by(report_id=r.id).order_by(ReportFeedback.id.asc()).all()

    return {
        "id": r.id,
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

        "content": r.content,
        "radiologist_text": r.radiologist_text,

        "status": r.status,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),

        "report_images": [
            {
                "id": img.id,
                "file_path": img.file_path,
                "url": report_image_url(img),
                "created_at": img.created_at.isoformat(),
            }
            for img in imgs
        ],

        "feedbacks": [
            feedback_response(f)
            for f in feedbacks
        ],
    }

def feedback_response(f: ReportFeedback):
    u = f.user
    return {
        "id": f.id,
        "report_id": f.report_id,
        "user_id": f.user_id,
        "user_name": u.name if u else None,
        "user_role": u.role if u else None,
        "message": f.message,
        "created_at": f.created_at.isoformat(),
        "updated_at": f.updated_at.isoformat(),
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
# -------------------------
@reports_bp.post("")
@radiographer_required
def create_report():
    form = request.form

    prescription_id = form.get("prescription_id", type=int)
    content = (form.get("content") or "").strip()

    if not prescription_id or not content:
        return fail("prescription_id and content are required.", code=400)

    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return fail("Prescription not found.", code=404)

    existing = Report.query.filter_by(prescription_id=prescription_id).first()
    if existing:
        return fail("Report already exists for this prescription.", code=409)

    scanned_images = ScannedImage.query.filter_by(prescription_id=prescription_id).all()
    if not scanned_images:
        return fail("Scanned images are required before creating a report.", code=400)

    report = Report(
        scan_req_id=prescription.scan_req_id,
        prescription_id=prescription.id,
        patient_id=prescription.patient_id,
        radiographer_id=current_user.id,
        radiologist_id=prescription.radiologist_id,
        doctor_id=prescription.doctor_id,
        content=content,
        radiologist_text=None,
        status=ReportStatus.PENDING.value,
    )

    files = request.files.getlist("report_images")
    saved_paths = []

    try:
        db.session.add(report)
        db.session.flush()

        for f in files:
            if not f or not f.filename:
                continue

            path = save_report_image(f, "uploads")
            saved_paths.append(path)

            db.session.add(ReportImage(
                report_id=report.id,
                file_path=path
            ))

        # once report exists, prescription becomes reported
        prescription.status = PrescriptionStatus.REPORTED.value

        db.session.commit()

    except ValueError as e:
        db.session.rollback()
        for path in saved_paths:
            delete_file_if_exists(path)
        return fail(str(e), code=400)

    except Exception:
        db.session.rollback()
        for path in saved_paths:
            delete_file_if_exists(path)
        return fail("Failed to create report.", code=500)

    return ok(report_response(report), "Report created", 201)


# -------------------------
# UPDATE REPORT
# radiologist only
# only radiologist_text
# -------------------------
@reports_bp.patch("/<int:report_id>")
@radiologist_required
def update_report(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    data = request.get_json() or {}

    if "radiologist_text" not in data:
        return fail("Only radiologist_text can be updated.", code=400)

    radiologist_text = (data.get("radiologist_text") or "").strip()
    if not radiologist_text:
        return fail("radiologist_text is required.", code=400)

    report.radiologist_text = radiologist_text
    report.radiologist_id = current_user.id

    db.session.commit()

    return ok(report_response(report), "Report updated")


# -------------------------
# APPROVE REPORT
# radiologist only
# -------------------------
@reports_bp.post("/<int:report_id>/approve")
@radiologist_required
def approve_report(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    report.status = ReportStatus.APPROVED.value
    report.radiologist_id = current_user.id
    db.session.commit()

    return ok(report_response(report), "Report approved")


# -------------------------
# DECLINE REPORT
# radiologist only
# -------------------------
@reports_bp.post("/<int:report_id>/decline")
@radiologist_required
def decline_report(report_id: int):
    report = Report.query.get(report_id)
    if not report:
        return fail("Report not found.", code=404)

    report.status = ReportStatus.DECLINED.value
    report.radiologist_id = current_user.id
    db.session.commit()

    return ok(report_response(report), "Report declined")


# -------------------------
# LIST REPORTS
# -------------------------
@reports_bp.get("")
@active_required
def list_reports():
    q = Report.query

    patient_id = request.args.get("patient_id", type=int)
    doctor_id = request.args.get("doctor_id", type=int)

    if current_user.role == Role.RADIOLOGIST.value:
        if patient_id:
            q = q.filter(Report.patient_id == patient_id)
        if doctor_id:
            q = q.filter(Report.doctor_id == doctor_id)

        items = q.order_by(Report.id.desc()).all()
        return ok([report_response(r) for r in items], "Reports list")

    if current_user.role == Role.RADIOGRAPHER.value:
        q = q.filter(Report.radiographer_id == current_user.id)
        items = q.order_by(Report.id.desc()).all()
        return ok([report_response(r) for r in items], "My reports list")

    if current_user.role == Role.DOCTOR.value:
        q = q.filter(
            Report.doctor_id == current_user.id,
            Report.status == ReportStatus.APPROVED.value
        )
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
    scanned_images = ScannedImage.query.filter_by(prescription_id=report.prescription_id).all()

    imgs = ReportImage.query.filter_by(report_id=report.id).all()
    for img in imgs:
        delete_file_if_exists(img.file_path)
        db.session.delete(img)

    db.session.delete(report)
    db.session.flush()

    remaining = Report.query.filter_by(prescription_id=report.prescription_id).count()
    if remaining == 0:
        if scanned_images:
            prescription.status = PrescriptionStatus.SCANNED.value
        else:
            prescription.status = PrescriptionStatus.PENDING.value

    db.session.commit()

    return ok(None, "Report deleted")

# -------------------------
# ADD REPORT FEEDBACK
# patient / doctor / radiographer / radiologist
# according to connected report
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