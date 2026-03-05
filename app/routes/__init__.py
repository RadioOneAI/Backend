from .auth_routes import auth_bp
from .admin_routes import admin_bp
from .profile_routes import profile_bp
from .patient_routes import patients_bp
from .prescriptions import prescriptions_bp
from .patient_prescriptions import patient_prescriptions_bp

def register_routes(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(prescriptions_bp)
    app.register_blueprint(patient_prescriptions_bp)