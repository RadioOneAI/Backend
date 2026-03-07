from .auth_routes import auth_bp
from .admin_routes import admin_bp
from .profile_routes import profile_bp
from .patient_routes import patients_bp
from .prescriptions import prescriptions_bp
from app.routes.scan_images import scan_images_bp
from app.routes.reports import reports_bp
from app.routes.notice_routes import notices_bp

def register_routes(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(prescriptions_bp)
    app.register_blueprint(scan_images_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(notices_bp)