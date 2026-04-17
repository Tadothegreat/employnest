from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def create_admin():
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(email='admin@employnest.com').first()
        
        if not admin:
            admin = User(
                name='System Admin',
                email='admin@employnest.com',
                password=generate_password_hash('Admin@2026'),
                role='admin',
                verified=True
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin account created!")
            print("   Email: admin@employnest.com")
            print("   Password: Admin@2026")
        else:
            print("ℹ️ Admin account already exists.")

if __name__ == "__main__":
    create_admin()