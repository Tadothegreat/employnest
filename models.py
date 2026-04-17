from extensions import db
from datetime import datetime


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'job_seeker', 'employer', 'admin'
    verified = db.Column(db.Boolean, default=False)
    
    # Account verification fields
    email_verified = db.Column(db.Boolean, default=False)
    phone_verified = db.Column(db.Boolean, default=False)
    phone_number = db.Column(db.String(20))
    email_verification_code = db.Column(db.String(6))
    phone_verification_code = db.Column(db.String(6))
    verification_code_expiry = db.Column(db.DateTime)
    
    # Personal Details (for job seekers)
    first_name = db.Column(db.String(100))
    surname = db.Column(db.String(100))
    date_of_birth = db.Column(db.Date)
    national_id = db.Column(db.String(50))
    gender = db.Column(db.String(20))
    religion = db.Column(db.String(50))
    marital_status = db.Column(db.String(30))
    place_of_birth = db.Column(db.String(200))
    home_address = db.Column(db.Text)
    contact_phone = db.Column(db.String(50))
    
    # Job Seeker Verification
    seeker_verified = db.Column(db.Boolean, default=False)
    seeker_verification_requested = db.Column(db.Boolean, default=False)
    seeker_verification_date = db.Column(db.DateTime)
    seeker_verified_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Verification fields (for employers)
    company_name = db.Column(db.String(200))
    company_registration = db.Column(db.String(100))  # Business registration number
    company_address = db.Column(db.String(300))
    company_phone = db.Column(db.String(50))
    verification_requested = db.Column(db.Boolean, default=False)
    verification_date = db.Column(db.DateTime)
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_verified_by'))  # Admin who verified
    
    # Profile fields (for job seekers)
    skills = db.Column(db.Text)  # Comma-separated skills
    qualifications = db.Column(db.Text)
    experience_years = db.Column(db.Integer)
    resume_filename = db.Column(db.String(200))
    profile_complete = db.Column(db.Boolean, default=False)
    
    # Relationships
    jobs_posted = db.relationship('Job', backref='employer', lazy=True, foreign_keys='Job.employer_id')
    applications = db.relationship('Application', backref='applicant', lazy=True)
    
    def __repr__(self):
        return f'<User {self.name} ({self.role})>'


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, nullable=False)
    salary = db.Column(db.String(100))
    job_type = db.Column(db.String(50))
    category = db.Column(db.String(100))
    posted_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    employer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    applications = db.relationship('Application', backref='job', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Job {self.title} at {self.company}>'


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    applied_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # pending, reviewed, shortlisted, rejected, hired
    cover_letter = db.Column(db.Text)
    
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    applicant_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    __table_args__ = (db.UniqueConstraint('job_id', 'applicant_id', name='unique_application'),)
    
    def __repr__(self):
        return f'<Application {self.applicant_id} -> Job {self.job_id} ({self.status})>'