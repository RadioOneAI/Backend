from sqlalchemy.exc import IntegrityError
from flask import Blueprint, request
from flask_jwt_extended import current_user

from app.extensions import db
from app.utils.responses import ok, fail
from app.utils.decorators import active_required

profile_bp = Blueprint("profile", __name__, url_prefix="/api")

@profile_bp.get("/me")
@active_required
def get_me():
    return ok(current_user.to_dict(), "My profile")

@profile_bp.patch("/me")
@active_required
def update_me():
    data = request.get_json() or {}

    # ❌ not allowed to change these by anyone
    if "role" in data:
        return fail("role cannot be updated.", code=400)
    if "status" in data:
        return fail("status cannot be updated by staff.", code=400)
    if "license_number" in data:
        return fail("license_number cannot be updated.", code=400)

    # ✅ allowed fields
    allowed = ["name", "username", "email", "phone", "address", "password"]
    for key in list(data.keys()):
        if key not in allowed:
            data.pop(key, None)

    if "name" in data and data["name"]:
        current_user.name = data["name"].strip()

    if "username" in data and data["username"]:
        current_user.username = data["username"].strip()

    if "email" in data and data["email"]:
        current_user.email = data["email"].strip()

    if "phone" in data and data["phone"]:
        current_user.phone = data["phone"].strip()

    if "address" in data:
        current_user.address = (data.get("address") or "").strip()

    if "password" in data and data["password"]:
        current_user.set_password(data["password"])

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return fail("username/email/phone already exists.", code=409)
    except ValueError as e:
        db.session.rollback()
        return fail(str(e), code=400)

    return ok(current_user.to_dict(), "Profile updated")
