from app.models import Role, LICENSE_REQUIRED_ROLES

def normalize_role(role: str) -> str:
    if not role:
        return ""
    return role.strip().lower()

def is_valid_role(role: str) -> bool:
    return normalize_role(role) in {r.value for r in Role}

def require_license_for_role(role: str, license_number: str):
    role_norm = normalize_role(role)
    required = role_norm in {r.value for r in LICENSE_REQUIRED_ROLES}
    if required and not license_number:
        return False, "license_number is required for doctor/radiographer/radiologist."
    return True, None

def staff_roles_only(role: str) -> bool:
    role_norm = normalize_role(role)
    return role_norm in {
        Role.RECEPTIONIST.value,
        Role.DOCTOR.value,
        Role.RADIOGRAPHER.value,
        Role.RADIOLOGIST.value,
    }

def is_patient_role(role: str) -> bool:
    return normalize_role(role) == Role.PATIENT.value