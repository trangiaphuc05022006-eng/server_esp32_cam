import os
import time
import sqlite3
import requests
import re
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# ==================== CẤU HÌNH API ====================
API_KEY = "TVOlPyMlopjjxFd1KRXVF0e2na6IlIll"
API_SECRET = "lHmbOhuIjFtqw2mXa5OunKLQ9FHDiAEb"
FACESET_OUTER_ID = "registered_face"
AI_API_URL = "https://api-us.faceplusplus.com/facepp/v3/search"

# ==================== KHỞI TẠO ====================
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_FILE = 'history.db'
last_esp32_ping = None

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            image_path TEXT,
            status TEXT,
            confidence REAL,
            message TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def remove_vietnamese_accents(s):
    s = re.sub(r'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', s)
    s = re.sub(r'[ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴ]', 'A', s)
    s = re.sub(r'[èéẹẻẽêềếệểễ]', 'e', s)
    s = re.sub(r'[ÈÉẸẺẼÊỀẾỆỂỄ]', 'E', s)
    s = re.sub(r'[òóọỏõôồốộổỗơờớợởỡ]', 'o', s)
    s = re.sub(r'[ÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ]', 'O', s)
    s = re.sub(r'[ìíịỉĩ]', 'i', s)
    s = re.sub(r'[ÌÍỊỈĨ]', 'I', s)
    s = re.sub(r'[ùúụủũưừứựửữ]', 'u', s)
    s = re.sub(r'[ÙÚỤỦŨƯỪỨỰỬỮ]', 'U', s)
    s = re.sub(r'[ỳýỵỷỹ]', 'y', s)
    s = re.sub(r'[ỲÝỴỶỸ]', 'Y', s)
    s = re.sub(r'[đ]', 'd', s)
    s = re.sub(r'[Đ]', 'D', s)
    return s

def save_history(image_path, status, confidence, message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    vn_tz = timezone(timedelta(hours=7))
    timestamp = datetime.now(vn_tz).strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO scan_history (timestamp, image_path, status, confidence, message) VALUES (?, ?, ?, ?, ?)',
              (timestamp, image_path, status, confidence, message))
    conn.commit()
    conn.close()

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/history')
def get_history():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM scan_history ORDER BY id DESC LIMIT 50')
    rows = c.fetchall()
    conn.close()
    history_list = []
    for row in rows:
        history_list.append({'id': row[0], 'timestamp': row[1], 'image_path': row[2], 'status': row[3], 'confidence': row[4], 'message': row[5]})
    return jsonify(history_list)

@app.route('/api/status')
def get_status():
    global last_esp32_ping
    esp32_status = "Offline"
    if last_esp32_ping and (time.time() - last_esp32_ping < 30):
        esp32_status = "Online"
    return jsonify({'server_status': 'Online', 'esp32_cam_status': esp32_status})

@app.route('/api/ping', methods=['GET'])
def handle_ping():
    global last_esp32_ping
    last_esp32_ping = time.time()
    return jsonify({"status": "ok"})

@app.route('/api/recognize', methods=['POST'])
def handle_esp32_request():
    global last_esp32_ping
    last_esp32_ping = time.time()
    
    if 'image' not in request.files:
        return jsonify({'match': False, 'message': 'No image'}), 400
    
    file = request.files['image']
    img_bytes = file.read()
    filename = f"capture_{int(time.time())}.jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, 'wb') as f:
        f.write(img_bytes)
    web_filepath = f"/{UPLOAD_FOLDER}/{filename}".replace('\\', '/')
    
    payload = {'api_key': API_KEY, 'api_secret': API_SECRET, 'outer_id': FACESET_OUTER_ID}
    files = {'image_file': img_bytes}
    
    try:
        response = requests.post(AI_API_URL, data=payload, files=files)
        if response.status_code == 200:
            ai_result = response.json()
            if 'results' in ai_result and len(ai_result['results']) > 0:
                highest_confidence = ai_result['results'][0]['confidence']
                if highest_confidence > 75.0:
                    user_id_hex = ai_result['results'][0].get('user_id', '')
                    person_name = "Owner"
                    try:
                        person_name = remove_vietnamese_accents(bytes.fromhex(user_id_hex).decode('utf-8'))
                    except: pass
                    save_history(web_filepath, 'success', highest_confidence, f'Unlock ({person_name})')
                    return jsonify({'match': True, 'message': 'Unlock'})
                else:
                    save_history(web_filepath, 'failed', highest_confidence, 'Stranger')
                    return jsonify({'match': False, 'message': 'Lock: Stranger'})
            else:
                save_history(web_filepath, 'failed', 0, 'No face')
                return jsonify({'match': False, 'message': 'Lock: No face'})
        else:
            error_text = response.text[:25]
            save_history(web_filepath, 'error', 0, f'API: {error_text}')
            return jsonify({'match': False, 'message': error_text}), 500
             
    except Exception as e:
        save_history(web_filepath, 'error', 0, 'System Error')
        return jsonify({'match': False, 'message': 'Server Error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)