"""
One-time script to create admin account in Aiven MySQL database.
Run this ONCE from your local computer.
"""

import os
import pymysql
from werkzeug.security import generate_password_hash

# Aiven MySQL Connection Details
HOST = "employnest-mysql-employnest.a.aivencloud.com"
PORT = 22531
USER = "avnadmin"
PASSWORD = "AVNS_DEKvDdKIJVCSG8WX0hP"
DATABASE = "defaultdb"
SSL_MODE = "REQUIRED"

def create_admin():
    """Create admin account in cloud database"""
    
    # Connect to Aiven MySQL
    connection = pymysql.connect(
        host=HOST,
        port=PORT,
        user=USER,
        password=PASSWORD,
        database=DATABASE,
        ssl={'ssl_mode': SSL_MODE}
    )
    
    cursor = connection.cursor()
    
    # Check if admin already exists
    cursor.execute("SELECT id FROM user WHERE email = 'admin@employnest.com'")
    existing = cursor.fetchone()
    
    if existing:
        print("ℹ️ Admin account already exists in cloud database!")
        print("   Email: admin@employnest.com")
        print("   Password: Admin@2026")
        connection.close()
        return
    
    # Create admin account
    hashed_password = generate_password_hash('Admin@2026')
    
    cursor.execute("""
        INSERT INTO user 
        (name, email, password, role, verified, email_verified, phone_verified)
        VALUES 
        (%s, %s, %s, %s, %s, %s, %s)
    """, (
        'System Admin',
        'admin@employnest.com',
        hashed_password,
        'admin',
        True,
        True,
        True
    ))
    
    connection.commit()
    connection.close()
    
    print("✅ Admin account created successfully in cloud database!")
    print("   Email: admin@employnest.com")
    print("   Password: Admin@2026")
    print("")
    print("🌐 You can now login at: https://employnest.onrender.com/login")

if __name__ == "__main__":
    create_admin()