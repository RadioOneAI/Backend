import os
from flask import Blueprint, request, send_file
from flask_jwt_extended import current_user

from app.extensions import db
from app.models import (
    Prescription,
    PrescriptionStatus,
    ScannedImage,
    ScanImageStatus,
    Role,
    User,
)
from app.utils.responses import ok, fail
from app.utils.decorators import radiographer_required, active_required
from app.utils.upload import save_scanned_image, delete_file_if_exists

scan_images_bp = Blueprint("scan_images", __name__, url_prefix="/api/prescriptions")


def scanned_image_url(item: ScannedImage):
    return f"/api/prescriptions/{item.prescription_id}/scanned-images/{item.id}/file"


def scanned_image_response(item: ScannedImage):
    radiographer = User.query.get(item.radiographer_id) if item.radiographer_id else None

    return {
        "id": item.id,
        "prescription_id": item.prescription_id,
        "scan_req_id": item.scan_req_id,
        "radiographer_id": item.radiographer_id,
        "radiographer": None if not radiographer else {
            "id": radiographer.id,
            "name": radiographer.name,
            "role": radiographer.role,
            "username": radiographer.username,
        },
        "file_path": item.file_path,
        "file_url": scanned_image_url(item),
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }

def can_view_scanned_images(prescription: Prescription) -> bool:
    if current_user.role in {Role.RADIOGRAPHER.value, Role.RADIOLOGIST.value}:
        return True

    if current_user.role == Role.DOCTOR.value and prescription.doctor_id == current_user.id:
        return True

    if current_user.role == Role.PATIENT.value and prescription.patient_id == current_user.id:
        return True

    return False

@scan_images_bp.get("/<int:prescription_id>/scanned-images")
@active_required
def list_scanned_images(prescription_id: int):
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return fail("Prescription not found.", code=404)

    if not can_view_scanned_images(prescription):
        return fail("Access denied.", code=403)

    items = ScannedImage.query.filter_by(prescription_id=prescription_id)\
        .order_by(ScannedImage.id.desc()).all()

    return ok([scanned_image_response(i) for i in items], "Scanned images list")

@scan_images_bp.get("/<int:prescription_id>/scanned-images/<int:image_id>")
@active_required
def get_scanned_image(prescription_id: int, image_id: int):
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return fail("Prescription not found.", code=404)

    if not can_view_scanned_images(prescription):
        return fail("Access denied.", code=403)

    item = ScannedImage.query.filter_by(
        id=image_id,
        prescription_id=prescription_id
    ).first()

    if not item:
        return fail("Scanned image not found.", code=404)

    return ok(scanned_image_response(item), "Scanned image details")

@scan_images_bp.get("/<int:prescription_id>/scanned-images/<int:image_id>/file")
@active_required
def get_scanned_image_file(prescription_id: int, image_id: int):
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return fail("Prescription not found.", code=404)

    if not can_view_scanned_images(prescription):
        return fail("Access denied.", code=403)

    item = ScannedImage.query.filter_by(
        id=image_id,
        prescription_id=prescription_id
    ).first()

    if not item:
        return fail("Scanned image not found.", code=404)

    abs_path = os.path.join(os.getcwd(), item.file_path)
    if not os.path.exists(abs_path):
        return fail("Image file missing on server.", code=404)

    return send_file(abs_path)

@scan_images_bp.post("/<int:prescription_id>/scanned-images")
@radiographer_required
def upload_scanned_images(prescription_id: int):
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return fail("Prescription not found.", code=404)

    files = request.files.getlist("scanned_images")
    if not files:
        return fail("scanned_images files are required.", code=400)

    saved_paths = []
    created_items = []

    try:
        for f in files:
            if not f or not f.filename:
                continue

            path = save_scanned_image(f, "uploads")
            saved_paths.append(path)

            item = ScannedImage(
                prescription_id=prescription.id,
                scan_req_id=prescription.scan_req_id,
                radiographer_id=current_user.id,
                file_path=path,
                status=ScanImageStatus.PENDING.value,
            )
            db.session.add(item)
            created_items.append(item)

        if not created_items:
            return fail("No valid files uploaded.", code=400)

        # update prescription status to scanned
        prescription.status = PrescriptionStatus.SCANNED.value

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
        return fail("Failed to upload scanned images.", code=500)

    return ok([scanned_image_response(i) for i in created_items], "Scanned images uploaded", 201)

@scan_images_bp.patch("/<int:prescription_id>/scanned-images/<int:image_id>")
@radiographer_required
def update_scanned_image(prescription_id: int, image_id: int):
    item = ScannedImage.query.filter_by(
        id=image_id,
        prescription_id=prescription_id
    ).first()

    if not item:
        return fail("Scanned image not found.", code=404)

    file = request.files.get("scanned_image")
    if not file or not file.filename:
        return fail("scanned_image file is required.", code=400)

    old_path = item.file_path

    try:
        new_path = save_scanned_image(file, "uploads")

        item.file_path = new_path
        item.radiographer_id = current_user.id

        db.session.commit()

        delete_file_if_exists(old_path)

    except ValueError as e:
        db.session.rollback()
        return fail(str(e), code=400)

    except Exception:
        db.session.rollback()
        return fail("Failed to update scanned image.", code=500)

    return ok(scanned_image_response(item), "Scanned image updated")

@scan_images_bp.delete("/<int:prescription_id>/scanned-images/<int:image_id>")
@radiographer_required
def delete_scanned_image(prescription_id: int, image_id: int):
    item = ScannedImage.query.filter_by(
        id=image_id,
        prescription_id=prescription_id
    ).first()

    if not item:
        return fail("Scanned image not found.", code=404)

    path = item.file_path

    db.session.delete(item)
    db.session.commit()

    delete_file_if_exists(path)

    return ok(None, "Scanned image deleted")

