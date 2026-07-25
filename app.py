from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session

from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)

from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import os

from dotenv import load_dotenv
# Load variables from a local .env file, if present, and let them take priority
# over any stray OS/User/Machine-level environment variables of the same name.
# This means a project's own .env is always authoritative for local development,
# regardless of what other projects on this machine may have set at the OS level.
load_dotenv(override=True)

from sqlalchemy import func, extract
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'probuild-engineering-secret-key-2024')

# Use DATABASE_URL if set (Postgres in production / Vercel), otherwise fall back to local SQLite for dev.
database_url = os.environ.get('DATABASE_URL', 'sqlite:///probuild.db')
if database_url.startswith('postgres://'):
    # SQLAlchemy 1.4+/2.x requires the 'postgresql://' scheme
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Optional SMTP settings for the public contact form (leads are always saved to the DB regardless)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_TO'] = os.environ.get('MAIL_TO', 'info@probuild.com')

db = SQLAlchemy(app)

@app.context_processor
def inject_current_year():
    return {'current_year_value': datetime.now().year}

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ==================== MODELS ====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # admin, manager, user
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    department = db.Column(db.String(50))
    # Permissions
    can_add_projects = db.Column(db.Boolean, default=False)
    can_edit_projects = db.Column(db.Boolean, default=False)
    can_delete_projects = db.Column(db.Boolean, default=False)
    can_add_expenses = db.Column(db.Boolean, default=False)
    can_edit_expenses = db.Column(db.Boolean, default=False)
    can_delete_expenses = db.Column(db.Boolean, default=False)
    can_view_reports = db.Column(db.Boolean, default=False)
    can_manage_users = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    city = db.Column(db.String(50))
    country = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    projects = db.relationship('Project', backref='client', lazy=True, cascade='all, delete-orphan')

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    status = db.Column(db.String(20), default='Planning')  # Planning, In Progress, On Hold, Completed
    priority = db.Column(db.String(20), default='Medium')  # Low, Medium, High, Critical
    budget = db.Column(db.Float, default=0)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    completion_percentage = db.Column(db.Integer, default=0)
    location = db.Column(db.String(200))
    project_manager = db.Column(db.String(100))
    notes = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=False)  # show on public portfolio page
    cover_image = db.Column(db.String(300))  # URL/path to a portfolio image
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='project', lazy=True, cascade='all, delete-orphan')
    expenses = db.relationship('Expense', backref='project', lazy=True, cascade='all, delete-orphan')
    milestones = db.relationship('Milestone', backref='project', lazy=True, cascade='all, delete-orphan')
    documents = db.relationship('Document', backref='project', lazy=True, cascade='all, delete-orphan')

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    assigned_to = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Pending')  # Pending, In Progress, Completed
    priority = db.Column(db.String(20), default='Medium')
    start_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Milestone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_date = db.Column(db.Date)
    completion_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='Pending')  # Pending, Achieved, Delayed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    employee_id = db.Column(db.String(50), unique=True)
    position = db.Column(db.String(100))
    department = db.Column(db.String(100))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    hire_date = db.Column(db.Date)
    salary = db.Column(db.Float, default=0)
    payment_frequency = db.Column(db.String(20), default='Monthly')  # Monthly, Bi-weekly, Weekly
    status = db.Column(db.String(20), default='Active')  # Active, Inactive, Terminated
    address = db.Column(db.Text)
    emergency_contact = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    salaries = db.relationship('Salary', backref='employee', lazy=True, cascade='all, delete-orphan')

class Salary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    month = db.Column(db.Integer)
    year = db.Column(db.Integer)
    bonus = db.Column(db.Float, default=0)
    deductions = db.Column(db.Float, default=0)
    net_amount = db.Column(db.Float)
    payment_method = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    category = db.Column(db.String(100), nullable=False)  # Materials, Labor, Equipment, Transport, etc.
    item_name = db.Column(db.String(200))  # Specific item name for better tracking
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Float, default=1)  # Quantity for better tracking
    unit_price = db.Column(db.Float)  # Unit price for items
    date = db.Column(db.Date, nullable=False)
    vendor = db.Column(db.String(100))
    payment_method = db.Column(db.String(50))
    receipt_number = db.Column(db.String(100))
    paid_by = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Pending')  # Pending, Approved, Paid
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    document_type = db.Column(db.String(50))  # Contract, Invoice, Blueprint, Report, etc.
    description = db.Column(db.Text)
    file_path = db.Column(db.String(300))
    uploaded_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    category = db.Column(db.String(100))  # Materials, Equipment, Services
    rating = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    equipment_id = db.Column(db.String(50), unique=True)
    category = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Available')  # Available, In Use, Maintenance, Retired
    purchase_date = db.Column(db.Date)
    purchase_cost = db.Column(db.Float)
    current_value = db.Column(db.Float)
    location = db.Column(db.String(200))
    assigned_to = db.Column(db.String(100))
    maintenance_schedule = db.Column(db.String(100))
    last_maintenance = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Lead(db.Model):
    """Submissions from the public contact form."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    company = db.Column(db.String(120))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='New')  # New, Contacted, Closed
    email_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SiteContent(db.Model):
    """Simple key/value store for editable text blocks on the public website
    (Home hero text, About story, Contact info, etc.) so admins can change copy
    from the dashboard instead of editing HTML templates."""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)

class ServiceItem(db.Model):
    """A single service card shown on the public Services page (and the
    'What We Do' section on Home), fully manageable from the admin panel."""
    id = db.Column(db.Integer, primary_key=True)
    icon = db.Column(db.String(50), default='fas fa-check')  # Font Awesome class
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    show_on_home = db.Column(db.Boolean, default=False)  # feature in Home's 3-card "What We Do" section

# ==================== AUTHENTICATION ====================

def get_content(key, default=''):
    """Fetch an editable site-content text block by key, falling back to a
    default if it hasn't been set yet (e.g. on a fresh install)."""
    item = SiteContent.query.filter_by(key=key).first()
    return item.value if item and item.value else default

app.jinja_env.globals['get_content'] = get_content

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def manager_required(f):
    """Manager or Admin only (e.g. reports, leads management)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('admin', 'manager'):
            flash('Access denied. Manager privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def block_viewer(f):
    """Blocks the read-only Viewer role from any add/edit action. Admin, Manager, Data Entry may pass."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role == 'viewer':
            flash('Your account has read-only access.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def manager_or_admin_for_delete(f):
    """Only Admin/Manager may delete records. Data Entry and Viewer cannot."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ('admin', 'manager'):
            flash('You do not have permission to delete records.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission):
    """Decorator to check if user has specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))

            # Admin and Manager have all permissions
            if current_user.role in ('admin', 'manager'):
                return f(*args, **kwargs)

            # Viewer is always read-only, regardless of legacy permission flags
            if current_user.role == 'viewer':
                flash('Your account has read-only access.', 'danger')
                return redirect(url_for('dashboard'))

            # Data Entry Operator can add/edit but never delete
            if current_user.role == 'data_entry' and permission.startswith('can_delete'):
                flash('Data Entry accounts cannot delete records.', 'danger')
                return redirect(url_for('dashboard'))

            # Fall back to legacy per-user permission flags (for any custom/legacy accounts)
            if not getattr(current_user, permission, False) and current_user.role not in ('data_entry',):
                flash(f'Access denied. You do not have permission to perform this action.', 'danger')
                return redirect(url_for('dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==================== ROUTES ====================

# ==================== PUBLIC WEBSITE ====================
# These pages require no login and are visible to anyone. They only ever show
# non-sensitive, curated data (projects explicitly marked is_public=True), never
# budgets, client contact details, or any accounting data.

@app.route('/')
def index():
    featured_projects = Project.query.filter_by(is_public=True).order_by(Project.created_at.desc()).limit(3).all()
    completed_count = Project.query.filter_by(status='Completed').count()
    active_count = Project.query.filter(Project.status.in_(['In Progress', 'Planning'])).count()
    years_experience = int(os.environ.get('COMPANY_YEARS_EXPERIENCE', 15))
    home_services = ServiceItem.query.filter_by(show_on_home=True).order_by(ServiceItem.sort_order).limit(3).all()
    return render_template('home.html',
                            featured_projects=featured_projects,
                            completed_count=completed_count,
                            active_count=active_count,
                            years_experience=years_experience,
                            home_services=home_services)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/services')
def services():
    all_services = ServiceItem.query.order_by(ServiceItem.sort_order).all()
    return render_template('services.html', all_services=all_services)

@app.route('/portfolio')
def portfolio():
    status_filter = request.args.get('status', 'all')
    query = Project.query.filter_by(is_public=True)
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    public_projects = query.order_by(Project.created_at.desc()).all()
    return render_template('portfolio.html', projects=public_projects, status_filter=status_filter)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')

        if not name or not email or not message:
            flash('Please fill in your name, email, and message.', 'danger')
            return redirect(url_for('contact'))

        lead = Lead(
            name=name,
            email=email,
            phone=request.form.get('phone'),
            company=request.form.get('company'),
            subject=request.form.get('subject'),
            message=message
        )
        db.session.add(lead)
        db.session.commit()

        # Best-effort email notification; never blocks the lead from being saved.
        lead.email_sent = send_lead_email(lead)
        db.session.commit()

        flash('Thanks for reaching out! Our team will get back to you soon.', 'success')
        return redirect(url_for('contact'))

    return render_template('contact.html')

def send_lead_email(lead):
    """Best-effort SMTP notification for a new lead. Returns True on success, False otherwise.
    Silently no-ops if MAIL_SERVER isn't configured, so the contact form always works even
    without email set up."""
    if not app.config.get('MAIL_SERVER'):
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText

        body = (f"New website inquiry\n\n"
                f"Name: {lead.name}\nEmail: {lead.email}\nPhone: {lead.phone or 'N/A'}\n"
                f"Company: {lead.company or 'N/A'}\nSubject: {lead.subject or 'N/A'}\n\n"
                f"Message:\n{lead.message}")
        msg = MIMEText(body)
        msg['Subject'] = f"New Contact Form Lead: {lead.name}"
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = app.config['MAIL_TO']

        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            server.starttls()
            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            server.sendmail(app.config['MAIL_USERNAME'], [app.config['MAIL_TO']], msg.as_string())
        return True
    except Exception as e:
        app.logger.warning(f"Lead email notification failed: {e}")
        return False

# ==================== INTERNAL LEADS (Manager/Admin) ====================

@app.route('/leads')
@login_required
@manager_required
def leads():
    status_filter = request.args.get('status', 'all')
    query = Lead.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    all_leads = query.order_by(Lead.created_at.desc()).all()
    return render_template('leads.html', leads=all_leads, status_filter=status_filter)

@app.route('/leads/update-status/<int:id>', methods=['POST'])
@login_required
@manager_required
def update_lead_status(id):
    lead = Lead.query.get_or_404(id)
    lead.status = request.form.get('status', lead.status)
    db.session.commit()
    return redirect(url_for('leads'))

@app.route('/leads/delete/<int:id>')
@login_required
@manager_required
def delete_lead(id):
    lead = Lead.query.get_or_404(id)
    db.session.delete(lead)
    db.session.commit()
    flash('Lead deleted.', 'success')
    return redirect(url_for('leads'))

# ==================== INTERNAL SYSTEM (login required) ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact admin.', 'danger')
                return redirect(url_for('login'))
            
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Internal accounting system: staff accounts are created by an admin (see /users/add),
    # not via public self-registration. Keeping the route so old links don't 404.
    flash('Account registration is by invitation only. Please contact your system administrator.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Statistics
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='In Progress').count()
    total_clients = Client.query.count()
    total_employees = Employee.query.filter_by(status='Active').count()
    
    # Recent projects
    recent_projects = Project.query.order_by(Project.created_at.desc()).limit(5).all()
    
    # Upcoming tasks
    upcoming_tasks = Task.query.filter(
        Task.status != 'Completed',
        Task.due_date >= datetime.now().date()
    ).order_by(Task.due_date).limit(5).all()
    
    # Monthly expenses
    current_month = datetime.now().month
    current_year = datetime.now().year
    monthly_expenses = db.session.query(func.sum(Expense.amount)).filter(
        extract('month', Expense.date) == current_month,
        extract('year', Expense.date) == current_year
    ).scalar() or 0
    
    # Monthly salaries
    monthly_salaries = db.session.query(func.sum(Salary.net_amount)).filter(
        Salary.month == current_month,
        Salary.year == current_year
    ).scalar() or 0
    
    # Project status distribution
    project_statuses = db.session.query(
        Project.status, func.count(Project.id)
    ).group_by(Project.status).all()
    
    return render_template('dashboard.html',
                         total_projects=total_projects,
                         active_projects=active_projects,
                         total_clients=total_clients,
                         total_employees=total_employees,
                         recent_projects=recent_projects,
                         upcoming_tasks=upcoming_tasks,
                         monthly_expenses=monthly_expenses,
                         monthly_salaries=monthly_salaries,
                         project_statuses=project_statuses)

# ==================== PROFILE & SETTINGS ====================

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name')
        current_user.email = request.form.get('email')
        current_user.phone = request.form.get('phone')
        current_user.department = request.form.get('department')
        
        # Check if email is already taken by another user
        existing_user = User.query.filter_by(email=current_user.email).first()
        if existing_user and existing_user.id != current_user.id:
            flash('Email already in use by another user.', 'danger')
            return redirect(url_for('profile'))
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html')

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not check_password_hash(current_user.password_hash, current_password):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('profile'))
    
    if new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('profile'))
    
    if len(new_password) < 6:
        flash('Password must be at least 6 characters long.', 'danger')
        return redirect(url_for('profile'))
    
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash('Password changed successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

# ==================== WEBSITE CONTENT MANAGEMENT (ADMIN ONLY) ====================
# Lets an admin edit the public-facing website (Home/About/Contact copy and the
# Services list) directly from the dashboard, without touching HTML templates.

WEBSITE_CONTENT_FIELDS = [
    ('home_hero_title', 'Home — Hero Title'),
    ('home_hero_subtitle', 'Home — Hero Subtitle'),
    ('home_cta_title', 'Home — Bottom CTA Title'),
    ('home_cta_subtitle', 'Home — Bottom CTA Subtitle'),
    ('about_title', 'About — Page Title'),
    ('about_subtitle', 'About — Page Subtitle'),
    ('about_story', 'About — Our Story'),
    ('about_mission', 'About — Our Mission'),
    ('about_image_url', 'About — Image URL'),
    ('services_title', 'Services — Page Title'),
    ('services_subtitle', 'Services — Page Subtitle'),
    ('contact_address', 'Contact — Address'),
    ('contact_phone', 'Contact — Phone'),
    ('contact_email', 'Contact — Email'),
    ('contact_hours', 'Contact — Business Hours'),
]

@app.route('/admin/website', methods=['GET', 'POST'])
@admin_required
def website_content():
    if request.method == 'POST':
        for key, _label in WEBSITE_CONTENT_FIELDS:
            value = request.form.get(key, '')
            item = SiteContent.query.filter_by(key=key).first()
            if item:
                item.value = value
            else:
                db.session.add(SiteContent(key=key, value=value))
        db.session.commit()
        flash('Website content updated successfully!', 'success')
        return redirect(url_for('website_content'))

    content = {key: get_content(key) for key, _label in WEBSITE_CONTENT_FIELDS}
    return render_template('website_content.html', fields=WEBSITE_CONTENT_FIELDS, content=content)

@app.route('/admin/website/services')
@admin_required
def website_services():
    all_services = ServiceItem.query.order_by(ServiceItem.sort_order).all()
    return render_template('website_services.html', services=all_services)

@app.route('/admin/website/services/add', methods=['GET', 'POST'])
@admin_required
def add_website_service():
    if request.method == 'POST':
        service = ServiceItem(
            icon=request.form.get('icon') or 'fas fa-check',
            title=request.form.get('title'),
            description=request.form.get('description'),
            sort_order=int(request.form.get('sort_order') or 0),
            show_on_home=request.form.get('show_on_home') == 'on'
        )
        db.session.add(service)
        db.session.commit()
        flash('Service added successfully!', 'success')
        return redirect(url_for('website_services'))
    return render_template('add_website_service.html')

@app.route('/admin/website/services/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_website_service(id):
    service = ServiceItem.query.get_or_404(id)
    if request.method == 'POST':
        service.icon = request.form.get('icon') or 'fas fa-check'
        service.title = request.form.get('title')
        service.description = request.form.get('description')
        service.sort_order = int(request.form.get('sort_order') or 0)
        service.show_on_home = request.form.get('show_on_home') == 'on'
        db.session.commit()
        flash('Service updated successfully!', 'success')
        return redirect(url_for('website_services'))
    return render_template('edit_website_service.html', service=service)

@app.route('/admin/website/services/delete/<int:id>')
@admin_required
def delete_website_service(id):
    service = ServiceItem.query.get_or_404(id)
    db.session.delete(service)
    db.session.commit()
    flash('Service deleted.', 'info')
    return redirect(url_for('website_services'))

# ==================== USER MANAGEMENT (ADMIN ONLY) ====================

@app.route('/users')
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users.html', users=all_users)

@app.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('add_user'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('add_user'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            full_name=request.form.get('full_name'),
            phone=request.form.get('phone'),
            department=request.form.get('department'),
            can_add_projects=request.form.get('can_add_projects') == 'on',
            can_edit_projects=request.form.get('can_edit_projects') == 'on',
            can_delete_projects=request.form.get('can_delete_projects') == 'on',
            can_add_expenses=request.form.get('can_add_expenses') == 'on',
            can_edit_expenses=request.form.get('can_edit_expenses') == 'on',
            can_delete_expenses=request.form.get('can_delete_expenses') == 'on',
            can_view_reports=request.form.get('can_view_reports') == 'on',
            can_manage_users=request.form.get('can_manage_users') == 'on',
            is_active=True,
            created_by=current_user.id
        )
        db.session.add(user)
        db.session.commit()
        flash(f'User {username} created successfully!', 'success')
        return redirect(url_for('users'))
    
    return render_template('add_user.html')

@app.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        # Don't allow editing the main admin user's role
        if user.username == 'admin' and request.form.get('role') != 'admin':
            flash('Cannot change admin user role.', 'danger')
            return redirect(url_for('edit_user', id=id))
        
        user.email = request.form.get('email')
        user.role = request.form.get('role')
        user.full_name = request.form.get('full_name')
        user.phone = request.form.get('phone')
        user.department = request.form.get('department')
        user.can_add_projects = request.form.get('can_add_projects') == 'on'
        user.can_edit_projects = request.form.get('can_edit_projects') == 'on'
        user.can_delete_projects = request.form.get('can_delete_projects') == 'on'
        user.can_add_expenses = request.form.get('can_add_expenses') == 'on'
        user.can_edit_expenses = request.form.get('can_edit_expenses') == 'on'
        user.can_delete_expenses = request.form.get('can_delete_expenses') == 'on'
        user.can_view_reports = request.form.get('can_view_reports') == 'on'
        user.can_manage_users = request.form.get('can_manage_users') == 'on'
        user.is_active = request.form.get('is_active') == 'on'
        
        # Update password if provided
        new_password = request.form.get('new_password')
        if new_password:
            user.password_hash = generate_password_hash(new_password)
        
        db.session.commit()
        flash(f'User {user.username} updated successfully!', 'success')
        return redirect(url_for('users'))
    
    return render_template('edit_user.html', user=user)

@app.route('/users/delete/<int:id>')
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    
    # Prevent deleting the main admin
    if user.username == 'admin':
        flash('Cannot delete the main admin user.', 'danger')
        return redirect(url_for('users'))
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('users'))
    
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted successfully.', 'success')
    return redirect(url_for('users'))

@app.route('/users/toggle-active/<int:id>')
@admin_required
def toggle_user_active(id):
    user = User.query.get_or_404(id)
    
    if user.username == 'admin':
        flash('Cannot deactivate the main admin user.', 'danger')
        return redirect(url_for('users'))
    
    user.is_active = not user.is_active
    db.session.commit()
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.username} has been {status}.', 'success')
    return redirect(url_for('users'))

# ==================== CLIENT ROUTES ====================

@app.route('/clients')
@login_required
def clients():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    return render_template('clients.html', clients=clients)

@app.route('/clients/add', methods=['GET', 'POST'])
@login_required
@block_viewer
def add_client():
    if request.method == 'POST':
        client = Client(
            name=request.form.get('name'),
            company=request.form.get('company'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            address=request.form.get('address'),
            city=request.form.get('city'),
            country=request.form.get('country'),
            notes=request.form.get('notes')
        )
        db.session.add(client)
        db.session.commit()
        flash('Client added successfully!', 'success')
        return redirect(url_for('clients'))
    
    return render_template('add_client.html')

@app.route('/clients/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@block_viewer
def edit_client(id):
    client = Client.query.get_or_404(id)
    
    if request.method == 'POST':
        client.name = request.form.get('name')
        client.company = request.form.get('company')
        client.email = request.form.get('email')
        client.phone = request.form.get('phone')
        client.address = request.form.get('address')
        client.city = request.form.get('city')
        client.country = request.form.get('country')
        client.notes = request.form.get('notes')
        
        db.session.commit()
        flash('Client updated successfully!', 'success')
        return redirect(url_for('clients'))
    
    return render_template('edit_client.html', client=client)

@app.route('/clients/delete/<int:id>')
@login_required
@manager_or_admin_for_delete
def delete_client(id):
    client = Client.query.get_or_404(id)
    db.session.delete(client)
    db.session.commit()
    flash('Client deleted successfully!', 'success')
    return redirect(url_for('clients'))

# ==================== PROJECT ROUTES ====================

@app.route('/projects')
@login_required
def projects():
    status_filter = request.args.get('status', 'all')
    
    if status_filter == 'all':
        projects = Project.query.order_by(Project.created_at.desc()).all()
    else:
        projects = Project.query.filter_by(status=status_filter).order_by(Project.created_at.desc()).all()
    
    # Calculate expenses for each project
    project_data = []
    for project in projects:
        total_expenses = db.session.query(func.sum(Expense.amount)).filter_by(project_id=project.id).scalar() or 0
        project_data.append({
            'project': project,
            'total_expenses': total_expenses,
            'remaining_budget': project.budget - total_expenses
        })
    
    return render_template('projects.html', project_data=project_data, status_filter=status_filter)

@app.route('/projects/add', methods=['GET', 'POST'])
@login_required
@permission_required('can_add_projects')
def add_project():
    if request.method == 'POST':
        project = Project(
            name=request.form.get('name'),
            description=request.form.get('description'),
            client_id=request.form.get('client_id'),
            status=request.form.get('status'),
            priority=request.form.get('priority'),
            budget=float(request.form.get('budget', 0)),
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date() if request.form.get('start_date') else None,
            end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None,
            location=request.form.get('location'),
            project_manager=request.form.get('project_manager'),
            notes=request.form.get('notes'),
            is_public=request.form.get('is_public') == 'on',
            cover_image=request.form.get('cover_image')
        )
        db.session.add(project)
        db.session.commit()
        flash('Project added successfully!', 'success')
        return redirect(url_for('projects'))
    
    clients = Client.query.order_by(Client.name).all()
    return render_template('add_project.html', clients=clients)

@app.route('/projects/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('can_edit_projects')
def edit_project(id):
    project = Project.query.get_or_404(id)
    
    if request.method == 'POST':
        project.name = request.form.get('name')
        project.description = request.form.get('description')
        project.client_id = request.form.get('client_id')
        project.status = request.form.get('status')
        project.priority = request.form.get('priority')
        project.budget = float(request.form.get('budget', 0))
        project.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date() if request.form.get('start_date') else None
        project.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None
        project.completion_percentage = int(request.form.get('completion_percentage', 0))
        project.location = request.form.get('location')
        project.project_manager = request.form.get('project_manager')
        project.notes = request.form.get('notes')
        project.is_public = request.form.get('is_public') == 'on'
        project.cover_image = request.form.get('cover_image')
        
        db.session.commit()
        flash('Project updated successfully!', 'success')
        return redirect(url_for('project_detail', id=id))
    
    clients = Client.query.order_by(Client.name).all()
    return render_template('edit_project.html', project=project, clients=clients)

@app.route('/projects/<int:id>')
@login_required
def project_detail(id):
    project = Project.query.get_or_404(id)
    tasks = Task.query.filter_by(project_id=id).order_by(Task.due_date).all()
    milestones = Milestone.query.filter_by(project_id=id).order_by(Milestone.target_date).all()
    expenses = Expense.query.filter_by(project_id=id).order_by(Expense.date.desc()).all()
    
    # Calculate total expenses
    total_expenses = sum(expense.amount for expense in expenses)
    
    # Calculate expenses by category
    expense_by_category = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total'),
        func.count(Expense.id).label('count')
    ).filter_by(project_id=id).group_by(Expense.category).all()
    
    # Calculate expenses by item
    expense_by_item = db.session.query(
        Expense.item_name,
        Expense.category,
        func.sum(Expense.amount).label('total'),
        func.sum(Expense.quantity).label('total_quantity')
    ).filter(
        Expense.project_id == id,
        Expense.item_name.isnot(None)
    ).group_by(Expense.item_name, Expense.category).all()
    
    # Calculate daily expenses for timeline
    daily_expenses = db.session.query(
        Expense.date,
        func.sum(Expense.amount).label('total')
    ).filter_by(project_id=id).group_by(Expense.date).order_by(Expense.date).all()
    
    # Project timeline stats
    days_elapsed = 0
    days_remaining = 0
    if project.start_date:
        days_elapsed = (datetime.now().date() - project.start_date).days
        if project.end_date:
            total_days = (project.end_date - project.start_date).days
            days_remaining = (project.end_date - datetime.now().date()).days
    
    return render_template('project_detail.html', 
                         project=project, 
                         tasks=tasks, 
                         milestones=milestones,
                         expenses=expenses,
                         total_expenses=total_expenses,
                         expense_by_category=expense_by_category,
                         expense_by_item=expense_by_item,
                         daily_expenses=daily_expenses,
                         remaining_budget=project.budget - total_expenses,
                         days_elapsed=days_elapsed,
                         days_remaining=days_remaining)

@app.route('/projects/delete/<int:id>')
@login_required
@permission_required('can_delete_projects')
def delete_project(id):
    project = Project.query.get_or_404(id)
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted successfully!', 'success')
    return redirect(url_for('projects'))

# ==================== TASK ROUTES ====================

@app.route('/tasks')
@login_required
def tasks():
    status_filter = request.args.get('status', 'all')
    
    if status_filter == 'all':
        tasks = Task.query.order_by(Task.due_date).all()
    else:
        tasks = Task.query.filter_by(status=status_filter).order_by(Task.due_date).all()
    
    return render_template('tasks.html', tasks=tasks, status_filter=status_filter)

@app.route('/tasks/add', methods=['GET', 'POST'])
@login_required
@block_viewer
def add_task():
    if request.method == 'POST':
        task = Task(
            project_id=request.form.get('project_id'),
            title=request.form.get('title'),
            description=request.form.get('description'),
            assigned_to=request.form.get('assigned_to'),
            status=request.form.get('status'),
            priority=request.form.get('priority'),
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date() if request.form.get('start_date') else None,
            due_date=datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date() if request.form.get('due_date') else None
        )
        db.session.add(task)
        db.session.commit()
        flash('Task added successfully!', 'success')
        
        # Redirect back to project if project_id was provided
        if request.form.get('project_id'):
            return redirect(url_for('project_detail', id=request.form.get('project_id')))
        return redirect(url_for('tasks'))
    
    projects = Project.query.order_by(Project.name).all()
    project_id = request.args.get('project_id')
    return render_template('add_task.html', projects=projects, selected_project_id=project_id)

@app.route('/tasks/update/<int:id>', methods=['POST'])
@login_required
@block_viewer
def update_task(id):
    task = Task.query.get_or_404(id)
    task.status = request.form.get('status')
    
    if task.status == 'Completed':
        task.completed_date = datetime.now().date()
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/tasks/delete/<int:id>')
@login_required
@manager_or_admin_for_delete
def delete_task(id):
    task = Task.query.get_or_404(id)
    project_id = task.project_id
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted successfully!', 'success')
    
    if project_id:
        return redirect(url_for('project_detail', id=project_id))
    return redirect(url_for('tasks'))

# ==================== MILESTONE ROUTES ====================

@app.route('/milestones/add', methods=['GET', 'POST'])
@login_required
@block_viewer
def add_milestone():
    if request.method == 'POST':
        milestone = Milestone(
            project_id=request.form.get('project_id'),
            title=request.form.get('title'),
            description=request.form.get('description'),
            target_date=datetime.strptime(request.form.get('target_date'), '%Y-%m-%d').date() if request.form.get('target_date') else None,
            status=request.form.get('status', 'Pending')
        )
        db.session.add(milestone)
        db.session.commit()
        flash('Milestone added successfully!', 'success')
        
        if request.form.get('project_id'):
            return redirect(url_for('project_detail', id=request.form.get('project_id')))
        return redirect(url_for('dashboard'))
    
    projects = Project.query.order_by(Project.name).all()
    project_id = request.args.get('project_id')
    return render_template('add_milestone.html', projects=projects, selected_project_id=project_id)

@app.route('/milestones/delete/<int:id>')
@login_required
@manager_or_admin_for_delete
def delete_milestone(id):
    milestone = Milestone.query.get_or_404(id)
    project_id = milestone.project_id
    db.session.delete(milestone)
    db.session.commit()
    flash('Milestone deleted successfully!', 'success')
    
    if project_id:
        return redirect(url_for('project_detail', id=project_id))
    return redirect(url_for('dashboard'))

# ==================== EMPLOYEE ROUTES ====================

@app.route('/employees')
@login_required
def employees():
    employees = Employee.query.order_by(Employee.name).all()
    return render_template('employees.html', employees=employees)

@app.route('/employees/add', methods=['GET', 'POST'])
@login_required
@block_viewer
def add_employee():
    if request.method == 'POST':
        employee = Employee(
            name=request.form.get('name'),
            employee_id=request.form.get('employee_id'),
            position=request.form.get('position'),
            department=request.form.get('department'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            hire_date=datetime.strptime(request.form.get('hire_date'), '%Y-%m-%d').date() if request.form.get('hire_date') else None,
            salary=float(request.form.get('salary', 0)),
            payment_frequency=request.form.get('payment_frequency'),
            status=request.form.get('status'),
            address=request.form.get('address'),
            emergency_contact=request.form.get('emergency_contact'),
            notes=request.form.get('notes')
        )
        db.session.add(employee)
        db.session.commit()
        flash('Employee added successfully!', 'success')
        return redirect(url_for('employees'))
    
    return render_template('add_employee.html')

@app.route('/employees/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@block_viewer
def edit_employee(id):
    employee = Employee.query.get_or_404(id)
    
    if request.method == 'POST':
        employee.name = request.form.get('name')
        employee.employee_id = request.form.get('employee_id')
        employee.position = request.form.get('position')
        employee.department = request.form.get('department')
        employee.email = request.form.get('email')
        employee.phone = request.form.get('phone')
        employee.hire_date = datetime.strptime(request.form.get('hire_date'), '%Y-%m-%d').date() if request.form.get('hire_date') else None
        employee.salary = float(request.form.get('salary', 0))
        employee.payment_frequency = request.form.get('payment_frequency')
        employee.status = request.form.get('status')
        employee.address = request.form.get('address')
        employee.emergency_contact = request.form.get('emergency_contact')
        employee.notes = request.form.get('notes')
        
        db.session.commit()
        flash('Employee updated successfully!', 'success')
        return redirect(url_for('employees'))
    
    return render_template('edit_employee.html', employee=employee)

@app.route('/employees/delete/<int:id>')
@login_required
@manager_or_admin_for_delete
def delete_employee(id):
    employee = Employee.query.get_or_404(id)
    db.session.delete(employee)
    db.session.commit()
    flash('Employee deleted successfully!', 'success')
    return redirect(url_for('employees'))

# ==================== SALARY ROUTES ====================

@app.route('/salaries')
@login_required
def salaries():
    salaries = Salary.query.order_by(Salary.payment_date.desc()).all()
    return render_template('salaries.html', salaries=salaries)

@app.route('/salaries/add', methods=['GET', 'POST'])
@login_required
@block_viewer
def add_salary():
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        bonus = float(request.form.get('bonus', 0))
        deductions = float(request.form.get('deductions', 0))
        net_amount = amount + bonus - deductions
        
        payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date()
        
        salary = Salary(
            employee_id=request.form.get('employee_id'),
            amount=amount,
            payment_date=payment_date,
            month=payment_date.month,
            year=payment_date.year,
            bonus=bonus,
            deductions=deductions,
            net_amount=net_amount,
            payment_method=request.form.get('payment_method'),
            notes=request.form.get('notes')
        )
        db.session.add(salary)
        db.session.commit()
        flash('Salary record added successfully!', 'success')
        return redirect(url_for('salaries'))
    
    employees = Employee.query.filter_by(status='Active').order_by(Employee.name).all()
    return render_template('add_salary.html', employees=employees)

@app.route('/salaries/delete/<int:id>')
@login_required
@manager_or_admin_for_delete
def delete_salary(id):
    salary = Salary.query.get_or_404(id)
    db.session.delete(salary)
    db.session.commit()
    flash('Salary record deleted successfully!', 'success')
    return redirect(url_for('salaries'))

# ==================== EXPENSE ROUTES ====================

@app.route('/expenses')
@login_required
def expenses():
    project_filter = request.args.get('project', 'all')
    category_filter = request.args.get('category', 'all')
    
    query = Expense.query
    
    if project_filter != 'all':
        query = query.filter_by(project_id=project_filter)
    
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    
    expenses = query.order_by(Expense.date.desc()).all()
    
    # Get all projects and categories for filters
    projects = Project.query.order_by(Project.name).all()
    categories = db.session.query(Expense.category).distinct().all()
    
    return render_template('expenses.html', 
                         expenses=expenses, 
                         projects=projects,
                         categories=categories,
                         project_filter=project_filter,
                         category_filter=category_filter)

@app.route('/expenses/add', methods=['GET', 'POST'])
@login_required
@permission_required('can_add_expenses')
def add_expense():
    if request.method == 'POST':
        quantity = float(request.form.get('quantity', 1))
        unit_price = float(request.form.get('unit_price', 0)) if request.form.get('unit_price') else None
        
        # Calculate amount based on quantity and unit_price if provided, otherwise use amount directly
        if unit_price:
            amount = quantity * unit_price
        else:
            amount = float(request.form.get('amount', 0))
        
        expense = Expense(
            project_id=request.form.get('project_id') if request.form.get('project_id') else None,
            category=request.form.get('category'),
            item_name=request.form.get('item_name'),
            description=request.form.get('description'),
            amount=amount,
            quantity=quantity,
            unit_price=unit_price,
            date=datetime.strptime(request.form.get('date'), '%Y-%m-%d').date(),
            vendor=request.form.get('vendor'),
            payment_method=request.form.get('payment_method'),
            receipt_number=request.form.get('receipt_number'),
            paid_by=request.form.get('paid_by'),
            status=request.form.get('status'),
            notes=request.form.get('notes'),
            created_by=current_user.id
        )
        db.session.add(expense)
        db.session.commit()
        flash('Expense added successfully!', 'success')
        
        # Redirect to project detail if expense was added from project page
        if request.form.get('project_id'):
            return redirect(url_for('project_detail', id=request.form.get('project_id')))
        return redirect(url_for('expenses'))
    
    projects = Project.query.order_by(Project.name).all()
    project_id = request.args.get('project_id')
    
    # Common expense categories
    categories = ['Materials', 'Labor', 'Equipment', 'Transport', 'Utilities', 
                 'Permits', 'Insurance', 'Subcontractors', 'Overhead', 'Other']
    
    return render_template('add_expense.html', 
                         projects=projects, 
                         categories=categories,
                         selected_project_id=project_id)

@app.route('/expenses/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('can_edit_expenses')
def edit_expense(id):
    expense = Expense.query.get_or_404(id)
    
    if request.method == 'POST':
        quantity = float(request.form.get('quantity', 1))
        unit_price = float(request.form.get('unit_price', 0)) if request.form.get('unit_price') else None
        
        if unit_price:
            amount = quantity * unit_price
        else:
            amount = float(request.form.get('amount', 0))
        
        expense.project_id = request.form.get('project_id') if request.form.get('project_id') else None
        expense.category = request.form.get('category')
        expense.item_name = request.form.get('item_name')
        expense.description = request.form.get('description')
        expense.amount = amount
        expense.quantity = quantity
        expense.unit_price = unit_price
        expense.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        expense.vendor = request.form.get('vendor')
        expense.payment_method = request.form.get('payment_method')
        expense.receipt_number = request.form.get('receipt_number')
        expense.paid_by = request.form.get('paid_by')
        expense.status = request.form.get('status')
        expense.notes = request.form.get('notes')
        
        db.session.commit()
        flash('Expense updated successfully!', 'success')
        return redirect(url_for('expenses'))
    
    projects = Project.query.order_by(Project.name).all()
    categories = ['Materials', 'Labor', 'Equipment', 'Transport', 'Utilities', 
                 'Permits', 'Insurance', 'Subcontractors', 'Overhead', 'Other']
    
    return render_template('edit_expense.html', 
                         expense=expense, 
                         projects=projects,
                         categories=categories)

@app.route('/expenses/delete/<int:id>')
@login_required
@permission_required('can_delete_expenses')
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    project_id = expense.project_id
    db.session.delete(expense)
    db.session.commit()
    flash('Expense deleted successfully!', 'success')
    
    # Redirect back to project if expense was linked to a project
    if project_id:
        return redirect(url_for('project_detail', id=project_id))
    return redirect(url_for('expenses'))

# ==================== SUPPLIER ROUTES ====================

@app.route('/suppliers')
@login_required
def suppliers():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template('suppliers.html', suppliers=suppliers)

@app.route('/suppliers/add', methods=['GET', 'POST'])
@login_required
@block_viewer
def add_supplier():
    if request.method == 'POST':
        supplier = Supplier(
            name=request.form.get('name'),
            company=request.form.get('company'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            address=request.form.get('address'),
            category=request.form.get('category'),
            rating=int(request.form.get('rating', 0)) if request.form.get('rating') else None,
            notes=request.form.get('notes')
        )
        db.session.add(supplier)
        db.session.commit()
        flash('Supplier added successfully!', 'success')
        return redirect(url_for('suppliers'))
    
    return render_template('add_supplier.html')

@app.route('/suppliers/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@block_viewer
def edit_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    
    if request.method == 'POST':
        supplier.name = request.form.get('name')
        supplier.company = request.form.get('company')
        supplier.email = request.form.get('email')
        supplier.phone = request.form.get('phone')
        supplier.address = request.form.get('address')
        supplier.category = request.form.get('category')
        supplier.rating = int(request.form.get('rating', 0)) if request.form.get('rating') else None
        supplier.notes = request.form.get('notes')
        
        db.session.commit()
        flash('Supplier updated successfully!', 'success')
        return redirect(url_for('suppliers'))
    
    return render_template('edit_supplier.html', supplier=supplier)

@app.route('/suppliers/delete/<int:id>')
@login_required
@manager_or_admin_for_delete
def delete_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    db.session.delete(supplier)
    db.session.commit()
    flash('Supplier deleted successfully!', 'success')
    return redirect(url_for('suppliers'))

# ==================== EQUIPMENT ROUTES ====================

@app.route('/equipment')
@login_required
def equipment():
    equipment_list = Equipment.query.order_by(Equipment.name).all()
    return render_template('equipment.html', equipment_list=equipment_list)

@app.route('/equipment/add', methods=['GET', 'POST'])
@login_required
@block_viewer
def add_equipment():
    if request.method == 'POST':
        equipment = Equipment(
            name=request.form.get('name'),
            equipment_id=request.form.get('equipment_id'),
            category=request.form.get('category'),
            status=request.form.get('status'),
            purchase_date=datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date() if request.form.get('purchase_date') else None,
            purchase_cost=float(request.form.get('purchase_cost', 0)) if request.form.get('purchase_cost') else None,
            current_value=float(request.form.get('current_value', 0)) if request.form.get('current_value') else None,
            location=request.form.get('location'),
            assigned_to=request.form.get('assigned_to'),
            maintenance_schedule=request.form.get('maintenance_schedule'),
            last_maintenance=datetime.strptime(request.form.get('last_maintenance'), '%Y-%m-%d').date() if request.form.get('last_maintenance') else None,
            notes=request.form.get('notes')
        )
        db.session.add(equipment)
        db.session.commit()
        flash('Equipment added successfully!', 'success')
        return redirect(url_for('equipment'))
    
    return render_template('add_equipment.html')

@app.route('/equipment/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@block_viewer
def edit_equipment(id):
    equipment = Equipment.query.get_or_404(id)
    
    if request.method == 'POST':
        equipment.name = request.form.get('name')
        equipment.equipment_id = request.form.get('equipment_id')
        equipment.category = request.form.get('category')
        equipment.status = request.form.get('status')
        equipment.purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date() if request.form.get('purchase_date') else None
        equipment.purchase_cost = float(request.form.get('purchase_cost', 0)) if request.form.get('purchase_cost') else None
        equipment.current_value = float(request.form.get('current_value', 0)) if request.form.get('current_value') else None
        equipment.location = request.form.get('location')
        equipment.assigned_to = request.form.get('assigned_to')
        equipment.maintenance_schedule = request.form.get('maintenance_schedule')
        equipment.last_maintenance = datetime.strptime(request.form.get('last_maintenance'), '%Y-%m-%d').date() if request.form.get('last_maintenance') else None
        equipment.notes = request.form.get('notes')
        
        db.session.commit()
        flash('Equipment updated successfully!', 'success')
        return redirect(url_for('equipment'))
    
    return render_template('edit_equipment.html', equipment=equipment)

@app.route('/equipment/delete/<int:id>')
@login_required
@manager_or_admin_for_delete
def delete_equipment(id):
    equipment = Equipment.query.get_or_404(id)
    db.session.delete(equipment)
    db.session.commit()
    flash('Equipment deleted successfully!', 'success')
    return redirect(url_for('equipment'))

# ==================== REPORTS ROUTES ====================

@app.route('/reports')
@login_required
def reports():
    # Reports are read-only, so any logged-in role (admin, manager, data_entry, viewer) can view them.
    # Financial summary
    total_expenses = db.session.query(func.sum(Expense.amount)).scalar() or 0
    total_project_budgets = db.session.query(func.sum(Project.budget)).scalar() or 0
    
    # Monthly breakdown
    current_year = datetime.now().year
    monthly_data = []
    for month in range(1, 13):
        expenses = db.session.query(func.sum(Expense.amount)).filter(
            extract('month', Expense.date) == month,
            extract('year', Expense.date) == current_year
        ).scalar() or 0
        
        salaries = db.session.query(func.sum(Salary.net_amount)).filter(
            Salary.month == month,
            Salary.year == current_year
        ).scalar() or 0
        
        monthly_data.append({
            'month': datetime(current_year, month, 1).strftime('%B'),
            'expenses': expenses,
            'salaries': salaries,
            'total': expenses + salaries
        })
    
    # Project statistics
    project_stats = db.session.query(
        Project.status, 
        func.count(Project.id),
        func.sum(Project.budget)
    ).group_by(Project.status).all()
    
    # Expense by category
    expense_by_category = db.session.query(
        Expense.category,
        func.sum(Expense.amount)
    ).group_by(Expense.category).all()
    
    return render_template('reports.html',
                         total_expenses=total_expenses,
                         total_project_budgets=total_project_budgets,
                         monthly_data=monthly_data,
                         project_stats=project_stats,
                         expense_by_category=expense_by_category)

# ==================== INITIALIZATION ====================

def init_db():
    with app.app_context():
        db.create_all()
        
        # Create default admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@probuild.com',
                password_hash=generate_password_hash('admin123'),
                role='admin',
                full_name='System Administrator',
                can_add_projects=True,
                can_edit_projects=True,
                can_delete_projects=True,
                can_add_expenses=True,
                can_edit_expenses=True,
                can_delete_expenses=True,
                can_view_reports=True,
                can_manage_users=True,
                is_active=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: username='admin', password='admin123'")

        # Seed default services so the public Services page (and Home's "What We
        # Do" section) keep showing sensible content out of the box, while being
        # fully editable from the admin panel (Website Content -> Manage Services).
        if ServiceItem.query.count() == 0:
            default_services = [
                ('fas fa-drafting-compass', 'Design & Planning', 'Feasibility studies, site surveys, architectural drawings, and structural engineering design.', True),
                ('fas fa-hard-hat', 'General Construction', 'Residential, commercial, and industrial construction managed from groundbreaking to handover.', True),
                ('fas fa-road', 'Infrastructure', 'Roads, utilities, and civil infrastructure projects delivered to public and private clients.', False),
                ('fas fa-tools', 'Renovation & Maintenance', 'Upgrades, retrofits, and ongoing facility maintenance for existing structures.', True),
                ('fas fa-clipboard-check', 'Project Management', 'Budgeting, scheduling, procurement, and on-site supervision for the life of the project.', False),
                ('fas fa-truck', 'Equipment & Logistics', 'Heavy machinery, material sourcing, and supplier coordination for large-scale builds.', False),
            ]
            for i, (icon, title, desc, on_home) in enumerate(default_services):
                db.session.add(ServiceItem(icon=icon, title=title, description=desc, sort_order=i, show_on_home=on_home))
            db.session.commit()

# On Vercel (and any WSGI server) this module is imported, not run as __main__,
# so we call init_db() here to guarantee tables + the default admin exist.
# db.create_all() is safe to call repeatedly - it only creates missing tables.
init_db()

if __name__ == '__main__':
    print("=" * 60)
    print("ProBuild - Construction Management System")
    print("=" * 60)
    print("\nServer starting...")
    print(f"Access the application at: http://127.0.0.1:5000")
    print(f"Or from network at: http://0.0.0.0:5000")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60)
    print("\nDefault admin credentials:")
    print("Username: admin")
    print("Password: admin123")
    print("=" * 60 + "\n")
    
    # Run with debug=False for production/standalone builds
    app.run(debug=False, host='0.0.0.0', port=5000)
