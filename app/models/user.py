from datetime import datetime
from enum import Enum

from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import event
from sqlalchemy.orm.attributes import get_history
from sqlalchemy.orm import relationship

from app.extensions import db


class Role(str, Enum):
    ADMIN = "admin"
    RECEPTIONIST = "receptionist"
    DOCTOR = "doctor"
    RADIOGRAPHER = "radiographer"
    RADIOLOGIST = "radiologist"
    PATIENT = "patient"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


LICENSE_REQUIRED_ROLES = {Role.DOCTOR, Role.RADIOGRAPHER, Role.RADIOLOGIST}


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(30), nullable=False)  # store Role.value

    username = db.Column(db.String(60), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(30), unique=True, nullable=False)

    license_number = db.Column(db.String(80), unique=True, nullable=True)
    address = db.Column(db.String(255), nullable=True)

    password_hash = db.Column(db.String(255), nullable=False)

    status = db.Column(db.String(20), nullable=False, default=AccountStatus.ACTIVE.value)

    # ✅ NEW: track who created this user (admin/receptionist)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by = relationship("User", remote_side=[id], lazy="joined")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value

    def is_patient(self) -> bool:
        return self.role == Role.PATIENT.value

    def to_dict(self):
        # default dict (unchanged)
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "username": self.username,
            "email": self.email,
            "phone": self.phone,
            "license_number": self.license_number,
            "address": self.address,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@event.listens_for(User, "before_update")
def prevent_role_or_license_edit(mapper, connection, target: User):
    # role cannot change
    role_hist = get_history(target, "role")
    if role_hist.has_changes():
        raise ValueError("Role cannot be updated.")

    # license cannot change once set
    lic_hist = get_history(target, "license_number")
    if lic_hist.has_changes():
        old = lic_hist.deleted[0] if lic_hist.deleted else None
        new = lic_hist.added[0] if lic_hist.added else None
        if old is not None and new != old:
            raise ValueError("License/registration number cannot be updated.")