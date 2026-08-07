# ─────────────────────────────────────────────
# KDT Resource — Auth Backend (Python / Flask)
# Stack: Flask · PyMongo · bcrypt · PyJWT · python-dotenv
# ─────────────────────────────────────────────
# pip install flask pymongo bcrypt PyJWT python-dotenv flask-cors

import os
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

load_dotenv()

app = Flask(__name__, static_folder='public', static_url_path='')
CORS(app)

# ── MongoDB connection ──────────────────────
MONGO_URI  = os.getenv('MONGO_URI', 'mongodb://localhost:27017/kdt_resource')
JWT_SECRET = os.getenv('JWT_SECRET', 'changeme_secret')
PORT       = int(os.getenv('PORT', 4000))

client = MongoClient(MONGO_URI)
db     = client.get_default_database()
users  = db['users']

# Ensure unique indexes
users.create_index('email',    unique=True)
users.create_index('username', unique=True)

print('✅  MongoDB connected')

# ── Helper: sign JWT ────────────────────────
def sign_token(user_id: str) -> str:
    payload = {
        'id':  user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

# ── Helper: serialize user doc ──────────────
def serialize_user(user: dict) -> dict:
    return {
        '_id':       str(user['_id']),
        'username':  user['username'],
        'email':     user['email'],
        'createdAt': user.get('createdAt', datetime.now(timezone.utc)).isoformat()
    }

# ── Auth middleware (decorator) ─────────────
def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'message': 'No token provided.'}), 401
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user_id = payload['id']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid or expired token.'}), 401
        return f(*args, **kwargs)
    return decorated

# ── Serve index.html at root ────────────────
@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

# ── POST /api/auth/register ─────────────────
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}

    username = (data.get('username') or '').strip()
    email    = (data.get('email')    or '').strip().lower()
    password =  data.get('password') or ''

    if not username or not email or not password:
        return jsonify({'message': 'All fields are required.'}), 400
    if len(username) < 3:
        return jsonify({'message': 'Username must be at least 3 characters.'}), 400
    if len(password) < 8:
        return jsonify({'message': 'Password must be at least 8 characters.'}), 400

    # Check duplicates
    if users.find_one({'$or': [{'email': email}, {'username': username}]}):
        return jsonify({'message': 'Username or email already in use.'}), 409

    # Hash password
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))

    try:
        result = users.insert_one({
            'username':  username,
            'email':     email,
            'password':  hashed.decode('utf-8'),   # store as string
            'createdAt': datetime.now(timezone.utc)
        })
    except DuplicateKeyError:
        return jsonify({'message': 'Username or email already in use.'}), 409

    user_id = str(result.inserted_id)
    print(f'✅ Registered: {email}')

    return jsonify({
        'message': 'Account created successfully.',
        'token':   sign_token(user_id),
        'user':    {'id': user_id, 'username': username, 'email': email}
    }), 201

# ── POST /api/auth/login ────────────────────
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}

    email    = (data.get('email')    or '').strip().lower()
    password =  data.get('password') or ''

    if not email or not password:
        return jsonify({'message': 'Email and password are required.'}), 400

    user = users.find_one({'email': email})

    if not user:
        print(f'❌ Login failed — no user found for: {email}')
        return jsonify({'message': 'Invalid email or password.'}), 401

    password_match = bcrypt.checkpw(
        password.encode('utf-8'),
        user['password'].encode('utf-8')
    )
    print(f'🔑 Login attempt: {email} | match: {password_match}')

    if not password_match:
        return jsonify({'message': 'Invalid email or password.'}), 401

    return jsonify({
        'message': 'Login successful.',
        'token':   sign_token(str(user['_id'])),
        'user':    {'id': str(user['_id']), 'username': user['username'], 'email': user['email']}
    })

# ── GET /api/auth/me (protected) ───────────
@app.route('/api/auth/me', methods=['GET'])
@auth_required
def me():
    user = users.find_one({'_id': ObjectId(request.user_id)})
    if not user:
        return jsonify({'message': 'User not found.'}), 404
    return jsonify(serialize_user(user))

# ── Start server ────────────────────────────
if __name__ == '__main__':
    print(f'🚀  Server running on http://localhost:{PORT}')
    app.run(port=PORT, debug=True)