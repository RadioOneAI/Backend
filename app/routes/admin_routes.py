from sqlalchemy.exc import IntegrityError
from flask import Blueprint, request

from app.extensions import db
from app.models import User, Role, AccountStatus
from app.utils.responses import ok, fail
from app.utils.decorators import admin_required
from app.utils.validators import (
    normalize_role, is_valid_role, staff_roles_only, require_license_for_role
)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ---------------------------
# Admin CRUD (admins only)
# ---------------------------

@admin_bp.get("/admins")
@admin_required
def list_admins():
    admins = User.query.filter_by(role=Role.ADMIN.value).order_by(User.id.desc()).all()
    return ok([a.to_dict() for a in admins], "Admins list")

@admin_bp.post("/admins")
@admin_required
def create_admin():
    data = request.get_json() or {}

    required = ["name", "username", "email", "phone", "password"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return fail("Missing fields", missing, 400)

    u = User(
        name=data["name"].strip(),
        role=Role.ADMIN.value,
        username=data["username"].strip(),
        email=data["email"].strip(),
        phone=data["phone"].strip(),
        address=(data.get("address") or "").strip(),
        status=data.get("status") or AccountStatus.ACTIVE.value,
    )
    u.set_password(data["password"])

    try:
        db.session.add(u)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return fail("username/email/phone already exists.", code=409)

    return ok(u.to_dict(), "Admin created", 201)

@admin_bp.patch("/admins/<int:admin_id>")
@admin_required
def update_admin(admin_id: int):
    admin = User.query.filter_by(id=admin_id, role=Role.ADMIN.value).first()
    if not admin:
        return fail("Admin not found.", code=404)

    data = request.get_json() or {}

    # ❌ role not editable
    if "role" in data:
        return fail("role cannot be updated.", code=400)

    # ✅ allow updating admin details
    if "name" in data and data["name"]:
        admin.name = data["name"].strip()
    if "username" in data and data["username"]:
        admin.username = data["username"].strip()
    if "email" in data and data["email"]:
        admin.email = data["email"].strip()
    if "phone" in data and data["phone"]:
        admin.phone = data["phone"].strip()
    if "address" in data:
        admin.address = (data.get("address") or "").strip()

    # allow admin status update (optional but practical)
    if "status" in data and data["status"] in {AccountStatus.ACTIVE.value, AccountStatus.INACTIVE.value}:
        admin.status = data["status"]

    if "password" in data and data["password"]:
        admin.set_password(data["password"])

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return fail("username/email/phone already exists.", code=409)
    except ValueError as e:
        db.session.rollback()
        return fail(str(e), code=400)

    return ok(admin.to_dict(), "Admin updated")

@admin_bp.delete("/admins/<int:admin_id>")
@admin_required
def delete_admin(admin_id: int):
    admin = User.query.filter_by(id=admin_id, role=Role.ADMIN.value).first()
    if not admin:
        return fail("Admin not found.", code=404)

    db.session.delete(admin)
    db.session.commit()
    return ok(None, "Admin deleted")


# ---------------------------
# Staff management
# ---------------------------

@admin_bp.get("/staff")
@admin_required
def list_staff():
    role = request.args.get("role")
    q = User.query.filter(User.role != Role.ADMIN.value)

    if role:
        role = normalize_role(role)
        if not is_valid_role(role) or role == Role.ADMIN.value:
            return fail("Invalid staff role filter.", code=400)
        q = q.filter(User.role == role)

    staff = q.order_by(User.id.desc()).all()
    return ok([s.to_dict() for s in staff], "Staff list")

@admin_bp.post("/staff")
@admin_required
def create_staff():
    data = request.get_json() or {}

    required = ["name", "role", "username", "email", "phone", "password"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return fail("Missing fields", missing, 400)

    role = normalize_role(data["role"])
    if not staff_roles_only(role):
        return fail("role must be receptionist/doctor/radiographer/radiologist.", code=400)

    license_number = (data.get("license_number") or "").strip() or None
    ok_lic, err = require_license_for_role(role, license_number)
    if not ok_lic:
        return fail(err, code=400)

    u = User(
        name=data["name"].strip(),
        role=role,
        username=data["username"].strip(),
        email=data["email"].strip(),
        phone=data["phone"].strip(),
        license_number=license_number,
        address=(data.get("address") or "").strip(),
        status=AccountStatus.ACTIVE.value,
    )
    u.set_password(data["password"])

    try:
        db.session.add(u)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return fail("username/email/phone/license_number already exists.", code=409)

    return ok(u.to_dict(), "Staff created", 201)

@admin_bp.patch("/staff/<int:user_id>/status")
@admin_required
def update_staff_status(user_id: int):
    staff = User.query.filter(User.id == user_id, User.role != Role.ADMIN.value).first()
    if not staff:
        return fail("Staff member not found.", code=404)

    data = request.get_json() or {}
    new_status = data.get("status")

    if new_status not in {AccountStatus.ACTIVE.value, AccountStatus.INACTIVE.value}:
        return fail("status must be active or inactive.", code=400)

    staff.status = new_status
    db.session.commit()
    return ok(staff.to_dict(), "Staff status updated")

@admin_bp.delete("/staff/<int:user_id>")
@admin_required
def delete_staff(user_id: int):
    staff = User.query.filter(User.id == user_id, User.role != Role.ADMIN.value).first()
    if not staff:
        return fail("Staff member not found.", code=404)

    db.session.delete(staff)
    db.session.commit()
    return ok(None, "Staff deleted")
