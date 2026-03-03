# app/routes/patients.py
from sqlalchemy.exc import IntegrityError
from flask import Blueprint, request
from flask_jwt_extended import current_user

from app.extensions import db
from app.models import User, Role, AccountStatus
from app.utils.responses import ok, fail
from app.utils.decorators import admin_required, admin_or_receptionist_required

patients_bp = Blueprint("patients", __name__, url_prefix="/api/patients")


def patient_response(patient: User):
    creator = patient.created_by  # User or None

    return {
        "id": patient.id,
        "name": patient.name,
        "role": patient.role,
        "username": patient.username,
        "email": patient.email,
        "phone": patient.phone,
        "address": patient.address,
        "status": patient.status,
        "created_at": patient.created_at.isoformat(),
        "updated_at": patient.updated_at.isoformat(),

        # ✅ NEW: who registered this patient
        "registered_by": None if not creator else {
            "id": creator.id,
            "name": creator.name,
            "role": creator.role,
            "username": creator.username,
        }
    }


@patients_bp.get("")
@admin_or_receptionist_required
def list_patients():
    patients = User.query.filter_by(role=Role.PATIENT.value).order_by(User.id.desc()).all()
    return ok([patient_response(p) for p in patients], "Patients list")


@patients_bp.get("/<int:patient_id>")
@admin_or_receptionist_required
def get_patient(patient_id: int):
    patient = User.query.filter_by(id=patient_id, role=Role.PATIENT.value).first()
    if not patient:
        return fail("Patient not found.", code=404)
    return ok(patient_response(patient), "Patient details")


@patients_bp.post("")
@admin_or_receptionist_required
def create_patient():
    data = request.get_json() or {}

    required = ["name", "username", "email", "phone", "password"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return fail("Missing fields", missing, 400)

    u = User(
        name=data["name"].strip(),
        role=Role.PATIENT.value,
        username=data["username"].strip(),
        email=data["email"].strip(),
        phone=data["phone"].strip(),
        address=(data.get("address") or "").strip(),
        status=data.get("status") or AccountStatus.ACTIVE.value,

        # ✅ store receptionist/admin who created the patient
        created_by_id=current_user.id
    )
    u.set_password(data["password"])

    try:
        db.session.add(u)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return fail("username/email/phone already exists.", code=409)

    return ok(patient_response(u), "Patient created", 201)


@patients_bp.delete("/<int:patient_id>")
@admin_required
def delete_patient(patient_id: int):
    patient = User.query.filter_by(id=patient_id, role=Role.PATIENT.value).first()
    if not patient:
        return fail("Patient not found.", code=404)

    db.session.delete(patient)
    db.session.commit()
    return ok(None, "Patient deleted")