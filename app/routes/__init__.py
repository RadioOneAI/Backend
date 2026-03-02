from .auth_routes import auth_bp
from .admin_routes import admin_bp
from .profile_routes import profile_bp
from .patient_routes import patients_bp

def register_routes(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(patients_bp)