import re
from sqlalchemy.exc import IntegrityError
from flask import Blueprint, request
from flask_jwt_extended import current_user

from app.extensions import db
from app.models import Prescription, PrescriptionImage, User, Role, PrescriptionStatus, AccountStatus
from app.utils.responses import ok, fail
from app.utils.decorators import active_required, receptionist_or_radiographer_required, admin_or_receptionist_required
from app.utils.upload import save_prescription_image, delete_file_if_exists

from .prescriptions import prescription_response, prescription_summary

patient_prescriptions_bp = Blueprint(
    "patient_prescriptions",
    __name__,
    url_prefix="/api/patients"
)

SCAN_REQ_ID_RE = re.compile(r"^sr_\d{6}$")

def generate_next_scan_req_id() -> str:
    """
    Generates next scan request id like: sr_000001, sr_000002 ...
    Uses latest row in DB. Safe because scan_req_id is UNIQUE (retry on collision).
    """
    last = Prescription.query.order_by(Prescription.id.desc()).first()
    if not last or not last.scan_req_id:
        return "sr_000001"

    # if older values exist but format not matching, still fallback
    m = re.match(r"^sr_(\d{6})$", last.scan_req_id)
    if not m:
        return "sr_000001"

    n = int(m.group(1)) + 1
    return f"sr_{n:06d}"

# -------------------------
# LIST UNDER PATIENT
# -------------------------
@patient_prescriptions_bp.get("/<int:patient_id>/prescriptions")
@active_required
def list_patient_prescriptions(patient_id: int):

    patient = User.query.get(patient_id)
    if not patient or patient.role != Role.PATIENT.value:
        return fail("Patient not found.", code=404)

    if current_user.role in {Role.RECEPTIONIST.value, Role.RADIOGRAPHER.value}:
        items = Prescription.query.filter_by(patient_id=patient_id)\
            .order_by(Prescription.id.desc()).all()

        return ok([prescription_summary(p) for p in items],
                  "Patient prescriptions list")

    if current_user.role == Role.PATIENT.value:
        if current_user.id != patient_id:
            return fail("Access denied.", code=403)

        items = Prescription.query.filter_by(patient_id=current_user.id)\
            .order_by(Prescription.id.desc()).all()

        return ok([prescription_summary(p) for p in items],
                  "My prescriptions list")

    return fail("Access denied.", code=403)

# -------------------------
# CREATE UNDER PATIENT
# -------------------------
@patient_prescriptions_bp.post("/<int:patient_id>/prescriptions")
@receptionist_or_radiographer_required
def create_patient_prescription(patient_id: int):

    form = request.form

    scan_type = (form.get("scan_type") or "").strip()
    organ = (form.get("organ") or "").strip()

    if not scan_type or not organ:
        return fail("scan_type and organ are required.", code=400)

    patient = User.query.get(patient_id)
    if not patient or patient.role != Role.PATIENT.value:
        return fail("Invalid patient.", code=400)

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

    files = request.files.getlist("prescription_images")
    saved_paths = []

    for _ in range(5):
        scan_req_id = generate_next_scan_req_id()

        p = Prescription(
            scan_req_id=scan_req_id,
            doctor_id=doctor_id_int,
            patient_id=patient_id,
            scan_type=scan_type,
            organ=organ,
            description=description,
            status=PrescriptionStatus.PENDING.value,
            created_by_id=current_user.id
        )

        try:
            db.session.add(p)
            db.session.flush()

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
            return ok(prescription_response(p), "Prescription created", 201)

        except IntegrityError:
            db.session.rollback()
            continue

        except ValueError as e:
            db.session.rollback()
            for path in saved_paths:
                delete_file_if_exists(path)
            return fail(str(e), code=400)

        except Exception:
            db.session.rollback()
            for path in saved_paths:
                delete_file_if_exists(path)
            return fail("Failed to create prescription.", code=500)

    return fail("Failed to generate unique scan_req_id. Try again.", code=500)

# -------------------------
# ACTIVE DOCTORS LIST (dropdown)
# access: admin + receptionist
# -------------------------
@patient_prescriptions_bp.get("/doctors/active")
@admin_or_receptionist_required
def list_active_doctors_dropdown():
    doctors = User.query.filter(
        User.role == Role.DOCTOR.value,
        User.status == AccountStatus.ACTIVE.value
    ).order_by(User.name.asc()).all()

    data = [
        {
            "id": d.id,
            "name": d.name,
            "license_number": d.license_number
        }
        for d in doctors
    ]

    return ok(data, "Active doctors list")
