from ai.matcher import get_job_recommendations, get_top_candidates, get_skill_recommendations, matcher
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from extensions import db
from models import User, Job, Application
from datetime import datetime, timedelta
from functools import wraps
from itsdangerous import URLSafeTimedSerializer
import re
import os
import random
import urllib.parse

app = Flask(__name__)

# ========== DATABASE CONFIGURATION ==========
database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')

# Parse and fix Aiven MySQL connection
if database_url and 'mysql' in database_url:
    # Ensure we use pymysql driver
    if database_url.startswith('mysql://'):
        database_url = database_url.replace('mysql://', 'mysql+pymysql://')
    
    # Add SSL parameters for Aiven
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

# Password Reset Configuration
app.config['SECURITY_PASSWORD_SALT'] = 'employnest-password-reset-salt'

def generate_reset_token(email):
    """Generate a password reset token valid for 1 hour"""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])

def verify_reset_token(token, expiration=3600):
    """Verify a password reset token (default 1 hour expiry)"""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
        return email
    except:
        return None

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])

def send_verification_email(email, code):
    """Simulate sending verification email"""
    print(f"[DEV] Verification code for {email}: {code}")
    return True

def send_verification_sms(phone, code):
    """Simulate sending verification SMS"""
    print(f"[DEV] SMS code for {phone}: {code}")
    return True

# Upload configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# CONNECT db to app
db.init_app(app)

# Create tables on startup
with app.app_context():
    try:
        db.create_all()
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"✅ Database connected! Tables: {tables}")
    except Exception as e:
        print(f"❌ Database error: {e}")
        # Fall back to SQLite if MySQL fails
        if 'mysql' in database_url:
            print("⚠️ Falling back to SQLite...")
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
            db.create_all()

# ========== VALIDATION FUNCTIONS ==========

def is_valid_email(email):
    """Check if email format is valid"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def is_valid_password(password):
    """Check password requirements:
    - At least 6 characters
    - Only letters, numbers, and allowed symbols (@._-)
    """
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    
    # Allow only alphanumeric and @._-
    allowed_pattern = r'^[a-zA-Z0-9@._-]+$'
    if not re.match(allowed_pattern, password):
        return False, "Password can only contain letters, numbers, and @ . _ -"
    
    return True, ""


def is_valid_name(name):
    """Check if name is valid (letters and spaces only)"""
    if len(name.strip()) < 2:
        return False, "Name must be at least 2 characters long"
    
    # Allow letters and spaces only
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


# ========== SETUP ROUTE (SAFE TO KEEP PERMANENTLY) ==========
@app.route("/setup-admin")
def setup_admin():
    """Create admin account if it doesn't exist. Safe to run multiple times."""
    from models import User
    from werkzeug.security import generate_password_hash
    
    # Check if admin already exists
    admin = User.query.filter_by(email='admin@employnest.com').first()
    
    if admin:
        return """
            <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                <h3>ℹ️ Admin Account Already Exists</h3>
                <p>The admin account is already set up.</p>
                <p><a href='/login'>← Go to Login</a></p>
            </div>
        """
    
    # Create admin if not exists
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


# ========== DATABASE SETUP ROUTE (SAFE TO KEEP PERMANENTLY) ==========
@app.route("/db-setup")
def db_setup():
    """
    Check if database needs migration. Safe to run anytime.
    Only creates missing tables/columns, never drops data unnecessarily.
    """
    from sqlalchemy import inspect
    from sqlalchemy.exc import OperationalError
    
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    # Check if we need to create tables (if none exist)
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
    
    # Check for missing columns in user table
    try:
        # Try to query new columns - if they don't exist, recreate tables
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
        # Missing columns - need to recreate
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

# Home
@app.route("/")
def home():
    return render_template("index.html")


# Register
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        phone_number = request.form.get("phone_number", "").strip()

        # Validation checks
        errors = []
        
        # Check for empty fields
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

        # If validation fails, return error messages
        if errors:
            error_html = "<h3>Please fix the following errors:</h3><ul>"
            for error in errors:
                error_html += f"<li>{error}</li>"
            error_html += '</ul><a href="/register">Go Back</a>'
            return error_html

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return "Email already registered. Please use another one. <a href='/register'>Go Back</a>"

        # Generate verification codes
        email_code = generate_verification_code()
        phone_code = generate_verification_code() if phone_number else None
        expiry = datetime.utcnow() + timedelta(hours=24)

        # Create new user with hashed password
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
        
        # Send verification codes
        send_verification_email(email, email_code)
        if phone_number:
            send_verification_sms(phone_number, phone_code)
        
        # Store user_id in session for verification
        session["pending_user_id"] = new_user.id
        
        return redirect("/verify-account")

    return render_template("register.html")


# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Basic validation
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


# Dashboard (Protected)
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    
    user = User.query.get(session["user_id"])
    
    # Admin goes to admin panel
    if user.role == 'admin':
        return redirect("/admin")
    
    return render_template("dashboard.html", user=user)


# Logout
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
        
        # Check expiry
        if user.verification_code_expiry and user.verification_code_expiry < datetime.utcnow():
            return "Verification codes have expired. <a href='/resend-verification'>Resend Codes</a>"
        
        # Verify email
        if email_code == user.email_verification_code:
            user.email_verified = True
        
        # Verify phone (if provided)
        if user.phone_number:
            if phone_code == user.phone_verification_code:
                user.phone_verified = True
        else:
            user.phone_verified = True  # No phone provided
        
        db.session.commit()
        
        if user.email_verified and user.phone_verified:
            session.pop("pending_user_id", None)
            session["user_id"] = user.id
            session["role"] = user.role
            session["name"] = user.name
            return redirect("/dashboard?verified=1")
        else:
            return "Invalid verification codes. Please try again. <a href='/verify-account'>Go Back</a>"
    
    return render_template("verify_account.html", user=user)


@app.route("/resend-verification")
def resend_verification():
    if "pending_user_id" not in session:
        return redirect("/register")
    
    user = User.query.get(session["pending_user_id"])
    if not user:
        return redirect("/register")
    
    # Generate new codes
    user.email_verification_code = generate_verification_code()
    if user.phone_number:
        user.phone_verification_code = generate_verification_code()
    user.verification_code_expiry = datetime.utcnow() + timedelta(hours=24)
    db.session.commit()
    
    # Resend codes
    send_verification_email(user.email, user.email_verification_code)
    if user.phone_number:
        send_verification_sms(user.phone_number, user.phone_verification_code)
    
    return redirect("/verify-account?resent=1")


# ========== PASSWORD RESET ROUTES ==========

# Forgot Password - Request Reset
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        
        if not email:
            return "Email is required. <a href='/forgot-password'>Go Back</a>"
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate reset token
            token = generate_reset_token(email)
            reset_url = url_for('reset_password', token=token, _external=True)
            
            # In production, send email here
            # For development, display the link
            return f"""
                <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                    <h3>📧 Password Reset Link (Development Mode)</h3>
                    <p>A password reset link has been generated for: <strong>{email}</strong></p>
                    <p>In production, this would be emailed. For now, click the link below:</p>
                    <a href='{reset_url}' style='display: inline-block; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px;'>Reset Password</a>
                    <p style='margin-top: 20px; font-size: 12px; color: #666;'>Link expires in 1 hour.</p>
                    <p><a href='/login'>← Back to Login</a></p>
                </div>
            """
        else:
            # Don't reveal if email exists or not (security)
            return """
                <div style='padding: 20px; background: white; border-radius: 10px; max-width: 500px; margin: 50px auto;'>
                    <h3>📧 Password Reset Requested</h3>
                    <p>If an account exists with that email, a password reset link will be sent.</p>
                    <p><a href='/login'>← Back to Login</a></p>
                </div>
            """
    
    return render_template("forgot_password.html")


# Reset Password - Set New Password
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
        
        # Validation
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

# Browse all jobs (accessible to everyone)
@app.route("/jobs")
def browse_jobs():
    # Get filter parameters
    category = request.args.get('category', '')
    job_type = request.args.get('job_type', '')
    location = request.args.get('location', '')
    
    # Base query - only active jobs
    query = Job.query.filter_by(is_active=True)
    
    # Apply filters if provided
    if category:
        query = query.filter_by(category=category)
    if job_type:
        query = query.filter_by(job_type=job_type)
    if location:
        query = query.filter(Job.location.contains(location))
    
    jobs = query.order_by(Job.posted_date.desc()).all()
    
    # Get unique categories and job types for filter dropdowns
    categories = db.session.query(Job.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    
    job_types = db.session.query(Job.job_type).distinct().all()
    job_types = [j[0] for j in job_types if j[0]]
    
    return render_template("jobs.html", 
                         jobs=jobs, 
                         categories=categories, 
                         job_types=job_types,
                         selected_category=category,
                         selected_type=job_type,
                         selected_location=location)


# View single job details
@app.route("/job/<int:job_id>")
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    
    # Check if current user has already applied
    has_applied = False
    if "user_id" in session:
        existing_application = Application.query.filter_by(
            job_id=job_id, 
            applicant_id=session["user_id"]
        ).first()
        has_applied = existing_application is not None
    
    return render_template("job_detail.html", job=job, has_applied=has_applied)


# Post a new job (employers only)
@app.route("/post-job", methods=["GET", "POST"])
def post_job():
    # Check if user is logged in and is an employer
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return "Only employers can post jobs. <a href='/dashboard'>Go to Dashboard</a>"
    
    user = User.query.get(session["user_id"])
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        company = request.form.get("company", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        requirements = request.form.get("requirements", "").strip()
        salary = request.form.get("salary", "").strip()
        job_type = request.form.get("job_type", "")
        category = request.form.get("category", "")
        
        # Basic validation
        if not all([title, company, location, description, requirements]):
            return "All fields except salary are required. <a href='/post-job'>Go Back</a>"
        
        # Create new job
        new_job = Job(
            title=title,
            company=company,
            location=location,
            description=description,
            requirements=requirements,
            salary=salary if salary else "Negotiable",
            job_type=job_type,
            category=category,
            employer_id=session["user_id"]
        )
        
        db.session.add(new_job)
        db.session.commit()
        
        return redirect("/my-jobs")
    
    return render_template("post_job.html", user=user)


# My Jobs (employers only - view their posted jobs)
@app.route("/my-jobs")
def my_jobs():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return redirect("/dashboard")
    
    jobs = Job.query.filter_by(employer_id=session["user_id"]).order_by(Job.posted_date.desc()).all()
    return render_template("my_jobs.html", jobs=jobs)


# Apply to a job (job seekers only)
@app.route("/apply/<int:job_id>", methods=["POST"])
def apply_job(job_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return "Only job seekers can apply to jobs. <a href='/jobs'>Browse Jobs</a>"
    
    cover_letter = request.form.get("cover_letter", "").strip()
    
    # Check if already applied
    existing = Application.query.filter_by(
        job_id=job_id,
        applicant_id=session["user_id"]
    ).first()
    
    if existing:
        return "You have already applied to this job. <a href='/jobs'>Browse Jobs</a>"
    
    # Create application
    application = Application(
        job_id=job_id,
        applicant_id=session["user_id"],
        cover_letter=cover_letter
    )
    
    db.session.add(application)
    db.session.commit()
    
    return redirect(f"/job/{job_id}?applied=success")


# View applicants for a specific job (employers only)
@app.route("/job/<int:job_id>/applicants")
def view_applicants(job_id):
    if "user_id" not in session:
        return redirect("/login")
    
    job = Job.query.get_or_404(job_id)
    
    # Check if current user owns this job
    if job.employer_id != session["user_id"]:
        return "You don't have permission to view these applicants."
    
    applications = Application.query.filter_by(job_id=job_id).order_by(Application.applied_date.desc()).all()
    return render_template("applicants.html", job=job, applications=applications)


# Delete a job (employers only)
@app.route("/job/<int:job_id>/delete")
def delete_job(job_id):
    if "user_id" not in session:
        return redirect("/login")
    
    job = Job.query.get_or_404(job_id)
    
    # Check ownership
    if job.employer_id != session["user_id"]:
        return "You don't have permission to delete this job."
    
    # Delete all applications first (due to foreign key)
    Application.query.filter_by(job_id=job_id).delete()
    db.session.delete(job)
    db.session.commit()
    
    return redirect("/my-jobs")


# Toggle job active/inactive
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

# Request verification (employers only)
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
        
        # Validation
        if not all([company_name, company_registration, company_address, company_phone]):
            return "All fields are required. <a href='/request-verification'>Go Back</a>"
        
        # Update user with company details
        user.company_name = company_name
        user.company_registration = company_registration
        user.company_address = company_address
        user.company_phone = company_phone
        user.verification_requested = True
        
        db.session.commit()
        
        return redirect("/dashboard?verification_requested=1")
    
    return render_template("request_verification.html", user=user)


# ========== JOB SEEKER VERIFICATION ROUTES ==========

# Request verification (job seekers only)
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
        national_id = request.form.get("national_id", "").strip()
        gender = request.form.get("gender", "")
        religion = request.form.get("religion", "").strip()
        marital_status = request.form.get("marital_status", "")
        place_of_birth = request.form.get("place_of_birth", "").strip()
        home_address = request.form.get("home_address", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()
        
        # Validation
        if not all([first_name, surname, date_of_birth, national_id, gender, home_address]):
            return "All required fields must be filled. <a href='/request-seeker-verification'>Go Back</a>"
        
        # Update user with personal details
        user.first_name = first_name
        user.surname = surname
        user.date_of_birth = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
        user.national_id = national_id
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

# Admin Panel - Pending Verifications
@app.route("/admin/verifications")
@admin_required
def admin_verifications():
    pending_employers = User.query.filter_by(
        role='employer', 
        verification_requested=True, 
        verified=False
    ).all()
    
    verified_employers = User.query.filter_by(
        role='employer',
        verified=True
    ).all()
    
    return render_template("admin_verifications.html", 
                         pending=pending_employers,
                         verified=verified_employers)


# Admin - View All Employers
@app.route("/admin/employers")
@admin_required
def admin_all_employers():
    # Get all employers with their verification status
    verified_employers = User.query.filter_by(role='employer', verified=True).all()
    unverified_employers = User.query.filter_by(role='employer', verified=False, verification_requested=False).all()
    pending_employers = User.query.filter_by(role='employer', verification_requested=True, verified=False).all()
    
    return render_template("admin_employers.html",
                         verified=verified_employers,
                         unverified=unverified_employers,
                         pending=pending_employers)


# Admin - Approve Employer Verification
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


# Admin - Reject Employer Verification
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


# Admin - View Pending Job Seeker Verifications
@app.route("/admin/seeker-verifications")
@admin_required
def admin_seeker_verifications():
    pending_seekers = User.query.filter_by(
        role='job_seeker',
        seeker_verification_requested=True,
        seeker_verified=False
    ).all()
    
    verified_seekers = User.query.filter_by(
        role='job_seeker',
        seeker_verified=True
    ).all()
    
    return render_template("admin_seeker_verifications.html",
                         pending=pending_seekers,
                         verified=verified_seekers)


# Admin - Approve Job Seeker Verification
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


# Admin - Reject Job Seeker Verification
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


# Admin Dashboard
@app.route("/admin")
@admin_required
def admin_dashboard():
    # Stats
    total_users = User.query.count()
    total_employers = User.query.filter_by(role='employer').count()
    total_seekers = User.query.filter_by(role='job_seeker').count()
    total_jobs = Job.query.filter_by(is_active=True).count()
    pending_verifications = User.query.filter_by(
        role='employer', 
        verification_requested=True, 
        verified=False
    ).count()
    verified_employers = User.query.filter_by(
        role='employer',
        verified=True
    ).count()
    pending_seeker_verifications = User.query.filter_by(
        role='job_seeker',
        seeker_verification_requested=True,
        seeker_verified=False
    ).count()
    
    return render_template("admin_dashboard.html",
                         total_users=total_users,
                         total_employers=total_employers,
                         total_seekers=total_seekers,
                         total_jobs=total_jobs,
                         pending_verifications=pending_verifications,
                         verified_employers=verified_employers,
                         pending_seeker_verifications=pending_seeker_verifications)


# ========== PROFILE ROUTES =
# ========== PROFILE ROUTES ==========

# View/Edit Profile
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")
    
    user = User.query.get(session["user_id"])
    
    if request.method == "POST":
        if user.role == 'job_seeker':
            # Update personal details
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
            
            # Update skills and qualifications
            skills = request.form.get("skills", "").strip()
            qualifications = request.form.get("qualifications", "").strip()
            experience_years = request.form.get("experience_years", "")
            
            user.skills = skills
            user.qualifications = qualifications
            user.experience_years = int(experience_years) if experience_years else 0
            
            # Check if profile is complete
            if skills and qualifications:
                user.profile_complete = True
            
            # Handle resume upload
            if 'resume' in request.files:
                file = request.files['resume']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"resume_{user.id}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    user.resume_filename = filename
            
        elif user.role == 'employer':
            # Update employer profile
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


# View public profile (for employers to see applicants)
@app.route("/applicant/<int:applicant_id>")
def view_applicant_profile(applicant_id):
    if "user_id" not in session:
        return redirect("/login")
    
    # Only employers can view applicant profiles
    if session.get("role") != "employer":
        return redirect("/dashboard")
    
    applicant = User.query.get_or_404(applicant_id)
    
    # Ensure the applicant is a job seeker
    if applicant.role != 'job_seeker':
        return "Invalid user type."
    
    return render_template("applicant_profile.html", applicant=applicant)


# ========== AI MATCHING ROUTES ==========

# Recommended Jobs for Job Seeker
@app.route("/recommended-jobs")
def recommended_jobs():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return redirect("/dashboard")
    
    user = User.query.get(session["user_id"])
    
    # Get all active jobs
    all_jobs = Job.query.filter_by(is_active=True).all()
    
    # Get recommendations
    recommended_job_ids = get_job_recommendations(user, all_jobs, top_n=10)
    
    # Fetch the actual job objects in the recommended order
    recommended_jobs = []
    job_dict = {job.id: job for job in all_jobs}
    
    for job_id in recommended_job_ids:
        if job_id in job_dict:
            recommended_jobs.append(job_dict[job_id])
    
    # Get jobs that user hasn't applied to
    applied_job_ids = [app.job_id for app in user.applications]
    new_jobs = [job for job in all_jobs if job.id not in applied_job_ids and job.id not in recommended_job_ids]
    
    return render_template("recommended_jobs.html",
                         recommended_jobs=recommended_jobs,
                         new_jobs=new_jobs[:5],
                         user=user)


# AI Rank Candidates for a Job (employers only)
@app.route("/job/<int:job_id>/rank-candidates")
def rank_candidates(job_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "employer":
        return redirect("/dashboard")
    
    job = Job.query.get_or_404(job_id)
    
    # Check ownership
    if job.employer_id != session["user_id"]:
        return "You don't have permission to view this."
    
    # Get all applicants for this job
    applications = Application.query.filter_by(job_id=job_id).all()
    candidates = [app.applicant for app in applications]
    
    # Get AI rankings with detailed results
    ranked_results = get_top_candidates(job, candidates, top_n=len(candidates))
    
    # Build ranked applications list from the detailed results
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
    
    return render_template("ranked_candidates.html",
                         job=job,
                         ranked_applications=ranked_applications)


# ========== ADVANCED AI ROUTES ==========

# Skill Gap Analysis for a Job
@app.route("/job/<int:job_id>/skill-gap")
def skill_gap_analysis(job_id):
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return redirect("/dashboard")
    
    user = User.query.get(session["user_id"])
    job = Job.query.get_or_404(job_id)
    
    # Get skill gap analysis
    gap_analysis = matcher.get_skill_gap_analysis(user, job)
    
    return render_template("skill_gap.html", 
                         job=job, 
                         user=user, 
                         analysis=gap_analysis)


# Skill Suggestions API (for autocomplete)
@app.route("/api/skill-suggestions")
def skill_suggestions():
    if "user_id" not in session:
        return {"suggestions": []}
    
    query = request.args.get('q', '').strip()
    
    if len(query) < 2:
        return {"suggestions": []}
    
    suggestions = matcher.suggest_skills(query, limit=8)
    return {"suggestions": suggestions}


# Market Skill Recommendations
@app.route("/skill-recommendations")
def skill_recommendations():
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != "job_seeker":
        return redirect("/dashboard")
    
    user = User.query.get(session["user_id"])
    all_jobs = Job.query.filter_by(is_active=True).all()
    
    recommended_skills = get_skill_recommendations(user.skills, all_jobs, top_n=10)
    
    return render_template("skill_recommendations.html",
                         user=user,
                         recommended_skills=recommended_skills)


if __name__ == "__main__":
    app.run(debug=True)