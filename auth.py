from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from models import User
from datetime import datetime, timedelta
import logging
from rate_limiter import rate_limiter, get_client_ip

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        client_ip = get_client_ip(request)
        allowed, retry_after = rate_limiter.is_allowed(
            key=f"auth_login:{client_ip}",
            limit=10,
            window_seconds=60
        )
        if not allowed:
            flash(f'Juda ko\'p urinish. {retry_after} soniyadan keyin qayta urinib ko\'ring.', 'error')
            return render_template('login.html'), 429

        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Foydalanuvchi nomi/email va parol kiritilishi shart!', 'error')
            return render_template('login.html')
        
        try:
            # Avval username bo'yicha qidiramiz
            user = User.query.filter_by(username=username).first()
            # Agar topilmasa, email bo'yicha ham urinib ko'ramiz
            if not user:
                user = User.query.filter_by(email=username).first()
        except Exception as db_error:
            logging.error(f"Database connection error during login: {str(db_error)}")
            flash('Ma\'lumotlar bazasi bilan bog\'lanishda muammo. Iltimos keyinroq urinib ko\'ring.', 'error')
            return render_template('login.html')
        
        if user and check_password_hash(user.password_hash, password):
            if user.is_active:
                login_user(user, remember=True)
                next_page = request.args.get('next')
                flash(f'Xush kelibsiz, {user.username}!', 'success')
                return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
            else:
                flash('Sizning hisobingiz bloklangan!', 'error')
        else:
            flash('Noto\'g\'ri foydalanuvchi nomi/email yoki parol!', 'error')
    
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            logging.info(f"Registration attempt for username: {username}, email: {email}")
            
            # Validation
            if not all([username, email, password, confirm_password]):
                flash('Barcha maydonlar to\'ldirilishi shart!', 'error')
                return render_template('register.html')
            
            if password != confirm_password:
                flash('Parollar mos kelmaydi!', 'error')
                return render_template('register.html')
            
            if password and len(password) < 6:
                flash('Parol kamida 6 ta belgidan iborat bo\'lishi kerak!', 'error')
                return render_template('register.html')
            
            # Check if user exists with database error handling
            try:
                existing_user = User.query.filter_by(username=username).first()
                if existing_user:
                    flash('Bu foydalanuvchi nomi band!', 'error')
                    return render_template('register.html')
                
                existing_email = User.query.filter_by(email=email).first()
                if existing_email:
                    flash('Bu email band!', 'error')
                    return render_template('register.html')
            except Exception as db_check_error:
                logging.error(f"Database check error: {str(db_check_error)}")
                flash('Ma\'lumotlar bazasi bilan bog\'lanishda muammo. Iltimos keyinroq urinib ko\'ring.', 'error')
                return render_template('register.html')
            
            # Create new user with test subscription (15 days)
            user = User()
            user.username = username
            user.email = email
            user.password_hash = generate_password_hash(password or '')
            user.language = 'uz'
            user.subscription_type = 'free'
            user.subscription_end_date = datetime.utcnow() + timedelta(days=15)
            user.is_active = True
            
            db.session.add(user)
            db.session.commit()
            
            logging.info(f"User registration successful for: {username}")
            flash('Ro\'yxatdan o\'tish muvaffaqiyatli! Endi tizimga kirishingiz mumkin.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            username_for_log = request.form.get('username', 'unknown')
            logging.error(f"Registration error for {username_for_log}: {str(e)}", exc_info=True)
            flash(f'Ro\'yxatdan o\'tishda xatolik yuz berdi. Iltimos qaytadan urinib ko\'ring.', 'error')
            return render_template('register.html')
    
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Tizimdan muvaffaqiyatli chiqdingiz!', 'info')
    return redirect(url_for('main.index'))
