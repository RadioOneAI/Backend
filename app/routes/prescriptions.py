import os
import re
from sqlalchemy.exc import IntegrityError
from flask import Blueprint, request, send_file
from flask_jwt_extended import current_user

from app.extensions import db
from app.models import Prescription, PrescriptionImage, Role, User, PrescriptionStatus
from app.utils.responses import ok, fail
from app.utils.decorators import active_required, receptionist_or_radiographer_required, admin_required
from app.utils.upload import save_prescription_image, delete_file_if_exists

prescriptions_bp = Blueprint("prescriptions", __name__, url_prefix="/api/prescriptions")

SCAN_REQ_ID_RE = re.compile(r"^sr_\d{6}$")  # sr_000001


def user_brief(u: User | None):
    if not u:
        return None
    return {"id": u.id, "name": u.name, "role": u.role, "username": u.username}


def can_view_prescription(p: Prescription) -> bool:
    if current_user.role in {
        Role.RECEPTIONIST.value,
        Role.RADIOGRAPHER.value,
        Role.RADIOLOGIST.value,
    }:
        return True

    if current_user.role == Role.DOCTOR.value and p.doctor_id == current_user.id:
        return True

    if current_user.role == Role.PATIENT.value and p.patient_id == current_user.id:
        return True

    return False


def image_url(img: PrescriptionImage):
    return f"/api/prescriptions/{img.prescription_id}/images/{img.id}"


def prescription_response(p: Prescription):
    created_by = User.query.get(p.created_by_id) if p.created_by_id else None
    updated_by = User.query.get(p.updated_by_id) if p.updated_by_id else None

    imgs = PrescriptionImage.query.filter_by(prescription_id=p.id).order_by(PrescriptionImage.id.asc()).all()

    return {
        "id": p.id,
        "scan_req_id": p.scan_req_id,
        "doctor_id": p.doctor_id,
        "patient_id": p.patient_id,
        "scan_type": p.scan_type,
        "organ": p.organ,
        "description": p.description,
        "status": p.status,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
        "created_by": user_brief(created_by),
        "updated_by": user_brief(updated_by),

        # ✅ multiple images
        "images": [
            {
                "id": im.id,
                "file_path": im.file_path,
                "url": image_url(im),
                "uploaded_by_id": im.uploaded_by_id,
                "created_at": im.created_at.isoformat(),
            }
            for im in imgs
        ],
    }

def prescription_summary(p: Prescription):
    created_by = User.query.get(p.created_by_id) if p.created_by_id else None
    updated_by = User.query.get(p.updated_by_id) if p.updated_by_id else None

    images_count = PrescriptionImage.query.filter_by(prescription_id=p.id).count()

    return {
        "id": p.id,
        "scan_req_id": p.scan_req_id,
        "doctor_id": p.doctor_id,
        "patient_id": p.patient_id,
        "scan_type": p.scan_type,
        "organ": p.organ,
        "description": p.description,
        "status": p.status,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
        "created_by": user_brief(created_by),
        "updated_by": user_brief(updated_by),
        "images_count": images_count,
    }

# -------------------------
# Global Prescription List
# -------------------------
@prescriptions_bp.get("")
@active_required
def list_prescriptions():
    q = Prescription.query

    doctor_id = request.args.get("doctor_id", type=int)
    patient_id = request.args.get("patient_id", type=int)

    # radiographer / radiologist -> all, optional filters
    if current_user.role in {Role.RADIOGRAPHER.value, Role.RADIOLOGIST.value}:
        if doctor_id:
            q = q.filter(Prescription.doctor_id == doctor_id)
        if patient_id:
            q = q.filter(Prescription.patient_id == patient_id)

        items = q.order_by(Prescription.id.desc()).all()
        return ok([prescription_summary(p) for p in items], "Prescriptions list")

    # receptionist -> all without advanced cross-role filtering if you want
    if current_user.role == Role.RECEPTIONIST.value:
        if patient_id:
            q = q.filter(Prescription.patient_id == patient_id)
        items = q.order_by(Prescription.id.desc()).all()
        return ok([prescription_summary(p) for p in items], "Prescriptions list")

    # doctor -> only own prescriptions, optional patient filter
    if current_user.role == Role.DOCTOR.value:
        q = q.filter(Prescription.doctor_id == current_user.id)
        if patient_id:
            q = q.filter(Prescription.patient_id == patient_id)

        items = q.order_by(Prescription.id.desc()).all()
        return ok([prescription_summary(p) for p in items], "My prescriptions list")

    # patient -> only own
    if current_user.role == Role.PATIENT.value:
        q = q.filter(Prescription.patient_id == current_user.id)
        items = q.order_by(Prescription.id.desc()).all()
        return ok([prescription_summary(p) for p in items], "My prescriptions list")

    return fail("Access denied.", code=403)


# -------------------------
# GET by ID
# -------------------------
@prescriptions_bp.get("/<int:prescription_id>")
@active_required
def get_prescription(prescription_id: int):
    p = Prescription.query.get(prescription_id)
    if not p:
        return fail("Prescription not found.", code=404)

    if not can_view_prescription(p):
        return fail("Access denied.", code=403)

    return ok(prescription_response(p), "Prescription details")


# -------------------------
# GET single image (secure)
# -------------------------
@prescriptions_bp.get("/<int:prescription_id>/images/<int:image_id>")
@active_required
def get_prescription_image(prescription_id: int, image_id: int):
    p = Prescription.query.get(prescription_id)
    if not p:
        return fail("Prescription not found.", code=404)

    if not can_view_prescription(p):
        return fail("Access denied.", code=403)

    img = PrescriptionImage.query.filter_by(id=image_id, prescription_id=prescription_id).first()
    if not img:
        return fail("Image not found.", code=404)

    abs_path = os.path.join(os.getcwd(), img.file_path)
    if not os.path.exists(abs_path):
        return fail("Image file missing on server.", code=404)

    return send_file(abs_path)


# -------------------------
# CREATE (multipart/form-data, multiple files)
# -------------------------
@prescriptions_bp.post("")
@receptionist_or_radiographer_required
def create_prescription():
    form = request.form

    scan_req_id = (form.get("scan_req_id") or "").strip()
    patient_id = (form.get("patient_id") or "").strip()
    scan_type = (form.get("scan_type") or "").strip()
    organ = (form.get("organ") or "").strip()

    if not scan_req_id or not patient_id or not scan_type or not organ:
        return fail("scan_req_id, patient_id, scan_type, organ are required.", code=400)

    # ✅ validate scan_req_id format
    if not SCAN_REQ_ID_RE.match(scan_req_id):
        return fail("scan_req_id must match format sr_000001 (sr_ + 6 digits).", code=400)

    # validate patient
    try:
        patient_id_int = int(patient_id)
    except ValueError:
        return fail("patient_id must be an integer.", code=400)

    patient = User.query.get(patient_id_int)
    if not patient or patient.role != Role.PATIENT.value:
        return fail("Invalid patient_id.", code=400)

    # optional doctor
    doctor_id = form.get("doctor_id")
    doctor_id_int = None
    if doctor_id:
        try:
            doctor_id_int = int(doctor_id)
        except ValueError:
            return fail("doctor_id must be an integer.", code=400)
        doctor = User.query.get(doctor_id_int)
        if not doctor or doctor.role != Role.DOCTOR.value:
            return fail("Invalid doctor_id.", code=400)

    description = (form.get("description") or "").strip() or None
    status = PrescriptionStatus.PENDING.value

    p = Prescription(
        scan_req_id=scan_req_id,
        doctor_id=doctor_id_int,
        patient_id=patient_id_int,
        scan_type=scan_type,
        organ=organ,
        description=description,
        status=status,
        created_by_id=current_user.id,
        updated_by_id=None,
    )

    try:
        db.session.add(p)
        db.session.flush()  # get p.id before images
    except IntegrityError:
        db.session.rollback()
        return fail("scan_req_id already exists.", code=409)

    # ✅ multiple images upload
    files = request.files.getlist("prescription_images")
    saved_paths = []
    try:
        for f in files:
            if not f or not f.filename:
                continue
            path = save_prescription_image(f, "uploads")
            saved_paths.append(path)
            db.session.add(PrescriptionImage(
                prescription_id=p.id,
                file_path=path,
                uploaded_by_id=current_user.id
            ))

        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        # cleanup any files saved before error
        for path in saved_paths:
            delete_file_if_exists(path)
        return fail(str(e), code=400)
    except Exception:
        db.session.rollback()
        for path in saved_paths:
            delete_file_if_exists(path)
        return fail("Failed to create prescription.", code=500)

    return ok(prescription_response(p), "Prescription created", 201)


# -------------------------
# UPDATE (multipart/form-data)
# - append images by default
# - if replace_images=true: delete old files + delete old rows then save new
# -------------------------
@prescriptions_bp.patch("/<int:prescription_id>")
@receptionist_or_radiographer_required
def update_prescription(prescription_id: int):
    p = Prescription.query.get(prescription_id)
    if not p:
        return fail("Prescription not found.", code=404)

    form = request.form

    # Optional text updates
    if "patient_id" in form:
        try:
            pid = int((form.get("patient_id") or "").strip())
        except ValueError:
            return fail("patient_id must be an integer.", code=400)
        patient = User.query.get(pid)
        if not patient or patient.role != Role.PATIENT.value:
            return fail("Invalid patient_id.", code=400)
        p.patient_id = pid

    if "doctor_id" in form:
        doc_val = (form.get("doctor_id") or "").strip()
        if doc_val == "":
            p.doctor_id = None
        else:
            try:
                did = int(doc_val)
            except ValueError:
                return fail("doctor_id must be an integer.", code=400)
            doctor = User.query.get(did)
            if not doctor or doctor.role != Role.DOCTOR.value:
                return fail("Invalid doctor_id.", code=400)
            p.doctor_id = did

    if "scan_type" in form and form.get("scan_type"):
        p.scan_type = form.get("scan_type").strip()

    if "organ" in form and form.get("organ"):
        p.organ = form.get("organ").strip()

    if "description" in form:
        p.description = (form.get("description") or "").strip() or None

    if "status" in form and form.get("status"):
        new_status = form.get("status").strip().lower()
        if new_status not in {s.value for s in PrescriptionStatus}:
            return fail("Invalid status. Allowed: pending, scanned, reported.", code=400)
        p.status = new_status

    # ✅ images behavior
    replace_images = (form.get("replace_images") or "").strip().lower() in {"1", "true", "yes"}

    files = request.files.getlist("prescription_images")
    saved_paths = []

    try:
        if replace_images and files:
            # delete old image files + rows
            old_imgs = PrescriptionImage.query.filter_by(prescription_id=p.id).all()
            for oi in old_imgs:
                delete_file_if_exists(oi.file_path)
                db.session.delete(oi)

        # add new images (append OR after replace)
        for f in files:
            if not f or not f.filename:
                continue
            path = save_prescription_image(f, "uploads")
            saved_paths.append(path)
            db.session.add(PrescriptionImage(
                prescription_id=p.id,
                file_path=path,
                uploaded_by_id=current_user.id
            ))

        # audit
        p.updated_by_id = current_user.id

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
        return fail("Failed to update prescription.", code=500)

    return ok(prescription_response(p), "Prescription updated")

# -------------------------
# DELETE (Admin Only)
# -------------------------
@prescriptions_bp.delete("/<int:prescription_id>")
@admin_required
def delete_prescription(prescription_id: int):

    p = Prescription.query.get(prescription_id)

    if not p:
        return fail("Prescription not found.", code=404)

    imgs = PrescriptionImage.query.filter_by(prescription_id=p.id).all()

    for im in imgs:
        delete_file_if_exists(im.file_path)
        db.session.delete(im)

    db.session.delete(p)
    db.session.commit()

    return ok(None, "Prescription deleted")