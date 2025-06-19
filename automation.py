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
# from db import db
from db import get_database, get_file_system


# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')

# Configure MongoDB connection
mongo_uri = os.environ.get("MONGO_URI")
client = MongoClient(mongo_uri)
db = client.get_database("auto_emailer")  # Change the database name as needed
users_collection = db["users"]
fs = get_file_system()

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

# # Decode the service account key file from the environment variable
# google_credentials = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
# # Add padding if necessary
# missing_padding = len(google_credentials) % 4
# if missing_padding:
#     google_credentials += '=' * (4 - missing_padding)

# service_account_info = json.loads(base64.b64decode(google_credentials))
# storage_client = storage.Client.from_service_account_info(service_account_info)
# bucket_name = os.environ.get('GCS_BUCKET_NAME')
# bucket = storage_client.bucket(bucket_name)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'csv', 'pdf'}

@login_manager.unauthorized_handler
def unauthorized_callback():
     if request.path.startswith('/upload_csv') or request.is_json:
        return jsonify({'status': 'error', 'message': 'Unauthorized. Please login.'}), 401
     elif request.path.startswith('/upload_resume'):
        return jsonify({'status': 'error', 'message': 'Unauthorized. Please login.'}), 401
     else:
        return redirect(url_for('login'))
    

def upload_file_to_gridfs(file, file_type):
    try:
        file_id = fs.put(file, filename=file.filename, content_type=file.content_type, metadata={"type": file_type})
        logging.info(f"File {file.filename} uploaded to GridFS with id: {file_id}")
        return str(file_id)  # Convert ObjectId to string
    except Exception as e:
        logging.error(f"Failed to upload file to GridFS: {e}")
        return None


def send_email_with_file(user_fullname, user_email, user_password, email_subject, hr_firstname, hr_email, company, resume_bytes, degree, major, job_role, resume_filename):
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

        # Attach resume directly
        attach_resume = MIMEApplication(resume_bytes, Name=resume_filename)
        attach_resume['Content-Disposition'] = f'attachment; filename="{resume_filename}"'
        message.attach(attach_resume)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(user_email, user_password)
            server.sendmail(user_email, hr_email, message.as_string())
        logging.info(f"Email sent to {hr_email}")

    except Exception as e:
        logging.error(f"Failed to send email: {e}")

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
            print(f"User ID: {user_obj.id}")  # Debugging line
            print("User logged in:", user_obj.username)  # Debugging line
            return redirect(url_for("upload"))
            
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
    return redirect(url_for('home'))

@app.route('/')
def home():
    logged_in = current_user.is_authenticated
    return render_template('home.html', logged_in=logged_in)

@app.route('/index')
def upload():
    logged_in = current_user.is_authenticated
    return render_template('upload.html', logged_in=logged_in)

@app.route('/contact')
def contact():
    logged_in = current_user.is_authenticated
    return render_template('contact.html', logged_in=logged_in)

@app.route('/upload_csv', methods=['POST'])
@login_required
def upload_csv():
    if 'csv_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No CSV file provided.'}), 400

    csv_file = request.files['csv_file']
    if csv_file and allowed_file(csv_file.filename):
        csv_file_id = upload_file_to_gridfs(csv_file, 'csv')
        if csv_file_id:
            session['csv_file_id'] = csv_file_id
            return jsonify({'status': 'success', 'message': 'CSV file uploaded successfully!'}), 200
        else:
            # Backend detailed error goes to logs only
            logging.error('CSV file upload to GridFS failed.')
            return jsonify({'status': 'error', 'message': 'Failed to upload CSV. Please try again later.'}), 500

    return jsonify({'status': 'error', 'message': 'Invalid file type. Only CSV allowed.'}), 400

@app.route('/upload_resume', methods=['POST'])
@login_required
def upload_resume():
    if 'resume_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No resume file provided.'}), 400

    resume_file = request.files['resume_file']
    if resume_file and allowed_file(resume_file.filename):
        resume_file_id = upload_file_to_gridfs(resume_file, 'resume')
        if resume_file_id:
            session['resume_file_id'] = resume_file_id
            return jsonify({'status': 'success', 'message': 'Resume uploaded successfully!'}), 200
        else:
            logging.error('Resume file upload to GridFS failed.')
            return jsonify({'status': 'error', 'message': 'Failed to upload resume. Try again later.'}), 500

    return jsonify({'status': 'error', 'message': 'Invalid file type. Only PDF allowed.'}), 400


@app.route('/send_emails', methods=['POST'])
@login_required
def send_emails():
    csv_file_id = session.get('csv_file_id')
    resume_file_id = session.get('resume_file_id')
    user_fullname = request.form.get('user_fullname')
    user_email = request.form.get('user_email')
    user_password = request.form.get('user_password')
    email_subject = request.form.get('email_subject')
    degree = request.form.get('degree')
    major = request.form.get('major')
    job_role = request.form.get('job_role')

    if not csv_file_id or not resume_file_id or not user_fullname or not user_email or not user_password or not email_subject or not degree or not major or not job_role:
        flash('All fields are required.')
        return jsonify({'status': 'error', 'message': 'Please ensure all fields are filled before sending emails.'})

    try:
        # Get CSV from GridFS
        csv_file = fs.get(ObjectId(csv_file_id))
        csv_content = csv_file.read().decode('utf-8').splitlines()
        reader = csv.reader(csv_content)
        next(reader)  # Skip header row if any

        # Get Resume file from GridFS
        resume_file = fs.get(ObjectId(resume_file_id))
        resume_bytes = resume_file.read()

        for row in reader:
            hr_firstname, hr_lastname, hr_email, company = row
            # Send each email with resume file (from bytes)
            send_email_with_file(user_fullname, user_email, user_password, email_subject,
                                 hr_firstname, hr_email, company, resume_bytes,
                                 degree, major, job_role, resume_file.filename)

        flash('Hurray! Emails sent successfully! Best of luck!')
        session.pop('csv_file_id', None)
        session.pop('resume_file_id', None)
        return jsonify({'status': 'success', 'message': 'Emails sent successfully!'})
    except Exception as e:
        logging.error(f"Error processing files: {e}")
        flash(f'OOPS! Error processing files:')
        return jsonify({'status': 'error', 'message': f'Error processing files'})


# @app.route('/send_emails', methods=['POST'])
# @login_required
# def send_emails():
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

def delete_file_from_gcs(bucket_name, file_path):
    """Deletes a file from Google Cloud Storage, but prevents 404 errors."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_path)

    try:
        blob.delete()
        return {"success": True, "message": "✅ File deleted successfully!"}

    except NotFound:
        return {"success": False, "message": "⚠️ File not found. It may have been deleted already."}

    except Exception as e:
        return {"success": False, "message": f"❌ An error occurred: {str(e)}"}

@app.route('/privacypolicy')
def privacy_policy():
    return render_template('privacypolicy.html')

@app.route('/terms')
def terms_of_service():
    return render_template('terms.html')


@app.route("/test_session")
def test_session():
    session["user_id"] = "123"
    return redirect(url_for("home"))

@app.route("/check_session")
def check_session():
    return redirect(url_for("home"))




if __name__ == "__main__":
    app.run(debug=True)