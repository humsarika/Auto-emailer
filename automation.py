import os
import uuid
from flask import Flask, render_template, request, flash, jsonify, session
from werkzeug.utils import secure_filename
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import smtplib
import csv
import logging

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'pdf'}
app.secret_key = 'your_secret_key'  # Replace with a strong secret key

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def ensure_upload_folder_exists():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

def clear_uploads_folder():
    ensure_upload_folder_exists()
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            logging.error(f'Failed to delete {file_path}. Reason: {e}')

def send_email(user_fullname, user_email, user_password, email_subject, hr_firstname, hr_email, company, resume_filename, degree, major, job_role):
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
        message['From'] = user_fullname  # Replace with your desired name
        # Attach resume taken from the uploads folder
        with open(os.path.join(app.config['UPLOAD_FOLDER'], resume_filename), 'rb') as resume:
            attach_resume = MIMEApplication(resume.read(), Name=resume_filename)
        attach_resume['Content-Disposition'] = f'attachment; filename="{resume_filename}"'
        message.attach(attach_resume)

        # Send email using SMTP server
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(user_email, user_password)  # Replace with your email and password
            server.sendmail(user_email, hr_email, message.as_string())
        logging.info(f"Email sent to {hr_email}")
    except Exception as e:
        logging.error(f"Failed to send email to {hr_email}: {e}")
        raise

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    ensure_upload_folder_exists()
    if 'csv_file' in request.files:
        csv_file = request.files['csv_file']
        if csv_file and allowed_file(csv_file.filename):
            csv_filename = secure_filename(f"{uuid.uuid4()}_{csv_file.filename}")
            csv_file.save(os.path.join(app.config['UPLOAD_FOLDER'], csv_filename))
            session['csv_filename'] = csv_filename
            flash('CSV file uploaded successfully!')
            return jsonify({'status': 'success', 'message': 'CSV file uploaded successfully!'})
    flash('Failed to upload CSV file.')
    return jsonify({'status': 'error', 'message': 'Failed to upload CSV file.'})

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    ensure_upload_folder_exists()
    if 'resume_file' in request.files:
        resume_file = request.files['resume_file']
        if resume_file and allowed_file(resume_file.filename):
            resume_filename = secure_filename(f"{uuid.uuid4()}_{resume_file.filename}")
            resume_file.save(os.path.join(app.config['UPLOAD_FOLDER'], resume_filename))
            session['resume_filename'] = resume_filename
            flash('Resume file uploaded successfully!')
            return jsonify({'status': 'success', 'message': 'Resume file uploaded successfully!'})
    flash('Failed to upload resume file.')
    return jsonify({'status': 'error', 'message': 'Failed to upload resume file.'})

@app.route('/send_emails', methods=['POST'])
def send_emails():
    csv_filename = session.get('csv_filename')
    resume_filename = session.get('resume_filename')
    user_fullname = request.form['user_fullname']
    user_email = request.form['user_email']
    user_password = request.form['user_password']
    email_subject = request.form['email_subject']
    degree = request.form['degree']
    major = request.form['major']
    job_role = request.form['job_role']

    if not csv_filename or not resume_filename:
        flash('Both files are required.')
        return jsonify({'status': 'error', 'message': 'Please upload both CSV and resume files before sending emails.'})
    
    try:
        with open(os.path.join(app.config['UPLOAD_FOLDER'], csv_filename), 'r') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip header row if present
            for row in reader:
                hr_firstname, hr_lastname,hr_email , company = row
                # Call send_email with recipient data and resume_filename
                send_email(user_fullname, user_email, user_password, email_subject,hr_firstname, hr_email, company, resume_filename,degree, major, job_role)
        flash('Hurray! Emails sent successfully! I wish you luck in your job search.')
        # Remove the uploaded files after sending emails
        clear_uploads_folder()
        session.pop('csv_filename', None)
        session.pop('resume_filename', None)
        return jsonify({'status': 'success', 'message': 'Emails sent successfully!'})
    except Exception as e:
        logging.error(f"Error processing files: {e}")
        flash(f'OOPS! Error processing files: {str(e)}')
        return jsonify({'status': 'error', 'message': f'Error processing files: Please reupload the files and try again.'})

if __name__ == '__main__':
    ensure_upload_folder_exists()
    clear_uploads_folder()
    app.run(debug=True)