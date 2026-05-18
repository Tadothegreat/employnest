import pymysql

# Aiven connection details
connection = pymysql.connect(
    host="employnest-mysql-employnest.a.aivencloud.com",
    port=22531,
    user="avnadmin",
    password="AVNS_DEKvDdKIJVCSG8WX0hP",
    database="defaultdb",
    ssl={'ssl_mode': 'REQUIRED'}
)

cursor = connection.cursor()

print("Connected to Aiven MySQL!")

# Drop tables
print("Dropping existing tables...")
cursor.execute("DROP TABLE IF EXISTS application")
cursor.execute("DROP TABLE IF EXISTS job")
cursor.execute("DROP TABLE IF EXISTS user")
connection.commit()
print("Tables dropped!")

# Create user table with ALL new columns
print("Creating user table...")
cursor.execute("""
CREATE TABLE user (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(200) NOT NULL,
    role VARCHAR(20) NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    email_verified BOOLEAN DEFAULT FALSE,
    phone_verified BOOLEAN DEFAULT FALSE,
    phone_number VARCHAR(20),
    email_verification_code VARCHAR(6),
    phone_verification_code VARCHAR(6),
    verification_code_expiry DATETIME,
    first_name VARCHAR(100),
    surname VARCHAR(100),
    date_of_birth DATE,
    national_id VARCHAR(50),
    gender VARCHAR(20),
    religion VARCHAR(50),
    marital_status VARCHAR(30),
    place_of_birth VARCHAR(200),
    home_address TEXT,
    contact_phone VARCHAR(50),
    seeker_verified BOOLEAN DEFAULT FALSE,
    seeker_verification_requested BOOLEAN DEFAULT FALSE,
    seeker_verification_date DATETIME,
    seeker_verified_by INTEGER,
    company_name VARCHAR(200),
    company_registration VARCHAR(100),
    company_address VARCHAR(300),
    company_phone VARCHAR(50),
    verification_requested BOOLEAN DEFAULT FALSE,
    verification_date DATETIME,
    verified_by INTEGER,
    skills TEXT,
    qualifications TEXT,
    experience_years INTEGER,
    resume_filename VARCHAR(200),
    profile_complete BOOLEAN DEFAULT FALSE
)
""")
connection.commit()
print("User table created!")

# Create job table
print("Creating job table...")
cursor.execute("""
CREATE TABLE job (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    company VARCHAR(200) NOT NULL,
    location VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    requirements TEXT NOT NULL,
    salary VARCHAR(100),
    job_type VARCHAR(50),
    category VARCHAR(100),
    posted_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    employer_id INTEGER NOT NULL
)
""")
connection.commit()
print("Job table created!")

# Create application table
print("Creating application table...")
cursor.execute("""
CREATE TABLE application (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    applied_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending',
    cover_letter TEXT,
    job_id INTEGER NOT NULL,
    applicant_id INTEGER NOT NULL,
    UNIQUE KEY unique_application (job_id, applicant_id)
)
""")
connection.commit()
print("Application table created!")

print("\n✅ Database fixed successfully!")
print("Now visit: https://employnest.onrender.com/setup-admin")
print("Then register a new job seeker - it will work!")

cursor.close()
connection.close()