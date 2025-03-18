from flask import Flask, render_template, request, flash, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import smtplib
import csv
import logging
import os
import requests
from google.cloud import storage
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from dotenv import load_dotenv
import base64
import json
from pymongo import MongoClient  
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from db import db

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')

# Configure MongoDB connection
mongo_uri = os.environ.get("MONGO_URI")
client = MongoClient(mongo_uri)
db = client.get_database("job_portal")  # Change the database name as needed
users_collection = db["users"]

# Flask-Login setup
login_manager = LoginManager(app)
login_manager.login_view = 'login'

users_collection = db["users"]  # Define users collection

@login_manager.user_loader
def load_user(user_id):
    logging.info(f"User ID: {user_id}")
    user_data = users_collection.find_one({"_id": ObjectId(user_id)})
    return User(user_data) if user_data else None

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])  # Convert ObjectId to string
        self.username = user_data.get("username")
        self.email = user_data.get("email")
        self.password = user_data.get("password")

    def is_authenticated(self):
        return True
        

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Decode the service account key file from the environment variable
google_credentials = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
# Add padding if necessary
missing_padding = len(google_credentials) % 4
if missing_padding:
    google_credentials += '=' * (4 - missing_padding)

service_account_info = json.loads(base64.b64decode(google_credentials))
storage_client = storage.Client.from_service_account_info(service_account_info)
bucket_name = os.environ.get('GCS_BUCKET_NAME')
bucket = storage_client.bucket(bucket_name)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'csv', 'pdf'}

def upload_file_to_gcs(file, bucket_name, folder_name):
    try:
        blob = bucket.blob(f"{folder_name}/{file.filename}")
        blob.upload_from_file(file, content_type=file.content_type)
        logging.info(f"File {file.filename} uploaded to {folder_name}/{file.filename}")
        return blob.public_url
    except Exception as e:
        logging.error(f"Failed to upload file to GCS: {e}")
        return None

def send_email(user_fullname, user_email, user_password, email_subject, hr_firstname, hr_email, company, resume_file_url, degree, major, job_role):
    try:
        message = MIMEMultipart("alternative")
        personalized_text = f"""
Hello {hr_firstname},

My name is {user_fullname}, and I'm a recent graduate with a {degree} in {major}. I'm writing to express my interest in {job_role} roles at your organization.

I am eager to learn more about opportunities at {company} and believe my skills and enthusiasm would be a valuable asset to your team.

I have attached my resume for your review and welcome the opportunity to discuss how I can contribute to your organization's success.

Thank you for your time and consideration.

Sincerely,
{user_fullname}
"""
        message.attach(MIMEText(personalized_text))
        message['Subject'] = email_subject
        message['From'] = user_fullname
        message['To'] = hr_email

        # Attach resume from the URL
        resume_response = requests.get(resume_file_url)
        resume_filename = resume_file_url.split('/')[-1]
        attach_resume = MIMEApplication(resume_response.content, Name=resume_filename)
        attach_resume['Content-Disposition'] = f'attachment; filename="{resume_filename}"'
        message.attach(attach_resume)

        # Send email using SMTP server
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(user_email, user_password)
            server.sendmail(user_email, hr_email, message.as_string())
        logging.info(f"Email sent to {hr_email}")
    except Exception as e:
        logging.error(f"Failed to send email to {hr_email}: {e}")
        raise

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = users_collection.find_one({"email": email})

        if user and check_password_hash(user["password"], password):
            user_obj = User(user)  # Create User object
            login_user(user_obj)  # Log in user
            flash("Logged in successfully!", "success")
            return redirect(url_for("index"))
            
        else:
            flash("Invalid email or password", "danger")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        # Check if email already exists
        existing_user = users_collection.find_one({"email": email})
        if existing_user:
            flash("Email already exists. Try logging in!", "danger")
            return redirect(url_for("register"))

        # Hash the password before storing it
        hashed_password = generate_password_hash(password)

        # Insert into MongoDB
        users_collection.insert_one({
            "username": username,
            "email": email,
            "password": hashed_password
        })

        flash("Registered successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('upload.html')

@app.route('/upload_csv', methods=['POST'])
@login_required
def upload_csv():
    if 'csv_file' in request.files:
        csv_file = request.files['csv_file']
        if csv_file and allowed_file(csv_file.filename):
            csv_file_url = upload_file_to_gcs(csv_file, bucket_name, 'csv_files')
            if csv_file_url:
                session['csv_file_url'] = csv_file_url
                flash('CSV file uploaded successfully!')
                return jsonify({'status': 'success', 'message': 'CSV file uploaded successfully!'})
    flash('Failed to upload CSV file.')
    return jsonify({'status': 'error', 'message': 'Failed to upload CSV file.'})

@app.route('/upload_resume', methods=['POST'])
@login_required
def upload_resume():
    if 'resume_file' in request.files:
        resume_file = request.files['resume_file']
        if resume_file and allowed_file(resume_file.filename):
            resume_file_url = upload_file_to_gcs(resume_file, bucket_name, 'resume_files')
            if resume_file_url:
                session['resume_file_url'] = resume_file_url
                flash('Resume file uploaded successfully!')
                return jsonify({'status': 'success', 'message': 'Resume file uploaded successfully!'})
    flash('Failed to upload resume file.')
    return jsonify({'status': 'error', 'message': 'Failed to upload resume file.'})

@app.route('/send_emails', methods=['POST'])
@login_required
def send_emails():
    # if current_user.email_count >= 10 and not current_user.is_plus:
    #     flash('Upgrade to Plus to send more than 10 emails.')
    #     return jsonify({'status': 'error', 'message': 'Upgrade to Plus to send more than 2 emails.'})

    csv_file_url = session.get('csv_file_url')
    resume_file_url = session.get('resume_file_url')
    user_fullname = request.form.get('user_fullname')
    user_email = request.form.get('user_email')
    user_password = request.form.get('user_password')
    email_subject = request.form.get('email_subject')
    degree = request.form.get('degree')
    major = request.form.get('major')
    job_role = request.form.get('job_role')


    if not csv_file_url or not resume_file_url or not user_fullname or not user_email or not user_password or not email_subject or not degree or not major or not job_role:
        flash('All fields are required.')
        return jsonify({'status': 'error', 'message': 'Please ensure all fields are filled before sending emails.'})

    try:
        # Extract the file name from the URL
        csv_file_name = csv_file_url.split('/')[-1]
        blob = bucket.blob(f'csv_files/{csv_file_name}')
        csv_file = blob.download_as_text().splitlines()
        reader = csv.reader(csv_file)
        next(reader)  # Skip header row if present
        for row in reader:
            hr_firstname, hr_lastname, hr_email, company = row
            # Call send_email with recipient data and resume_filename
            send_email(user_fullname, user_email, user_password, email_subject, hr_firstname, hr_email, company, resume_file_url, degree, major, job_role)
        # current_user.email_count += 1
        # db.session.commit()
        flash('Hurray! Emails sent successfully! I wish you luck in your job search.')
        
        # Delete the files from Google Cloud Storage
        csv_blob = bucket.blob(f'csv_files/{csv_file_name}')
        resume_blob = bucket.blob(f'resume_files/{resume_file_url.split("/")[-1]}')
        csv_blob.delete()
        resume_blob.delete()

        session.pop('csv_file_url', None)
        session.pop('resume_file_url', None)
        return jsonify({'status': 'success', 'message': 'Emails sent successfully!'})
    except Exception as e:
        logging.error(f"Error processing files: {e}")
        flash(f'OOPS! Error processing files: {str(e)}')
        return jsonify({'status': 'error', 'message': f'Error processing files: {str(e)}'})


if __name__ == "__main__":
    app.run(debug=True)