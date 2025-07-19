from flask import Flask, request, jsonify, send_from_directory
import hashlib
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import os

app = Flask(__name__, static_folder="static", template_folder="templates")

# ─── Firebase Credential Path ───────────────────────────────────────────────
cred_path = r"C:\Users\advai\Downloads\chat-app-493a1-firebase-adminsdk-fbsvc-820ec5fabf.json"
print("🧠 Credential Path:", cred_path)
print("📂 File Exists:", os.path.exists(cred_path))

if not os.path.exists(cred_path):
    raise RuntimeError("Missing or invalid GOOGLE_APPLICATION_CREDENTIALS path")

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ─── Helper: Hash Password ──────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# ─── Serve HTML Pages ──────────────────────────────────────────────────────
@app.route('/<page>.html')
def serve_page(page):
    return send_from_directory('.', f"{page}.html")

@app.route("/")
def serve_main():
    return send_from_directory('.', 'login.html')

# ─── API: Sign Up ───────────────────────────────────────────────────────────
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json or {}
    username = data.get('username', '').strip().lower()
    email = data.get('email', '').strip().lower()
    pw = data.get('password', '')
    confirm = data.get('confirm', '')

    if not username or not email or not pw or pw != confirm:
        return jsonify(success=False, message="Missing fields or password mismatch"), 400

    if not email.endswith('@gmail.com'):
        return jsonify(success=False, message="Email must be a Gmail address"), 400

    user_ref = db.collection('users').document(username)
    if user_ref.get().exists:
        return jsonify(success=False, message="Username already exists"), 409

    user_ref.set({
        'email': email,
        'password': hash_pw(pw),
        'friends': []
    })
    return jsonify(success=True, message="User registered")

# ─── API: Log In ────────────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')

    if not username or not password:
        return jsonify(success=False, message="Username and password required"), 400

    doc = db.collection("users").document(username).get()
    if not doc.exists:
        return jsonify(success=False, message="Username not found"), 404

    stored_pw = doc.to_dict().get("password")
    if hash_pw(password) != stored_pw:
        return jsonify(success=False, message="Incorrect password"), 401

    return jsonify(success=True, message="Login successful")

# ─── API: Search Users ──────────────────────────────────────────────────────
@app.route('/api/search_user', methods=['GET'])
def search_user():
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify(found=False), 400

    doc = db.collection('users').document(query).get()
    return jsonify(found=doc.exists, username=query)

# ─── API: Add Friend ────────────────────────────────────────────────────────
@app.route('/api/add_friend', methods=['POST'])
def add_friend():
    data = request.json or {}
    me = data.get('me', '').strip().lower()
    them = data.get('them', '').strip().lower()

    if me == them:
        return jsonify(success=False, message="Cannot friend yourself"), 400

    my_ref = db.collection('users').document(me)
    their_ref = db.collection('users').document(them)
    if not my_ref.get().exists or not their_ref.get().exists:
        return jsonify(success=False, message="User not found"), 404

    my_ref.update({'friends': firestore.ArrayUnion([them])})
    their_ref.update({'friends': firestore.ArrayUnion([me])})
    return jsonify(success=True)

# ─── API: Remove Friend ─────────────────────────────────────────────────────
@app.route('/api/remove_friend', methods=['POST'])
def remove_friend():
    data = request.json or {}
    me = data.get('me', '').strip().lower()
    them = data.get('them', '').strip().lower()

    db.collection('users').document(me).update({'friends': firestore.ArrayRemove([them])})
    db.collection('users').document(them).update({'friends': firestore.ArrayRemove([me])})
    return jsonify(success=True)

# ─── API: Get Friends ───────────────────────────────────────────────────────
@app.route('/api/get_friends', methods=['GET'])
def get_friends():
    me = request.args.get('me', '').strip().lower()
    doc = db.collection('users').document(me).get()
    if not doc.exists:
        return jsonify(success=False, message="User not found"), 404
    friends = doc.to_dict().get('friends', [])
    return jsonify(success=True, friends=friends)

# ─── API: Send Message ──────────────────────────────────────────────────────
@app.route('/api/send_message', methods=['POST'])
def send_message():
    data = request.json or {}
    sender = data.get('from', '').strip().lower()
    receiver = data.get('to', '').strip().lower()
    text = data.get('message', '').strip()
    if not sender or not receiver or not text:
        return jsonify(success=False), 400

    convo_id = "__".join(sorted([sender, receiver]))
    ts = datetime.utcnow().isoformat()
    db.collection('conversations') \
      .document(convo_id) \
      .collection('messages') \
      .add({'sender': sender, 'text': text, 'timestamp': ts})
    return jsonify(success=True, timestamp=ts)

# ─── API: Fetch Messages ────────────────────────────────────────────────────
@app.route('/api/get_messages', methods=['GET'])
def get_messages():
    me = request.args.get('me', '').strip().lower()
    them = request.args.get('them', '').strip().lower()
    convo_id = "__".join(sorted([me, them]))
    msgs_ref = db.collection('conversations') \
                 .document(convo_id) \
                 .collection('messages') \
                 .order_by('timestamp')
    docs = msgs_ref.stream()
    messages = [
        {
            'sender': doc.to_dict()['sender'],
            'text': doc.to_dict()['text'],
            'timestamp': doc.to_dict()['timestamp']
        }
        for doc in docs
    ]
    return jsonify(success=True, messages=messages)

# ─── Run App ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)