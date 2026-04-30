from flask import Blueprint, request
from flask_jwt_extended import current_user

from app.extensions import db
from app.models import (
    Notice,
    NoticePriority,
    Prescription,
    User,
    Role,
)
from app.utils.responses import ok, fail
from app.utils.decorators import active_required, radiographer_required

notices_bp = Blueprint("notices", __name__, url_prefix="/api/notices")


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


def notice_response(n: Notice):
    patient = User.query.get(n.patient_id) if n.patient_id else None
    doctor = User.query.get(n.doctor_id) if n.doctor_id else None
    radiologist = User.query.get(n.radiologist_id) if n.radiologist_id else None
    radiographer = User.query.get(n.radiographer_id) if n.radiographer_id else None
    updated_by_user = User.query.get(n.updated_by) if n.updated_by else None

    return {
        "id": n.id,
        "prescription_id": n.prescription_id,
        "scan_req_id": n.scan_req_id,

        "patient_id": n.patient_id,
        "patient": patient_brief(patient),

        "doctor_id": n.doctor_id,
        "doctor": user_brief(doctor),

        "radiologist_id": n.radiologist_id,
        "radiologist": user_brief(radiologist),

        "radiographer_id": n.radiographer_id,
        "radiographer": user_brief(radiographer),

        "priority": n.priority,
        "diagnosis": n.diagnosis,
        "reply_message": n.reply_message,
        "read_back_verification": n.read_back_verification,

        "send_to_radiologist": n.send_to_radiologist,
        "send_to_doctor": n.send_to_doctor,

        "updated_by": n.updated_by,
        "updated_by_user": user_brief(updated_by_user),

        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


def can_view_notice(n: Notice) -> bool:
    if current_user.role == Role.RADIOGRAPHER.value:
        return n.radiographer_id == current_user.id

    if current_user.role == Role.RADIOLOGIST.value:
        return n.send_to_radiologist and n.radiologist_id == current_user.id

    if current_user.role == Role.DOCTOR.value:
        return n.send_to_doctor and n.doctor_id == current_user.id

    return False


def can_reply_notice(n: Notice) -> bool:
    if current_user.role == Role.RADIOLOGIST.value:
        return n.send_to_radiologist and n.radiologist_id == current_user.id

    if current_user.role == Role.DOCTOR.value:
        return n.send_to_doctor and n.doctor_id == current_user.id

    return False


# -------------------------
# CREATE NOTICE
# only radiographer
# -------------------------
@notices_bp.post("")
@radiographer_required
def create_notice():
    data = request.get_json(silent=True) or {}

    prescription_id = data.get("prescription_id")
    priority = (data.get("priority") or "").strip().lower()
    diagnosis = (data.get("diagnosis") or "").strip()
    reply_message = (data.get("reply_message") or "").strip() or None
    read_back_verification = data.get("read_back_verification")
    send_to_radiologist = bool(data.get("send_to_radiologist", False))
    send_to_doctor = bool(data.get("send_to_doctor", False))

    if not prescription_id:
        return fail("prescription_id is required.", code=400)

    if priority not in {
        NoticePriority.CRITICAL.value,
        NoticePriority.URGENT.value,
        NoticePriority.ROUTINE.value,
    }:
        return fail("priority must be 'critical', 'urgent', or 'routine'.", code=400)

    if not diagnosis:
        return fail("diagnosis is required.", code=400)

    if read_back_verification is None:
        return fail("read_back_verification is required.", code=400)

    if not isinstance(read_back_verification, bool):
        return fail("read_back_verification must be true or false.", code=400)

    if not send_to_radiologist and not send_to_doctor:
        return fail("At least one of send_to_radiologist or send_to_doctor must be true.", code=400)

    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return fail("Prescription not found.", code=404)

    notice = Notice(
        prescription_id=prescription.id,
        scan_req_id=prescription.scan_req_id,
        patient_id=prescription.patient_id,
        doctor_id=prescription.doctor_id,
        radiologist_id=prescription.radiologist_id,
        radiographer_id=current_user.id,
        priority=priority,
        diagnosis=diagnosis,
        reply_message=reply_message,
        read_back_verification=read_back_verification,
        send_to_radiologist=send_to_radiologist,
        send_to_doctor=send_to_doctor,
        updated_by=current_user.id,
    )

    try:
        db.session.add(notice)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(f"Failed to create notice. {str(e)}", code=500)

    return ok(notice_response(notice), "Notice created", 201)


# -------------------------
# LIST NOTICES
# radiographer -> own created notices
# radiologist -> only notices sent to them
# doctor -> only notices sent to them
# -------------------------
@notices_bp.get("")
@active_required
def list_notices():
    q = Notice.query

    prescription_id = request.args.get("prescription_id", type=int)
    patient_id = request.args.get("patient_id", type=int)
    priority = request.args.get("priority")

    if prescription_id:
        q = q.filter(Notice.prescription_id == prescription_id)
    if patient_id:
        q = q.filter(Notice.patient_id == patient_id)
    if priority:
        q = q.filter(Notice.priority == priority.lower())

    if current_user.role == Role.RADIOGRAPHER.value:
        q = q.filter(Notice.radiographer_id == current_user.id)
        items = q.order_by(Notice.id.desc()).all()
        return ok([notice_response(n) for n in items], "My notices")

    if current_user.role == Role.RADIOLOGIST.value:
        q = q.filter(
            Notice.send_to_radiologist.is_(True),
            Notice.radiologist_id == current_user.id,
        )
        items = q.order_by(Notice.id.desc()).all()
        return ok([notice_response(n) for n in items], "Radiologist notices")

    if current_user.role == Role.DOCTOR.value:
        q = q.filter(
            Notice.send_to_doctor.is_(True),
            Notice.doctor_id == current_user.id,
        )
        items = q.order_by(Notice.id.desc()).all()
        return ok([notice_response(n) for n in items], "Doctor notices")

    return fail("Access denied.", code=403)


# -------------------------
# GET SINGLE NOTICE
# -------------------------
@notices_bp.get("/<int:notice_id>")
@active_required
def get_notice(notice_id: int):
    notice = Notice.query.get(notice_id)
    if not notice:
        return fail("Notice not found.", code=404)

    if not can_view_notice(notice):
        return fail("Access denied.", code=403)

    return ok(notice_response(notice), "Notice details")


# -------------------------
# PATCH REPLY MESSAGE
# only radiologist or doctor
# -------------------------
@notices_bp.patch("/<int:notice_id>/reply")
@active_required
def patch_notice_reply(notice_id: int):
    notice = Notice.query.get(notice_id)
    if not notice:
        return fail("Notice not found.", code=404)

    if not can_reply_notice(notice):
        return fail("Access denied.", code=403)

    data = request.get_json(silent=True) or {}
    reply_message = (data.get("reply_message") or "").strip()

    if not reply_message:
        return fail("reply_message is required.", code=400)

    notice.reply_message = reply_message
    notice.updated_by = current_user.id

    db.session.commit()

    return ok(notice_response(notice), "Reply message updated")


# -------------------------
# DELETE NOTICE
# only radiographer who created it
# -------------------------
@notices_bp.delete("/<int:notice_id>")
@radiographer_required
def delete_notice(notice_id: int):
    notice = Notice.query.get(notice_id)
    if not notice:
        return fail("Notice not found.", code=404)

    if notice.radiographer_id != current_user.id:
        return fail("Access denied.", code=403)

    db.session.delete(notice)
    db.session.commit()

    return ok(None, "Notice deleted")