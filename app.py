import os
import time
import sys
import sqlite3
import requests
import re
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

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

# ==================== API CONFIGURATION ====================
API_KEY = "TVOlPyMlopjjxFd1KRXVF0e2na6IlIll"
API_SECRET = "lHmbOhuIjFtqw2mXa5OunKLQ9FHDiAEb"
FACESET_OUTER_ID = "registered_face"
AI_API_URL = "https://api-us.faceplusplus.com/facepp/v3/search"
# ================================================================

# Track ESP32-CAM last connection time
last_esp32_ping = None

# Initialize directory and database
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_FILE = 'history.db'

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

def save_history(image_path, status, confidence, message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO scan_history (timestamp, image_path, status, confidence, message) VALUES (?, ?, ?, ?, ?)',
              (timestamp, image_path, status, confidence, message))
    conn.commit()
    conn.close()

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
        history_list.append({
            'id': row[0],
            'timestamp': row[1],
            'image_path': row[2],
            'status': row[3],
            'confidence': row[4],
            'message': row[5]
        })
    return jsonify(history_list)

@app.route('/api/status')
def get_status():
    global last_esp32_ping
    
    # Check if running on Render (Render sets the RENDER environment variable)
    is_render = os.environ.get('RENDER') == 'true'
    server_status = "Online (Render)" if is_render else "Online (Local/Other)"
    
    esp32_status = "Offline"
    if last_esp32_ping:
        time_since_last_ping = time.time() - last_esp32_ping
        if time_since_last_ping < 25: # 25 seconds
            esp32_status = "Online"
            
    return jsonify({
        'server_status': server_status,
        'esp32_cam_status': esp32_status,
        'last_esp32_ping': datetime.fromtimestamp(last_esp32_ping).strftime("%Y-%m-%d %H:%M:%S") if last_esp32_ping else "Never"
    })

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
        print("Error: ESP32 sent request but no image data included.")
        return jsonify({'match': False, 'message': 'No image file found'}), 400
    
    file = request.files['image']
    img_bytes = file.read()
    print(f"Received image from ESP32-CAM (Size: {len(img_bytes)} bytes). Processing...")
    
    # Save image to disk
    filename = f"capture_{int(time.time())}.jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, 'wb') as f:
        f.write(img_bytes)
        
    web_filepath = f"/{UPLOAD_FOLDER}/{filename}".replace('\\', '/')
    
    payload = {
        'api_key': API_KEY,
        'api_secret': API_SECRET,
        'outer_id': FACESET_OUTER_ID
    }
    files = {
        'image_file': img_bytes
    }
    
    try:
        print("Sending image to Face++ Cloud for analysis...")
        response = requests.post(AI_API_URL, data=payload, files=files)
        
        if response.status_code == 200:
            ai_result = response.json()
            
            if 'results' in ai_result and len(ai_result['results']) > 0:
                highest_confidence = ai_result['results'][0]['confidence']
                print(f"AI Analysis Result: Highest match rate is {highest_confidence}%")
                
                if highest_confidence > 75.0:
                    # Get user_id from API (Hex string of name) and decode back to original name
                    user_id_hex = ai_result['results'][0].get('user_id', '')
                    person_name = "Owner"
                    if user_id_hex:
                        try:
                            person_name = bytes.fromhex(user_id_hex).decode('utf-8')
                            person_name = remove_vietnamese_accents(person_name)
                        except:
                            person_name = user_id_hex
                    
                    print(f">>> AUTHENTICATION SUCCESSFUL: Member {person_name} recognized! Sending unlock command.")
                    save_history(web_filepath, 'success', highest_confidence, f'Unlock ({person_name})')
                    return jsonify({'match': True, 'message': 'Unlock'})
                else:
                    print(">>> AUTHENTICATION FAILED: Stranger detected. Door continues to be locked.")
                    save_history(web_filepath, 'failed', highest_confidence, 'Lock (Stranger)')
                    return jsonify({'match': False, 'message': 'Lock (Stranger)'})
            else:
                print(">>> WARNING: Captured image detected no face.")
                save_history(web_filepath, 'failed', 0, 'No face found')
                return jsonify({'match': False, 'message': 'Lock (No face detected)'})
                
        else:
            print(f"Face++ API connection error: Response code {response.status_code}")
            print(response.text)
            save_history(web_filepath, 'error', 0, 'API Error')
            return jsonify({'match': False, 'message': 'AI Server Error'}), 500
             
    except Exception as e:
        print(f"Server system error: {str(e)}")
        save_history(web_filepath, 'error', 0, f'Server Error: {str(e)}')
        return jsonify({'match': False, 'message': f'Server internal error: {str(e)}'}), 500

if __name__ == '__main__':
    print("=== AI RELAY SERVER & WEB DASHBOARD RUNNING ===")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)