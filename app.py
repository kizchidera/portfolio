import os
import sqlite3
import random
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "derki_visuals_secret_key"

# Folder Configurations
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['PROFILE_FOLDER'] = 'static/profile_pics'
app.config['PDF_FOLDER'] = 'static/pdfs'

# --- CONFIGURATION (Update with your real keys) ---
PAYSTACK_SECRET_KEY = "sk_test_xxxx" 
TWILIO_SID = "ACxxxx"
TWILIO_AUTH_TOKEN = "xxxx"
ADMIN_WHATSAPP = "whatsapp:+234xxxxxxxx" 
TWILIO_WHATSAPP = "whatsapp:+14155238886" 

# Ensure storage directories exist
for folder in [app.config['UPLOAD_FOLDER'], app.config['PROFILE_FOLDER'], app.config['PDF_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- PUBLIC ROUTES ---

@app.route('/')
def index():
    conn = get_db_connection()
    works = conn.execute('SELECT * FROM works').fetchall()
    profile = conn.execute('SELECT * FROM profile WHERE id = 1').fetchone()
    conn.close()
    
    # Shuffle works for the background carousel
    works_list = [dict(ix) for ix in works]
    random.shuffle(works_list)
    
    return render_template('index.html', works=works_list, profile=profile)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'password123':
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid Credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

# --- ADMIN DASHBOARD ---

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    works = conn.execute('SELECT * FROM works').fetchall()
    reqs = conn.execute('SELECT * FROM requests').fetchall()
    profile = conn.execute('SELECT * FROM profile WHERE id = 1').fetchone()
    conn.close()
    return render_template('admin.html', works=works, requests=reqs, profile=profile)

# --- PORTFOLIO & BRIEF MANAGEMENT ---

@app.route('/admin/add', methods=['POST'])
def add_work():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    title = request.form['title']
    category = request.form['category']
    description = request.form['description']
    
    # Handle Image Upload
    media = request.files.get('media')
    media_filename = None
    if media and media.filename != '':
        media_filename = secure_filename(media.filename)
        media.save(os.path.join(app.config['UPLOAD_FOLDER'], media_filename))
        
    # Handle PDF Brief Upload
    pdf = request.files.get('pdf_brief')
    pdf_filename = "" # Default to empty string to prevent index.html crashes
    if pdf and pdf.filename != '':
        pdf_filename = secure_filename(pdf.filename)
        pdf.save(os.path.join(app.config['PDF_FOLDER'], pdf_filename))
        
    conn = get_db_connection()
    conn.execute('''INSERT INTO works (title, category, description, media_url, pdf_url) 
                    VALUES (?,?,?,?,?)''',
                 (title, category, description, media_filename, pdf_filename))
    conn.commit()
    conn.close()
    flash("Project and Brief uploaded successfully!")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit/<int:id>', methods=['POST'])
def edit_work(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    title = request.form.get('title')
    category = request.form.get('category')
    description = request.form.get('description')
    
    conn = get_db_connection()
    conn.execute('UPDATE works SET title=?, category=?, description=? WHERE id=?', 
                 (title, category, description, id))
    conn.commit()
    conn.close()
    flash("Project updated!")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:id>')
def delete_work(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM works WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

# --- PROFILE UPDATE ---

@app.route('/admin/profile/update', methods=['POST'])
def update_profile():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    about = request.form.get('about')
    whatsapp = request.form.get('whatsapp')
    fb = request.form.get('fb')
    ig = request.form.get('ig')
    linkedin = request.form.get('linkedin')
    file = request.files.get('profile_pic')
    
    conn = get_db_connection()
    current = conn.execute('SELECT profile_pic FROM profile WHERE id = 1').fetchone()
    pic_filename = current['profile_pic'] if current else None

    if file and file.filename != '':
        pic_filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['PROFILE_FOLDER'], pic_filename))

    conn.execute('''UPDATE profile SET about=?, whatsapp=?, fb=?, ig=?, linkedin=?, profile_pic=? 
                    WHERE id = 1''', (about, whatsapp, fb, ig, linkedin, pic_filename))
    conn.commit()
    conn.close()
    flash("Profile updated!")
    return redirect(url_for('admin_dashboard'))

# --- PAYMENTS & REQUESTS ---

@app.route('/request-design', methods=['GET', 'POST'])
def request_design():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        details = request.form.get('details')
        
        url = "https://api.paystack.co/transaction/initialize"
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
        payload = {"email": email, "amount": 200000, "callback_url": url_for('callback', _external=True)}
        
        try:
            res = requests.post(url, headers=headers, json=payload).json()
            if res['status']:
                conn = get_db_connection()
                conn.execute('INSERT INTO requests (name, email, details) VALUES (?,?,?)', (name, email, details))
                conn.commit()
                conn.close()
                return redirect(res['data']['authorization_url'])
        except:
            flash("Gateway error. Please try again.")
            
    return render_template('request_form.html')

@app.route('/payment/callback')
def callback():
    send_whatsapp_notification("New Paid Design Request Received!")
    return "<h1>Success!</h1><p>Request sent. <a href='/'>Home</a></p>"

def send_whatsapp_notification(msg):
    from twilio.rest import Client
    try:
        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(from_=TWILIO_WHATSAPP, body=msg, to=ADMIN_WHATSAPP)
    except:
        print("WhatsApp notification failed (Check Twilio credentials)")

if __name__ == '__main__':
    app.run(debug=True)