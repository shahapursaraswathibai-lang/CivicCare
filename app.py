import os, sqlite3
from datetime import datetime
from functools import wraps
from difflib import SequenceMatcher
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR=os.path.abspath(os.path.dirname(__file__))
DB_PATH=os.path.join(BASE_DIR,'civiccare.db')
UPLOAD_DIR=os.path.join(BASE_DIR,'static','uploads')
ALLOWED_EXTENSIONS={'png','jpg','jpeg','webp'}
app=Flask(__name__)
app.secret_key=os.environ.get('SECRET_KEY','change-this-secret-key-for-production')
app.config['MAX_CONTENT_LENGTH']=5*1024*1024
app.config['UPLOAD_FOLDER']=UPLOAD_DIR
os.makedirs(UPLOAD_DIR,exist_ok=True)
CATEGORIES=['Road Damage','Streetlight','Garbage / Overflowing Bin','Drainage','Bus Stop','Public Building','Other']
STATUSES=['Pending','Verified','In Progress','Resolved','Rejected']

def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def db():
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); return con

def init_db():
    with db() as con:
        con.executescript("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'citizen',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,category TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL,location TEXT NOT NULL,latitude REAL,longitude REAL,photo TEXT,priority TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Pending',department TEXT,assigned_to INTEGER,admin_note TEXT,resolution_photo TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(assigned_to) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,report_id INTEGER NOT NULL UNIQUE,user_id INTEGER NOT NULL,rating INTEGER NOT NULL,comment TEXT,created_at TEXT NOT NULL,FOREIGN KEY(report_id) REFERENCES reports(id),FOREIGN KEY(user_id) REFERENCES users(id));""")
        for name,email,password,role in [('CivicCare Admin','admin@civiccare.local','Admin@123','admin'),('Maintenance Team','worker@civiccare.local','Worker@123','worker')]:
            if not con.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone(): con.execute('INSERT INTO users(name,email,password,role,created_at) VALUES(?,?,?,?,?)',(name,email,generate_password_hash(password),role,now()))

def allowed_file(filename): return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS
def save_upload(file):
    if not file or not file.filename: return None
    if not allowed_file(file.filename): raise ValueError('Only PNG, JPG, JPEG and WEBP images are allowed.')
    filename=datetime.now().strftime('%Y%m%d%H%M%S%f')+'_'+secure_filename(file.filename)
    file.save(os.path.join(UPLOAD_DIR,filename)); return filename

def current_user():
    if 'user_id' not in session: return None
    with db() as con: return con.execute('SELECT id,name,email,role FROM users WHERE id=?',(session['user_id'],)).fetchone()
@app.context_processor
def globals_ctx(): return {'current_user':current_user,'categories':CATEGORIES,'statuses':STATUSES}
def login_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        if 'user_id' not in session: flash('Please log in to continue.','warning'); return redirect(url_for('login'))
        return fn(*a,**kw)
    return wrapper
def roles_required(*roles):
    def dec(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a,**kw):
            user=current_user()
            if not user or user['role'] not in roles: abort(403)
            return fn(*a,**kw)
        return wrapper
    return dec
def suggest_priority(category,description):
    text=(category+' '+description).lower()
    urgent=['open manhole','exposed wire','electric wire','accident','dangerous','collapsed','fire','live wire','major leak']
    medium=['blocked','broken','overflow','pothole','not working','damaged']
    if any(x in text for x in urgent): return 'High'
    if category in ['Road Damage','Drainage','Streetlight'] or any(x in text for x in medium): return 'Medium'
    return 'Low'
def duplicate_check(category,location,title,description):
    with db() as con: rows=con.execute("SELECT id,title,description,location FROM reports WHERE category=? AND status NOT IN ('Resolved','Rejected') ORDER BY id DESC LIMIT 150",(category,)).fetchall()
    target=(title+' '+description).lower()
    for r in rows:
        if r['location'].strip().lower()==location.strip().lower() and SequenceMatcher(None,target,(r['title']+' '+r['description']).lower()).ratio()>=.48: return r['id']
    return None
@app.route('/')
def index(): return render_template('index.html')
@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        if not name or not email or len(password)<8: flash('Enter your name, email and a password of at least 8 characters.','danger')
        else:
            try:
                with db() as con: con.execute('INSERT INTO users(name,email,password,role,created_at) VALUES(?,?,?,?,?)',(name,email,generate_password_hash(password),'citizen',now()))
                flash('Account created. Please log in.','success'); return redirect(url_for('login'))
            except sqlite3.IntegrityError: flash('That email is already registered.','danger')
    return render_template('register.html')
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        with db() as con: user=con.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if user and check_password_hash(user['password'],password):
            session.clear(); session['user_id']=user['id']; flash('Welcome back, '+user['name']+'!','success'); return redirect(url_for('dashboard'))
        flash('Incorrect email or password.','danger')
    return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); flash('You have been logged out.','info'); return redirect(url_for('index'))
@app.route('/dashboard')
@login_required
def dashboard():
    user=current_user()
    with db() as con:
        if user['role']=='admin': rows=con.execute('SELECT r.*,u.name reporter FROM reports r JOIN users u ON u.id=r.user_id ORDER BY r.id DESC LIMIT 12').fetchall()
        elif user['role']=='worker': rows=con.execute('SELECT r.*,u.name reporter FROM reports r JOIN users u ON u.id=r.user_id WHERE r.assigned_to=? ORDER BY r.id DESC',(user['id'],)).fetchall()
        else: rows=con.execute('SELECT * FROM reports WHERE user_id=? ORDER BY id DESC',(user['id'],)).fetchall()
    return render_template('dashboard.html',reports=rows,role=user['role'])
@app.route('/report',methods=['GET','POST'])
@roles_required('citizen')
def create_report():
    if request.method=='POST':
        category=request.form.get('category',''); title=request.form.get('title','').strip(); description=request.form.get('description','').strip(); location=request.form.get('location','').strip(); lat=request.form.get('latitude') or None; lng=request.form.get('longitude') or None
        if category not in CATEGORIES or not title or not description or not location: flash('Please complete all required fields.','danger'); return render_template('report.html')
        try: photo=save_upload(request.files.get('photo'))
        except ValueError as e: flash(str(e),'danger'); return render_template('report.html')
        priority=suggest_priority(category,description); dup=duplicate_check(category,location,title,description)
        with db() as con:
            cur=con.execute("INSERT INTO reports(user_id,category,title,description,location,latitude,longitude,photo,priority,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,'Pending',?,?)",(session['user_id'],category,title,description,location,lat,lng,photo,priority,now(),now())); rid=cur.lastrowid
        flash(f'Report submitted. Possible duplicate #{dup} may need review.' if dup else f'Report #{rid} submitted. Suggested priority: {priority}.','warning' if dup else 'success'); return redirect(url_for('dashboard'))
    return render_template('report.html')
@app.route('/report/<int:report_id>/edit',methods=['GET','POST'])
@roles_required('citizen')
def edit_report(report_id):
    with db() as con: r=con.execute('SELECT * FROM reports WHERE id=?',(report_id,)).fetchone()
    if not r: abort(404)
    if r['user_id']!=session['user_id']: abort(403)
    if r['status'] not in ['Pending','Verified']: flash('This report can no longer be edited.','warning'); return redirect(url_for('report_detail',report_id=report_id))
    if request.method=='POST':
        category=request.form.get('category',''); title=request.form.get('title','').strip(); description=request.form.get('description','').strip(); location=request.form.get('location','').strip(); lat=request.form.get('latitude') or None; lng=request.form.get('longitude') or None
        if category not in CATEGORIES or not title or not description or not location: flash('Please complete all required fields.','danger'); return render_template('edit_report.html',report=r)
        try: photo=save_upload(request.files.get('photo')) or r['photo']
        except ValueError as e: flash(str(e),'danger'); return render_template('edit_report.html',report=r)
        with db() as con: con.execute("UPDATE reports SET category=?,title=?,description=?,location=?,latitude=?,longitude=?,photo=?,priority=?,updated_at=? WHERE id=? AND user_id=? AND status IN ('Pending','Verified')",(category,title,description,location,lat,lng,photo,suggest_priority(category,description),now(),report_id,session['user_id']))
        flash('Report updated.','success'); return redirect(url_for('report_detail',report_id=report_id))
    return render_template('edit_report.html',report=r)
@app.route('/reports')
@login_required
def reports():
    cat=request.args.get('category',''); status=request.args.get('status',''); q='SELECT r.*,u.name reporter FROM reports r JOIN users u ON u.id=r.user_id WHERE 1=1'; p=[]
    if cat in CATEGORIES: q+=' AND r.category=?'; p.append(cat)
    if status in STATUSES: q+=' AND r.status=?'; p.append(status)
    q+=' ORDER BY r.id DESC'
    with db() as con: rows=con.execute(q,p).fetchall()
    return render_template('reports.html',reports=rows,selected_category=cat,selected_status=status)
@app.route('/report/<int:report_id>')
@login_required
def report_detail(report_id):
    with db() as con:
        r=con.execute('SELECT r.*,u.name reporter FROM reports r JOIN users u ON u.id=r.user_id WHERE r.id=?',(report_id,)).fetchone()
        if not r: abort(404)
        if current_user()['role']=='citizen' and r['user_id']!=session['user_id']: abort(403)
        worker=con.execute('SELECT name FROM users WHERE id=?',(r['assigned_to'],)).fetchone() if r['assigned_to'] else None; feedback=con.execute('SELECT * FROM feedback WHERE report_id=?',(report_id,)).fetchone()
    return render_template('detail.html',report=r,worker=worker,feedback=feedback)
@app.route('/admin')
@roles_required('admin')
def admin():
    with db() as con:
        stats={s.lower().replace(' ','_'):con.execute('SELECT COUNT(*) FROM reports WHERE status=?',(s,)).fetchone()[0] for s in STATUSES}; total=con.execute('SELECT COUNT(*) FROM reports').fetchone()[0]
        active=con.execute("SELECT r.*,u.name reporter FROM reports r JOIN users u ON u.id=r.user_id WHERE r.status!='Resolved' ORDER BY CASE r.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,r.id DESC").fetchall()
        resolved=con.execute("SELECT r.id,r.title,r.category,r.priority,r.status,u.name reporter,r.updated_at FROM reports r JOIN users u ON u.id=r.user_id WHERE r.status='Resolved' ORDER BY r.updated_at DESC").fetchall()
        workers=con.execute("SELECT id,name FROM users WHERE role='worker' ORDER BY name").fetchall(); cats=con.execute('SELECT category,COUNT(*) count FROM reports GROUP BY category ORDER BY count DESC').fetchall()
    return render_template('admin.html',stats=stats,total=total,reports=active,resolved_reports=resolved,workers=workers,category_stats=cats)
@app.route('/admin/report/<int:report_id>/edit',methods=['GET','POST'])
@roles_required('admin')
def admin_edit_report(report_id):
    with db() as con: r=con.execute('SELECT * FROM reports WHERE id=?',(report_id,)).fetchone()
    if not r: abort(404)
    if request.method=='POST':
        category=request.form.get('category',''); title=request.form.get('title','').strip(); desc=request.form.get('description','').strip(); loc=request.form.get('location','').strip(); lat=request.form.get('latitude') or None; lng=request.form.get('longitude') or None
        if category not in CATEGORIES or not title or not desc or not loc: flash('Please complete all required fields.','danger'); return render_template('admin_edit_report.html',report=r)
        try: photo=save_upload(request.files.get('photo')) or r['photo']
        except ValueError as e: flash(str(e),'danger'); return render_template('admin_edit_report.html',report=r)
        with db() as con: con.execute('UPDATE reports SET category=?,title=?,description=?,location=?,latitude=?,longitude=?,photo=?,priority=?,updated_at=? WHERE id=?',(category,title,desc,loc,lat,lng,photo,suggest_priority(category,desc),now(),report_id))
        flash(f'Report #{report_id} corrected successfully.','success'); return redirect(url_for('report_detail',report_id=report_id))
    return render_template('admin_edit_report.html',report=r)
@app.route('/admin/report/<int:report_id>',methods=['POST'])
@roles_required('admin')
def admin_update(report_id):
    status=request.form.get('status',''); department=request.form.get('department','').strip(); assigned=request.form.get('assigned_to') or None; note=request.form.get('admin_note','').strip()
    if status not in STATUSES: flash('Invalid status.','danger'); return redirect(url_for('admin'))
    with db() as con:
        if not con.execute('SELECT id FROM reports WHERE id=?',(report_id,)).fetchone(): abort(404)
        con.execute('UPDATE reports SET status=?,department=?,assigned_to=?,admin_note=?,updated_at=? WHERE id=?',(status,department or None,assigned,note or None,now(),report_id))
    flash(f'Report #{report_id} updated.','success'); return redirect(url_for('admin'))
@app.route('/worker')
@roles_required('worker')
def worker():
    with db() as con: rows=con.execute('SELECT * FROM reports WHERE assigned_to=? ORDER BY id DESC',(session['user_id'],)).fetchall()
    return render_template('worker.html',reports=rows)
@app.route('/worker/report/<int:report_id>',methods=['POST'])
@roles_required('worker')
def worker_update(report_id):
    status=request.form.get('status',''); note=request.form.get('admin_note','').strip()
    if status not in ['In Progress','Resolved']: flash('Workers can set status to In Progress or Resolved.','danger'); return redirect(url_for('worker'))
    try: photo=save_upload(request.files.get('resolution_photo'))
    except ValueError as e: flash(str(e),'danger'); return redirect(url_for('worker'))
    with db() as con:
        r=con.execute('SELECT id FROM reports WHERE id=? AND assigned_to=?',(report_id,session['user_id'])).fetchone()
        if not r: abort(403)
        if photo: con.execute('UPDATE reports SET resolution_photo=?,status=?,admin_note=?,updated_at=? WHERE id=?',(photo,status,note or None,now(),report_id))
        else: con.execute('UPDATE reports SET status=?,admin_note=?,updated_at=? WHERE id=?',(status,note or None,now(),report_id))
    flash('Work status updated.','success'); return redirect(url_for('worker'))
@app.route('/feedback/<int:report_id>',methods=['POST'])
@roles_required('citizen')
def add_feedback(report_id):
    rating=request.form.get('rating',type=int); comment=request.form.get('comment','').strip()
    with db() as con:
        r=con.execute('SELECT id,user_id,status FROM reports WHERE id=?',(report_id,)).fetchone()
        if not r or r['user_id']!=session['user_id'] or r['status']!='Resolved': abort(403)
        if rating not in [1,2,3,4,5]: flash('Choose a rating from 1 to 5.','danger')
        else:
            try: con.execute('INSERT INTO feedback(report_id,user_id,rating,comment,created_at) VALUES(?,?,?,?,?)',(report_id,session['user_id'],rating,comment,now())); flash('Thank you for feedback.','success')
            except sqlite3.IntegrityError: flash('Feedback already submitted.','warning')
    return redirect(url_for('report_detail',report_id=report_id))
@app.route('/map')
@login_required
def issue_map():
    with db() as con: rows=con.execute("SELECT id,title,category,location,latitude,longitude,status,priority FROM reports WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND status!='Resolved'").fetchall()
    return render_template('map.html',points=[dict(r) for r in rows])
@app.errorhandler(403)
def forbidden(e): return render_template('error.html',code=403,message='You do not have permission to view this page.'),403
@app.errorhandler(404)
def not_found(e): return render_template('error.html',code=404,message='The page or report could not be found.'),404
with app.app_context(): init_db()
if __name__=='__main__': app.run(debug=True)
