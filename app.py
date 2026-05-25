import os
import sqlite3
import jwt
import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # разрешаем запросы с любых доменов (для разработки)

app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'  # ключ для JWT
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ---------- База данных SQLite ----------
def init_db():
    with sqlite3.connect('gosts.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gosts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT NOT NULL,
                title TEXT NOT NULL,
                year INTEGER,
                scope TEXT,
                keywords TEXT,
                filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted BOOLEAN DEFAULT 0
            )
        ''')
        # Создаём администратора по умолчанию, если нет пользователей
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            admin_pw = generate_password_hash('admin123')
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           ('admin', admin_pw, 'admin'))
        conn.commit()

init_db()

# ---------- Вспомогательные функции ----------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_by_id(user_id):
    with sqlite3.connect('gosts.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
        return cursor.fetchone()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            token = token.split(' ')[1]  # Bearer <token>
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = get_user_by_id(data['user_id'])
            if not current_user:
                return jsonify({'message': 'User not found'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(current_user, *args, **kwargs):
            if current_user['role'] not in roles:
                return jsonify({'message': 'Permission denied'}), 403
            return f(current_user, *args, **kwargs)
        return decorated
    return decorator

# ---------- API Эндпоинты ----------

# 1. Регистрация
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'message': 'Username and password required'}), 400
    hashed = generate_password_hash(password)
    try:
        with sqlite3.connect('gosts.db') as conn:
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                         (username, hashed, 'user'))
        return jsonify({'message': 'User created successfully'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'message': 'Username already exists'}), 409

# 2. Логин (возвращает JWT токен)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    with sqlite3.connect('gosts.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password, role FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            token = jwt.encode({
                'user_id': user['id'],
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm='HS256')
            return jsonify({
                'token': token,
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'role': user['role']
                }
            }), 200
    return jsonify({'message': 'Invalid credentials'}), 401

# 3. Получить список ГОСТов (с возможностью поиска по номеру/названию)
@app.route('/api/gosts', methods=['GET'])
@token_required
def get_gosts(current_user):
    search = request.args.get('search', '')
    query = "SELECT * FROM gosts WHERE deleted = 0"
    params = []
    if search:
        query += " AND (number LIKE ? OR title LIKE ?)"
        like = f'%{search}%'
        params = [like, like]
    with sqlite3.connect('gosts.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        gosts = [dict(row) for row in rows]
    return jsonify(gosts), 200

# 4. Расширенный поиск
@app.route('/api/gosts/advanced', methods=['GET'])
@token_required
def advanced_search(current_user):
    number = request.args.get('number', '')
    title = request.args.get('title', '')
    year = request.args.get('year', '')
    scope = request.args.get('scope', '')
    keywords = request.args.get('keywords', '')
    
    query = "SELECT * FROM gosts WHERE deleted = 0"
    params = []
    conditions = []
    if number:
        conditions.append("number LIKE ?")
        params.append(f'%{number}%')
    if title:
        conditions.append("title LIKE ?")
        params.append(f'%{title}%')
    if year:
        conditions.append("year = ?")
        params.append(year)
    if scope:
        conditions.append("scope LIKE ?")
        params.append(f'%{scope}%')
    if keywords:
        conditions.append("keywords LIKE ?")
        params.append(f'%{keywords}%')
    
    if conditions:
        query += " AND " + " AND ".join(conditions)
    
    with sqlite3.connect('gosts.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        gosts = [dict(row) for row in rows]
    return jsonify(gosts), 200

# 5. Получить один ГОСТ по ID
@app.route('/api/gosts/<int:gost_id>', methods=['GET'])
@token_required
def get_gost(current_user, gost_id):
    with sqlite3.connect('gosts.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gosts WHERE id = ? AND deleted = 0", (gost_id,))
        gost = cursor.fetchone()
        if not gost:
            return jsonify({'message': 'GOST not found'}), 404
    return jsonify(dict(gost)), 200

# 6. Скачать файл ГОСТа
@app.route('/api/uploads/<filename>', methods=['GET'])
@token_required
def download_file(current_user, filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 7. Добавить новый ГОСТ (только редактор и админ)
@app.route('/api/gosts', methods=['POST'])
@token_required
@role_required('admin', 'editor')
def create_gost(current_user):
    number = request.form.get('number')
    title = request.form.get('title')
    year = request.form.get('year') or None
    scope = request.form.get('scope')
    keywords = request.form.get('keywords')
    file = request.files.get('file')
    
    if not number or not title:
        return jsonify({'message': 'Number and title are required'}), 400
    
    filename = None
    if file and allowed_file(file.filename):
        orig_name = secure_filename(file.filename)
        name, ext = os.path.splitext(orig_name)
        filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{name}{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    with sqlite3.connect('gosts.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO gosts (number, title, year, scope, keywords, filename)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (number, title, year, scope, keywords, filename))
        gost_id = cursor.lastrowid
        conn.commit()
    
    return jsonify({'message': 'GOST created', 'id': gost_id}), 201

# 8. Редактировать ГОСТ (только редактор и админ)
@app.route('/api/gosts/<int:gost_id>', methods=['PUT'])
@token_required
@role_required('admin', 'editor')
def update_gost(current_user, gost_id):
    # Сначала получаем существующий ГОСТ
    with sqlite3.connect('gosts.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gosts WHERE id = ? AND deleted = 0", (gost_id,))
        existing = cursor.fetchone()
        if not existing:
            return jsonify({'message': 'GOST not found'}), 404
    
    number = request.form.get('number')
    title = request.form.get('title')
    year = request.form.get('year') or None
    scope = request.form.get('scope')
    keywords = request.form.get('keywords')
    file = request.files.get('file')
    
    filename = existing['filename']
    if file and allowed_file(file.filename):
        # удаляем старый файл, если есть
        if filename and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        orig_name = secure_filename(file.filename)
        name, ext = os.path.splitext(orig_name)
        filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{name}{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    with sqlite3.connect('gosts.db') as conn:
        conn.execute('''
            UPDATE gosts 
            SET number=?, title=?, year=?, scope=?, keywords=?, filename=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        ''', (number, title, year, scope, keywords, filename, gost_id))
        conn.commit()
    
    return jsonify({'message': 'GOST updated'}), 200

# 9. Удалить ГОСТ (мягкое удаление, только редактор и админ)
@app.route('/api/gosts/<int:gost_id>', methods=['DELETE'])
@token_required
@role_required('admin', 'editor')
def delete_gost(current_user, gost_id):
    with sqlite3.connect('gosts.db') as conn:
        conn.execute("UPDATE gosts SET deleted=1 WHERE id=?", (gost_id,))
        conn.commit()
    return jsonify({'message': 'GOST moved to archive'}), 200

# 10. Получить последние 5 добавленных ГОСТов
@app.route('/api/gosts/recent', methods=['GET'])
@token_required
def recent_gosts(current_user):
    with sqlite3.connect('gosts.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM gosts WHERE deleted = 0 
            ORDER BY created_at DESC LIMIT 5
        ''')
        rows = cursor.fetchall()
        recent = [dict(row) for row in rows]
    return jsonify(recent), 200

# 11. Резервное копирование БД (только админ)
@app.route('/api/admin/backup', methods=['GET'])
@token_required
@role_required('admin')
def backup_db(current_user):
    import shutil
    backup_name = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy('gosts.db', backup_name)
    return send_from_directory('.', backup_name, as_attachment=True)

# ---------- Запуск ----------
if __name__ == '__main__':
    app.run(debug=True)