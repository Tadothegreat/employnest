from ai.ai_matcher import get_job_recommendations, get_top_candidates, get_skill_recommendations, matcher
from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from extensions import db
from models import User, Job, Application
from datetime import datetime, timedelta
from functools import wraps
from itsdangerous import URLSafeTimedSerializer
import resend
import re
import os
import random
import urllib.parse

app = Flask(__name__)

# ========== RESEND EMAIL CONFIGURATION ==========
resend.api_key = os.environ.get("RESEND_API_KEY", "")

# ========== DATABASE CONFIGURATION ==========
database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')

# Parse and fix Aiven MySQL connection
if database_url and 'mysql' in database_url:
    if database_url.startswith('mysql://'):
        database_url = database_url.replace('mysql://', 'mysql+pymysql://')
    
    connect_args = {
        'ssl': {
            'ssl_mode': 'REQUIRED'
        }
    }
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': connect_args}
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')
app.config['SECURITY_PASSWORD_SALT'] = 'employnest-password-reset-salt'

def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])

def verify_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
        return email
    except:
        return None

def generate_verification_code():
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])

def send_verification_email(email, code):
    try:
        api_key = os.environ.get("RESEND_API_KEY", "")
        if api_key and api_key != "":
            params = {
                "from": "EmployNest <noreply@employnest.onrender.com>",
                "to": [email],
                "subject": "EmployNest - Email Verification Code",
                "html": f"""
                    <h2>Welcome to EmployNest! 🐦</h2>
                    <p>Thank you for registering!</p>
                    <p>Your email verification code is:</p>
                    <h1 style="font-size: 32px; letter-spacing: 8px; color: #667eea;">{code}</h1>
                    <p>Please enter this code on the verification page to complete your registration.</p>
                    <p>This code expires in 24 hours.</p>
                    <p>If you did not create an account with EmployNest, please ignore this email.</p>
                    <hr>
                    <p style="color: #888;">The EmployNest Team<br>https://employnest.onrender.com</p>
                """
            }
            resend.Emails.send(params)
            print(f"✅ Verification email sent to {email}")
            return True
        else:
            print(f"[DEV MODE] No Resend API key. Verification code for {email}: {code}")
            return False
    except Exception as e:
        print(f"❌ Email failed: {e}")
        print(f"[FALLBACK] Verification code for {email}: {code}")
        return False

def send_password_reset_email(email, reset_url):
    try:
        api_key = os.environ.get("RESEND_API_KEY", "")
        if api_key and api_key != "":
            params = {
                "from": "EmployNest <noreply@employnest.onrender.com>",
                "to": [email],
                "subject": "EmployNest - Password Reset",
                "html": f"""
                    <h2>Password Reset Request</h2>
                    <p>You recently requested to reset your password for your EmployNest account.</p>
                    <p>Click the link below to reset your password:</p>
                    <a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a>
                    <p>This link expires in 1 hour.</p>
                    <p>If you did not request a password reset, please ignore this email.</p>
                    <hr>
                    <p style="color: #888;">The EmployNest Team</p>
                """
            }
            resend.Emails.send(params)
            print(f"✅ Password reset email sent to {email}")
            return True
        else:
            print(f"[DEV MODE] No Resend API key. Reset URL for {email}: {reset_url}")
            return False
    except Exception as e:
        print(f"❌ Password reset email failed: {e}")
        return False

def send_verification_sms(phone, code):
    print(f"[DEV] SMS code for {phone}: {code}")
    return True

# Upload configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
VERIFICATION_ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max file size

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('static/uploads/verification_docs', exist_ok=True)
os.makedirs('static/uploads/id_docs', exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_verification_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in VERIFICATION_ALLOWED_EXTENSIONS

# CONNECT db to app
db.init_app(app)

with app.app_context():
    try:
        db.create_all()
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"✅ Database connected! Tables: {tables}")
    except Exception as e:
        print(f"❌ Database error: {e}")
        if 'mysql' in database_url:
            print("⚠️ Falling back to SQLite...")
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
            db.create_all()

# ========== VALIDATION FUNCTIONS ==========

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_password(password):
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    allowed_pattern = r'^[a-zA-Z0-9@._-]+$'
    if not re.match(allowed_pattern, password):
        return False, "Password can only contain letters, numbers, and @ . _ -"
    return True, ""

def is_valid_name(name):
    if len(name.strip()) < 2:
        return False, "Name must be at least 2 characters long"
    if not re.match(r'^[a-zA-Z\s]+$', name):
        return False, "Name can only contain letters and spaces"
    return True, ""

# ========== DECORATOR FOR ADMIN PROTECTION ==========

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        if session.get("role") != "admin":
            return "Access denied. Admin only. <a href='/dashboard'>Go to Dashboard</a>"
        return f(*args, **kwargs)
    return decorated_function

# ========== SETUP ROUTE ==========
@app.route("/setup-admin")
def setup_admin():
    from models import User
    from werkzeug.security import generate_password_hash
    
    admin = User.query.filter_by(email='admin@employnest.com').first()
    if admin:
        return """
            <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                <h3>ℹ️ Admin Account Already Exists</h3>
                <p>The admin account is already set up.</p>
                <p><a href='/login'>← Go to Login</a></p>
            </div>
        """
    
    admin = User(
        name='System Admin',
        email='admin@employnest.com',
        password=generate_password_hash('Admin@2026'),
        role='admin',
        verified=True,
        email_verified=True,
        phone_verified=True
    )
    db.session.add(admin)
    db.session.commit()
    
    return """
        <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
            <h3>✅ Admin Account Created!</h3>
            <p><strong>Email:</strong> admin@employnest.com</p>
            <p><strong>Password:</strong> Admin@2026</p>
            <p style='color: #dc3545; margin-top: 20px;'>⚠️ Please change this password after your first login!</p>
            <p><a href='/login'>← Go to Login</a></p>
        </div>
    """

# ========== DATABASE SETUP ROUTE ==========
@app.route("/db-setup")
def db_setup():
    from sqlalchemy import inspect
    from sqlalchemy.exc import OperationalError
    
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    if not tables:
        db.create_all()
        tables = inspector.get_table_names()
        return f"""
            <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                <h3>✅ Database Tables Created!</h3>
                <p>Tables: {tables}</p>
                <p><a href='/setup-admin'>→ Create Admin Account</a></p>
                <p><a href='/'>→ Go to Home</a></p>
            </div>
        """
    
    try:
        User.query.with_entities(User.first_name).first()
        User.query.with_entities(User.seeker_verified).first()
        return f"""
            <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                <h3>✅ Database is Up to Date!</h3>
                <p>Tables: {tables}</p>
                <p>All required columns are present.</p>
                <p><a href='/'>→ Go to Home</a></p>
            </div>
        """
    except OperationalError:
        db.drop_all()
        db.create_all()
        tables = inspector.get_table_names()
        return f"""
            <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                <h3>✅ Database Updated with New Columns!</h3>
                <p>Tables: {tables}</p>
                <p style='color: #dc3545;'>⚠️ Note: Existing data was cleared due to schema changes.</p>
                <p><a href='/setup-admin'>→ Create Admin Account</a></p>
                <p><a href='/'>→ Go to Home</a></p>
            </div>
        """

# ========== AUTH ROUTES ==========

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        phone_number = request.form.get("phone_number", "").strip()

        errors = []
        
        if not name:
            errors.append("Name is required")
        else:
            valid, msg = is_valid_name(name)
            if not valid:
                errors.append(msg)
        
        if not email:
            errors.append("Email is required")
        elif not is_valid_email(email):
            errors.append("Please enter a valid email address")
        
        if not password:
            errors.append("Password is required")
        else:
            valid, msg = is_valid_password(password)
            if not valid:
                errors.append(msg)
        
        if role not in ['job_seeker', 'employer']:
            errors.append("Please select a valid role")
        
        if phone_number and not re.match(r'^\+?[0-9\s\-]{8,20}$', phone_number):
            errors.append("Please enter a valid phone number")

        if errors:
            error_html = "<h3>Please fix the following errors:</h3><ul>"
            for error in errors:
                error_html += f"<li>{error}</li>"
            error_html += '</ul><a href="/register">Go Back</a>'
            return error_html

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return "Email already registered. Please use another one. <a href='/register'>Go Back</a>"

        email_code = generate_verification_code()
        phone_code = generate_verification_code() if phone_number else None
        expiry = datetime.utcnow() + timedelta(hours=24)

        hashed_password = generate_password_hash(password)
        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            role=role,
            phone_number=phone_number if phone_number else None,
            email_verification_code=email_code,
            phone_verification_code=phone_code,
            verification_code_expiry=expiry,
            email_verified=False,
            phone_verified=False
        )

        db.session.add(new_user)
        db.session.commit()
        
        email_sent = False
        try:
            email_sent = send_verification_email(email, email_code)
        except Exception as e:
            print(f"⚠️ Email error but registration continues: {e}")
        
        if phone_number:
            send_verification_sms(phone_number, phone_code)
        
        session["pending_user_id"] = new_user.id
        
        if not email_sent:
            return redirect(f"/verify-account?show_code={email_code}")
        
        return redirect("/verify-account")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return "Email and password are required. <a href='/login'>Go Back</a>"

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["role"] = user.role
            session["name"] = user.name
            return redirect("/dashboard")
        else:
            return "Invalid email or password. <a href='/login'>Try Again</a>"

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    user = User.query.get(session["user_id"])
    if user.role == 'admin':
        return redirect("/admin")
    return render_template("dashboard.html", user=user)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ========== ACCOUNT VERIFICATION ROUTES ==========

@app.route("/verify-account", methods=["GET", "POST"])
def verify_account():
    if "pending_user_id" not in session:
        return redirect("/register")
    
    user = User.query.get(session["pending_user_id"])
    if not user:
        session.pop("pending_user_id", None)
        return redirect("/register")
    
    if request.method == "POST":
        email_code = request.form.get("email_code", "").strip()
        phone_code = request.form.get("phone_code", "").strip()
        
        if user.verification_code_expiry and user.verification_code_expiry < datetime.utcnow():
            return "Verification codes have expired. <a href='/resend-verification'>Resend Codes</a>"
        
        if email_code == user.email_verification_code:
            user.email_verified = True
        
        if user.phone_number:
            if phone_code == user.phone_verification_code:
                user.phone_verified = True
        else:
            user.phone_verified = True
        
        db.session.commit()
        
        if user.email_verified and user.phone_verified:
            session.pop("pending_user_id", None)
            session["user_id"] = user.id
            session["role"] = user.role
            session["name"] = user.name
            return redirect("/dashboard?verified=1")
        else:
            return "Invalid verification codes. Please try again. <a href='/verify-account'>Go Back</a>"
    
    show_code = request.args.get('show_code', '')
    return render_template("verify_account.html", user=user, show_code=show_code)

@app.route("/resend-verification")
def resend_verification():
    if "pending_user_id" not in session:
        return redirect("/register")
    
    user = User.query.get(session["pending_user_id"])
    if not user:
        return redirect("/register")
    
    user.email_verification_code = generate_verification_code()
    if user.phone_number:
        user.phone_verification_code = generate_verification_code()
    user.verification_code_expiry = datetime.utcnow() + timedelta(hours=24)
    db.session.commit()
    
    email_sent = send_verification_email(user.email, user.email_verification_code)
    if user.phone_number:
        send_verification_sms(user.phone_number, user.phone_verification_code)
    
    if not email_sent:
        return redirect(f"/verify-account?resent=1&show_code={user.email_verification_code}")
    
    return redirect("/verify-account?resent=1")

# ========== PASSWORD RESET ROUTES ==========

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            return "Email is required. <a href='/forgot-password'>Go Back</a>"
        
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_reset_token(email)
            reset_url = url_for('reset_password', token=token, _external=True)
            email_sent = send_password_reset_email(email, reset_url)
            
            if email_sent:
                return f"""
                    <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                        <h3>📧 Password Reset Email Sent</h3>
                        <p>A password reset link has been sent to: <strong>{email}</strong></p>
                        <p>Please check your inbox and spam folder.</p>
                        <p style='color: #888; font-size: 14px;'>Link expires in 1 hour.</p>
                        <p><a href='/login'>← Back to Login</a></p>
                    </div>
                """
            else:
                return f"""
                    <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                        <h3>📧 Password Reset Link</h3>
                        <p>A password reset link has been generated for: <strong>{email}</strong></p>
                        <p>Click the link below to reset your password:</p>
                        <a href='{reset_url}' style='display: inline-block; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px;'>Reset Password</a>
                        <p style='margin-top: 20px; font-size: 12px; color: #666;'>Link expires in 1 hour.</p>
                        <p><a href='/login'>← Back to Login</a></p>
                    </div>
                """
        else:
            return """
                <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                    <h3>📧 Password Reset Requested</h3>
                    <p>If an account exists with that email, a password reset link will be sent.</p>
                    <p><a href='/login'>← Back to Login</a></p>
                </div>
            """
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    email = verify_reset_token(token)
    if not email:
        return """
            <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto; text-align: center;'>
                <h3 style='color: #dc3545;'>❌ Invalid or Expired Link</h3>
                <p>The password reset link is invalid or has expired.</p>
                <a href='/forgot-password' style='display: inline-block; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px;'>Request New Link</a>
            </div>
        """
    
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not password or not confirm_password:
            return "Both fields are required. <a href=''>Go Back</a>"
        if password != confirm_password:
            return "Passwords do not match. <a href=''>Go Back</a>"
        valid, msg = is_valid_password(password)
        if not valid:
            return f"{msg}. <a href=''>Go Back</a>"
        
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            return redirect("/login?reset=success")
    return render_template("reset_password.html", token=token)

# ========== JOB ROUTES ==========

@app.route("/jobs")
def browse_jobs():
    category = request.args.get('category', '')
    job_type = request.args.get('job_type', '')
    location = request.args.get('location', '')
    
    query = Job.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    if job_type:
        query = query.filter_by(job_type=job_type)
    if location:
        query = query.filter(Job.location.contains(location))
    
    jobs = query.order_by(Job.posted_date.desc()).all()
    
    categories = db.session.query(Job.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    job_types = db.session.query(Job.job_type).distinct().all()
    job_types = [j[0] for j in job_types if j[0]]
    
    return render_template("jobs.html", jobs=jobs, categories=categories, job_types=job_types,
                         selected_category=category, selected_type=job_type, selected_location=location)

@app.route("/job/<int:job_id>")
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    has_applied = False
    if "user_id" in session:
        existing = Application.query.filter_by(job_id=job_id, applicant_id=session["user_id"]).first()
        has_applied = existing is not None
    return render_template("job_detail.html", job=job, has_applied=has_applied)

@app.route("/post-job", methods=["GET", "POST"])
def post_job():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return "Only employers can post jobs. <a href='/dashboard'>Go to Dashboard</a>"
    
    user = User.query.get(session["user_id"])
    if not user.verified:
        return """
            <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto; text-align: center;'>
                <h3>⚠️ Verification Required</h3>
                <p>Only verified employers can post jobs. Please verify your account first.</p>
                <a href='/request-verification' class='btn btn-primary'>Request Verification</a>
                <a href='/dashboard' class='btn btn-outline'>Back to Dashboard</a>
            </div>
        """
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        company = request.form.get("company", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        requirements = request.form.get("requirements", "").strip()
        salary = request.form.get("salary", "").strip()
        job_type = request.form.get("job_type", "")
        category = request.form.get("category", "")
        
        if not all([title, company, location, description, requirements]):
            return "All fields except salary are required. <a href='/post-job'>Go Back</a>"
        
        new_job = Job(
            title=title, company=company, location=location, description=description,
            requirements=requirements, salary=salary if salary else "Negotiable",
            job_type=job_type, category=category, employer_id=session["user_id"]
        )
        db.session.add(new_job)
        db.session.commit()
        return redirect("/my-jobs")
    
    return render_template("post_job.html", user=user)

@app.route("/my-jobs")
def my_jobs():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return redirect("/dashboard")
    jobs = Job.query.filter_by(employer_id=session["user_id"]).order_by(Job.posted_date.desc()).all()
    return render_template("my_jobs.html", jobs=jobs)

@app.route("/apply/<int:job_id>", methods=["POST"])
def apply_job(job_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return "Only job seekers can apply to jobs. <a href='/jobs'>Browse Jobs</a>"
    
    user = User.query.get(session["user_id"])
    if not user.seeker_verified:
        return """
            <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto; text-align: center;'>
                <h3>⚠️ Verification Required</h3>
                <p>Only verified job seekers can apply to jobs. Please verify your identity first.</p>
                <a href='/request-seeker-verification' class='btn btn-primary'>Verify Your Identity</a>
                <a href='/jobs' class='btn btn-outline'>Back to Jobs</a>
            </div>
        """
    
    cover_letter = request.form.get("cover_letter", "").strip()
    existing = Application.query.filter_by(job_id=job_id, applicant_id=session["user_id"]).first()
    if existing:
        return "You have already applied to this job. <a href='/jobs'>Browse Jobs</a>"
    
    application = Application(job_id=job_id, applicant_id=session["user_id"], cover_letter=cover_letter)
    db.session.add(application)
    db.session.commit()
    return redirect(f"/job/{job_id}?applied=success")

@app.route("/job/<int:job_id>/applicants")
def view_applicants(job_id):
    if "user_id" not in session:
        return redirect("/login")
    job = Job.query.get_or_404(job_id)
    if job.employer_id != session["user_id"]:
        return "You don't have permission to view these applicants."
    applications = Application.query.filter_by(job_id=job_id).order_by(Application.applied_date.desc()).all()
    return render_template("applicants.html", job=job, applications=applications)

@app.route("/job/<int:job_id>/delete")
def delete_job(job_id):
    if "user_id" not in session:
        return redirect("/login")
    job = Job.query.get_or_404(job_id)
    if job.employer_id != session["user_id"]:
        return "You don't have permission to delete this job."
    Application.query.filter_by(job_id=job_id).delete()
    db.session.delete(job)
    db.session.commit()
    return redirect("/my-jobs")

@app.route("/job/<int:job_id>/toggle")
def toggle_job(job_id):
    if "user_id" not in session:
        return redirect("/login")
    job = Job.query.get_or_404(job_id)
    if job.employer_id != session["user_id"]:
        return "You don't have permission to modify this job."
    job.is_active = not job.is_active
    db.session.commit()
    return redirect("/my-jobs")

# ========== EMPLOYER VERIFICATION ROUTES ==========

@app.route("/request-verification", methods=["GET", "POST"])
def request_verification():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return redirect("/dashboard")
    
    user = User.query.get(session["user_id"])
    
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        company_registration = request.form.get("company_registration", "").strip()
        company_address = request.form.get("company_address", "").strip()
        company_phone = request.form.get("company_phone", "").strip()
        
        if not all([company_name, company_registration, company_address, company_phone]):
            return "All fields are required. <a href='/request-verification'>Go Back</a>"
        
        # Handle document uploads
        docs_folder = 'static/uploads/verification_docs'
        os.makedirs(docs_folder, exist_ok=True)
        
        # Upload registration certificate
        reg_cert_file = request.files.get('registration_cert')
        if reg_cert_file and reg_cert_file.filename and allowed_verification_file(reg_cert_file.filename):
            reg_filename = secure_filename(f"reg_cert_{user.id}_{reg_cert_file.filename}")
            reg_cert_file.save(os.path.join(docs_folder, reg_filename))
            user.registration_cert = reg_filename
        
        # Upload tax clearance
        tax_file = request.files.get('tax_clearance')
        if tax_file and tax_file.filename and allowed_verification_file(tax_file.filename):
            tax_filename = secure_filename(f"tax_{user.id}_{tax_file.filename}")
            tax_file.save(os.path.join(docs_folder, tax_filename))
            user.tax_clearance = tax_filename
        
        # Upload business license
        license_file = request.files.get('business_license')
        if license_file and license_file.filename and allowed_verification_file(license_file.filename):
            license_filename = secure_filename(f"license_{user.id}_{license_file.filename}")
            license_file.save(os.path.join(docs_folder, license_filename))
            user.business_license = license_filename
        
        user.company_name = company_name
        user.company_registration = company_registration
        user.company_address = company_address
        user.company_phone = company_phone
        user.verification_requested = True
        
        db.session.commit()
        return redirect("/dashboard?verification_requested=1")
    
    return render_template("request_verification.html", user=user)

# ========== JOB SEEKER VERIFICATION ROUTES ==========

@app.route("/request-seeker-verification", methods=["GET", "POST"])
def request_seeker_verification():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return redirect("/dashboard")
    
    user = User.query.get(session["user_id"])
    
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        surname = request.form.get("surname", "").strip()
        date_of_birth = request.form.get("date_of_birth", "")
        id_type = request.form.get("id_type", "national_id")
        national_id = request.form.get("national_id", "").strip()
        passport_number = request.form.get("passport_number", "").strip()
        gender = request.form.get("gender", "")
        religion = request.form.get("religion", "").strip()
        marital_status = request.form.get("marital_status", "")
        place_of_birth = request.form.get("place_of_birth", "").strip()
        home_address = request.form.get("home_address", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()
        
        # Validate based on ID type
        if id_type == 'national_id' and not national_id:
            return "National ID is required. <a href='/request-seeker-verification'>Go Back</a>"
        if id_type == 'passport' and not passport_number:
            return "Passport number is required. <a href='/request-seeker-verification'>Go Back</a>"
        
        if not all([first_name, surname, date_of_birth, gender, home_address]):
            return "All required fields must be filled. <a href='/request-seeker-verification'>Go Back</a>"
        
        # Handle ID document uploads
        docs_folder = 'static/uploads/id_docs'
        os.makedirs(docs_folder, exist_ok=True)
        
        # Upload front of ID
        id_front_file = request.files.get('id_front')
        if id_front_file and id_front_file.filename and allowed_verification_file(id_front_file.filename):
            front_filename = secure_filename(f"id_front_{user.id}_{id_front_file.filename}")
            id_front_file.save(os.path.join(docs_folder, front_filename))
            user.id_front_image = front_filename
        
        # Upload back of ID (for national ID only)
        id_back_file = request.files.get('id_back')
        if id_back_file and id_back_file.filename and allowed_verification_file(id_back_file.filename):
            back_filename = secure_filename(f"id_back_{user.id}_{id_back_file.filename}")
            id_back_file.save(os.path.join(docs_folder, back_filename))
            user.id_back_image = back_filename
        
        # Upload selfie with ID
        selfie_file = request.files.get('selfie_with_id')
        if selfie_file and selfie_file.filename and allowed_verification_file(selfie_file.filename):
            selfie_filename = secure_filename(f"selfie_{user.id}_{selfie_file.filename}")
            selfie_file.save(os.path.join(docs_folder, selfie_filename))
            user.selfie_with_id = selfie_filename
        
        user.first_name = first_name
        user.surname = surname
        user.date_of_birth = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
        user.id_type = id_type
        user.national_id = national_id if id_type == 'national_id' else None
        user.passport_number = passport_number if id_type == 'passport' else None
        user.gender = gender
        user.religion = religion
        user.marital_status = marital_status
        user.place_of_birth = place_of_birth
        user.home_address = home_address
        user.contact_phone = contact_phone
        user.seeker_verification_requested = True
        
        db.session.commit()
        return redirect("/dashboard?verification_requested=1")
    
    return render_template("request_seeker_verification.html", user=user)

# ========== ADMIN ROUTES ==========

@app.route("/admin/verifications")
@admin_required
def admin_verifications():
    pending_employers = User.query.filter_by(role='employer', verification_requested=True, verified=False).all()
    verified_employers = User.query.filter_by(role='employer', verified=True).all()
    return render_template("admin_verifications.html", pending=pending_employers, verified=verified_employers)

@app.route("/admin/employers")
@admin_required
def admin_all_employers():
    verified_employers = User.query.filter_by(role='employer', verified=True).all()
    unverified_employers = User.query.filter_by(role='employer', verified=False, verification_requested=False).all()
    pending_employers = User.query.filter_by(role='employer', verification_requested=True, verified=False).all()
    return render_template("admin_employers.html", verified=verified_employers, unverified=unverified_employers, pending=pending_employers)

@app.route("/admin/verify/<int:employer_id>")
@admin_required
def verify_employer(employer_id):
    employer = User.query.get_or_404(employer_id)
    if employer.role != 'employer':
        return "Invalid user type."
    employer.verified = True
    employer.verification_date = datetime.utcnow()
    employer.verified_by = session["user_id"]
    db.session.commit()
    return redirect("/admin/verifications?approved=1")

@app.route("/admin/reject/<int:employer_id>")
@admin_required
def reject_verification(employer_id):
    employer = User.query.get_or_404(employer_id)
    if employer.role != 'employer':
        return "Invalid user type."
    employer.verification_requested = False
    employer.verified = False
    db.session.commit()
    return redirect("/admin/verifications?rejected=1")

@app.route("/admin/delete-user/<int:user_id>")
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session["user_id"]:
        return "You cannot delete your own admin account. <a href='/admin/employers'>Go Back</a>"
    
    if user.role == 'employer':
        jobs = Job.query.filter_by(employer_id=user.id).all()
        for job in jobs:
            Application.query.filter_by(job_id=job.id).delete()
        Job.query.filter_by(employer_id=user.id).delete()
    
    Application.query.filter_by(applicant_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return redirect("/admin/employers?deleted=1")

@app.route("/admin/seeker-verifications")
@admin_required
def admin_seeker_verifications():
    pending_seekers = User.query.filter_by(role='job_seeker', seeker_verification_requested=True, seeker_verified=False).all()
    verified_seekers = User.query.filter_by(role='job_seeker', seeker_verified=True).all()
    return render_template("admin_seeker_verifications.html", pending=pending_seekers, verified=verified_seekers)

@app.route("/admin/verify-seeker/<int:seeker_id>")
@admin_required
def verify_seeker(seeker_id):
    seeker = User.query.get_or_404(seeker_id)
    if seeker.role != 'job_seeker':
        return "Invalid user type."
    seeker.seeker_verified = True
    seeker.seeker_verification_date = datetime.utcnow()
    seeker.seeker_verified_by = session["user_id"]
    db.session.commit()
    return redirect("/admin/seeker-verifications?approved=1")

@app.route("/admin/reject-seeker/<int:seeker_id>")
@admin_required
def reject_seeker_verification(seeker_id):
    seeker = User.query.get_or_404(seeker_id)
    if seeker.role != 'job_seeker':
        return "Invalid user type."
    seeker.seeker_verification_requested = False
    seeker.seeker_verified = False
    db.session.commit()
    return redirect("/admin/seeker-verifications?rejected=1")

@app.route("/admin")
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_employers = User.query.filter_by(role='employer').count()
    total_seekers = User.query.filter_by(role='job_seeker').count()
    total_jobs = Job.query.filter_by(is_active=True).count()
    pending_verifications = User.query.filter_by(role='employer', verification_requested=True, verified=False).count()
    verified_employers = User.query.filter_by(role='employer', verified=True).count()
    pending_seeker_verifications = User.query.filter_by(role='job_seeker', seeker_verification_requested=True, seeker_verified=False).count()
    
    return render_template("admin_dashboard.html", total_users=total_users, total_employers=total_employers,
                         total_seekers=total_seekers, total_jobs=total_jobs, pending_verifications=pending_verifications,
                         verified_employers=verified_employers, pending_seeker_verifications=pending_seeker_verifications)

# ========== PROFILE ROUTES ==========

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")
    
    user = User.query.get(session["user_id"])
    
    if request.method == "POST":
        if user.role == 'job_seeker':
            user.first_name = request.form.get("first_name", "").strip()
            user.surname = request.form.get("surname", "").strip()
            dob = request.form.get("date_of_birth", "")
            if dob:
                user.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()
            user.national_id = request.form.get("national_id", "").strip()
            user.gender = request.form.get("gender", "")
            user.religion = request.form.get("religion", "").strip()
            user.marital_status = request.form.get("marital_status", "")
            user.place_of_birth = request.form.get("place_of_birth", "").strip()
            user.home_address = request.form.get("home_address", "").strip()
            user.contact_phone = request.form.get("contact_phone", "").strip()
            
            skills = request.form.get("skills", "").strip()
            qualifications = request.form.get("qualifications", "").strip()
            experience_years = request.form.get("experience_years", "")
            user.skills = skills
            user.qualifications = qualifications
            user.experience_years = int(experience_years) if experience_years else 0
            
            if skills and qualifications:
                user.profile_complete = True
            
            if 'resume' in request.files:
                file = request.files['resume']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"resume_{user.id}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    user.resume_filename = filename
            
        elif user.role == 'employer':
            company_name = request.form.get("company_name", "").strip()
            company_phone = request.form.get("company_phone", "").strip()
            company_address = request.form.get("company_address", "").strip()
            if company_name:
                user.company_name = company_name
            if company_phone:
                user.company_phone = company_phone
            if company_address:
                user.company_address = company_address
        
        db.session.commit()
        return redirect("/profile?updated=1")
    
    return render_template("profile.html", user=user)

@app.route("/applicant/<int:applicant_id>")
def view_applicant_profile(applicant_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return redirect("/dashboard")
    applicant = User.query.get_or_404(applicant_id)
    if applicant.role != 'job_seeker':
        return "Invalid user type."
    return render_template("applicant_profile.html", applicant=applicant)

# ========== AI MATCHING ROUTES ==========

@app.route("/recommended-jobs")
def recommended_jobs():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return redirect("/dashboard")
    
    user = User.query.get(session["user_id"])
    all_jobs = Job.query.filter_by(is_active=True).all()
    
    if not user.skills or not user.skills.strip():
        return render_template("recommended_jobs.html", recommended_jobs=[], new_jobs=[], user=user, no_skills=True)
    
    recommended_job_ids = get_job_recommendations(user, all_jobs, top_n=10)
    recommended_jobs = []
    job_dict = {job.id: job for job in all_jobs}
    for job_id in recommended_job_ids:
        if job_id in job_dict:
            recommended_jobs.append(job_dict[job_id])
    
    applied_job_ids = [app.job_id for app in user.applications]
    new_jobs = [job for job in all_jobs if job.id not in applied_job_ids and job.id not in recommended_job_ids]
    
    return render_template("recommended_jobs.html", recommended_jobs=recommended_jobs, new_jobs=new_jobs[:5], user=user, no_skills=False)

@app.route("/job/<int:job_id>/rank-candidates")
def rank_candidates(job_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return redirect("/dashboard")
    
    job = Job.query.get_or_404(job_id)
    if job.employer_id != session["user_id"]:
        return "You don't have permission to view this."
    
    applications = Application.query.filter_by(job_id=job_id).all()
    candidates = [app.applicant for app in applications]
    ranked_results = get_top_candidates(job, candidates, top_n=len(candidates))
    
    ranked_applications = []
    candidate_dict = {c.id: c for c in candidates}
    app_dict = {app.applicant_id: app for app in applications}
    
    for result in ranked_results:
        candidate_id = result['candidate_id']
        if candidate_id in candidate_dict:
            ranked_applications.append({
                'applicant': candidate_dict[candidate_id],
                'application': app_dict[candidate_id],
                'match_score': result['score'],
                'text_score': result['text_score'],
                'skill_score': result['skill_score'],
                'matched_skills': result['matched_skills'],
                'missing_skills': result['missing_skills'],
                'total_required': result['total_required_skills']
            })
    
    return render_template("ranked_candidates.html", job=job, ranked_applications=ranked_applications)

@app.route("/job/<int:job_id>/skill-gap")
def skill_gap_analysis(job_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return redirect("/dashboard")
    user = User.query.get(session["user_id"])
    job = Job.query.get_or_404(job_id)
    gap_analysis = matcher.get_skill_gap_analysis(user, job)
    return render_template("skill_gap.html", job=job, user=user, analysis=gap_analysis)

@app.route("/job/<int:job_id>/blind-screening")
def blind_screening(job_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return redirect("/dashboard")
    
    job = Job.query.get_or_404(job_id)
    if job.employer_id != session["user_id"]:
        return "You don't have permission to view this."
    
    applications = Application.query.filter_by(job_id=job_id).all()
    if not applications:
        return render_template("blind_screening.html", job=job, ranked_candidates=[])
    
    candidates = [app.applicant for app in applications]
    blind_scores = []
    for candidate in candidates:
        try:
            score = matcher.get_blind_screening_score(candidate, job)
        except Exception as e:
            print(f"Error scoring candidate {candidate.id}: {e}")
            score = 0.0
        app = next((a for a in applications if a.applicant_id == candidate.id), None)
        if app:
            blind_scores.append({'candidate': candidate, 'application': app, 'blind_score': score})
    
    blind_scores.sort(key=lambda x: x['blind_score'], reverse=True)
    return render_template("blind_screening.html", job=job, ranked_candidates=blind_scores)

@app.route("/job-trends")
def job_trends():
    if "user_id" not in session:
        return redirect("/login")
    
    categories = db.session.query(Job.category, db.func.count(Job.id)).filter_by(is_active=True).group_by(Job.category).all()
    locations = db.session.query(Job.location, db.func.count(Job.id)).filter_by(is_active=True).group_by(Job.location).all()
    job_types = db.session.query(Job.job_type, db.func.count(Job.id)).filter_by(is_active=True).group_by(Job.job_type).all()
    total_jobs = Job.query.filter_by(is_active=True).count()
    recommended_skills = get_skill_recommendations("", Job.query.filter_by(is_active=True).all(), top_n=10)
    
    return render_template("job_trends.html", categories=categories, locations=locations, job_types=job_types,
                         total_jobs=total_jobs, recommended_skills=recommended_skills)

@app.route("/api/skill-suggestions")
def skill_suggestions():
    if "user_id" not in session:
        return {"suggestions": []}
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return {"suggestions": []}
    suggestions = matcher.suggest_skills(query, limit=8)
    return {"suggestions": suggestions}

@app.route("/skill-recommendations")
def skill_recommendations():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return redirect("/dashboard")
    user = User.query.get(session["user_id"])
    all_jobs = Job.query.filter_by(is_active=True).all()
    recommended_skills = get_skill_recommendations(user.skills, all_jobs, top_n=10)
    return render_template("skill_recommendations.html", user=user, recommended_skills=recommended_skills)

if __name__ == "__main__":
    app.run(debug=True)