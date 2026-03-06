import os
import uuid
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_prescription_image(file_storage, base_upload_folder: str) -> str:
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        raise ValueError("No file name.")
    if not allowed_file(filename):
        raise ValueError("Invalid file type. Allowed: png, jpg, jpeg, webp.")

    ext = filename.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"

    folder = os.path.join(base_upload_folder, "prescriptions")
    os.makedirs(folder, exist_ok=True)

    abs_path = os.path.join(folder, new_name)
    file_storage.save(abs_path)

    return os.path.join(base_upload_folder, "prescriptions", new_name).replace("\\", "/")

def delete_file_if_exists(file_path: str):
    if not file_path:
        return
    abs_path = os.path.join(os.getcwd(), file_path)
    if os.path.exists(abs_path):
        try:
            os.remove(abs_path)
        except Exception:
            pass  # optional: log

def save_scanned_image(file_storage, base_upload_folder: str) -> str:
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        raise ValueError("No file name.")

    if not allowed_file(filename):
        raise ValueError("Invalid file type. Allowed: png, jpg, jpeg, webp.")

    ext = filename.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"

    folder = os.path.join(base_upload_folder, "scanned_images")
    os.makedirs(folder, exist_ok=True)

    abs_path = os.path.join(folder, new_name)
    file_storage.save(abs_path)

    return os.path.join(base_upload_folder, "scanned_images", new_name).replace("\\", "/")