import os
import time
import sqlite3
import requests
import re
import pymongo
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# ==================== CẤU HÌNH API ====================
API_KEY = "TVOlPyMlopjjxFd1KRXVF0e2na6IlIll"
API_SECRET = "lHmbOhuIjFtqw2mXa5OunKLQ9FHDiAEb"
FACESET_OUTER_ID = "registered_face"
AI_API_URL = "https://api-us.faceplusplus.com/facepp/v3/search"

# ==================== KẾT NỐI DB & STORAGE ====================
# MongoDB
MONGO_URI = "mongodb+srv://trangiaphuc05022006_db_user:aimabiet123@esp32cam.xbh8hsn.mongodb.net/?appName=ESP32CAM"
mongo_client = pymongo.MongoClient(MONGO_URI)
db = mongo_client["esp32cam_db"]
history_collection = db["scan_history"]

# Supabase
SUPABASE_URL = "https://fydailqktdhjtxxvsbum.supabase.co"
SUPABASE_KEY = "sb_publishable_uQRNrQvF6kXcio8aqlb8Jg_dT0j46xA"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
SUPABASE_BUCKET = "images"  # Bạn cần tạo bucket tên "images" và set là Public trên Supabase

# ==================== KHỞI TẠO ====================
last_esp32_ping = None

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

def save_history(image_path, status, confidence, message, latency=0):
    vn_tz = timezone(timedelta(hours=7))
    timestamp = datetime.now(vn_tz)
    
    # Lưu vào MongoDB
    record = {
        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "date": timestamp.strftime("%Y-%m-%d"), # Lưu thêm trường date để tiện query
        "image_path": image_path,
        "status": status,
        "confidence": confidence,
        "message": message,
        "latency": latency
    }
    history_collection.insert_one(record)

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/history')
def get_history():
    selected_date = request.args.get('date')
    query = {}
    if selected_date:
        query = {"date": selected_date}
    
    # Lấy 50 record mới nhất của ngày đó (hoặc tất cả nếu ko truyền)
    records = list(history_collection.find(query).sort("_id", -1).limit(50))
    
    history_list = []
    for row in records:
        history_list.append({
            'id': str(row['_id']), 
            'timestamp': row['timestamp'], 
            'image_path': row['image_path'], 
            'status': row['status'], 
            'confidence': row['confidence'], 
            'message': row['message'],
            'latency': row.get('latency', 0)
        })
    return jsonify(history_list)

@app.route('/api/history/dates')
def get_history_dates():
    # Lấy danh sách các ngày đã có log (distinct date)
    dates = history_collection.distinct("date")
    # Sắp xếp giảm dần (ngày mới nhất lên đầu)
    dates.sort(reverse=True)
    return jsonify(dates)

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
    start_process_time = time.time()
    global last_esp32_ping
    last_esp32_ping = time.time()
    
    if 'image' not in request.files:
        return jsonify({'match': False, 'message': 'No image'}), 400
    
    file = request.files['image']
    img_bytes = file.read()
    filename = f"capture_{int(time.time())}.jpg"
    
    # Đẩy ảnh lên Supabase Storage
    try:
        supabase.storage.from_(SUPABASE_BUCKET).upload(filename, img_bytes, {"content-type": "image/jpeg"})
        web_filepath = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
    except Exception as e:
        print("Lỗi upload ảnh Supabase:", e)
        # Fallback lại URL trống nếu lỗi để không chết cả ứng dụng
        web_filepath = ""

    payload = {'api_key': API_KEY, 'api_secret': API_SECRET, 'outer_id': FACESET_OUTER_ID}
    files = {'image_file': img_bytes}
    
    try:
        response = requests.post(AI_API_URL, data=payload, files=files)
        latency_ms = int((time.time() - start_process_time) * 1000)
        
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
                    save_history(web_filepath, 'success', highest_confidence, f'Unlock ({person_name})', latency_ms)
                    return jsonify({'match': True, 'message': 'Unlock'})
                else:
                    save_history(web_filepath, 'failed', highest_confidence, 'Stranger', latency_ms)
                    return jsonify({'match': False, 'message': 'Lock: Stranger'})
            else:
                save_history(web_filepath, 'failed', 0, 'No face', latency_ms)
                return jsonify({'match': False, 'message': 'Lock: No face'})
        else:
            latency_ms = int((time.time() - start_process_time) * 1000)
            error_text = response.text[:25]
            save_history(web_filepath, 'error', 0, f'API: {error_text}', latency_ms)
            return jsonify({'match': False, 'message': error_text}), 500
             
    except Exception as e:
        latency_ms = int((time.time() - start_process_time) * 1000)
        save_history(web_filepath, 'error', 0, 'System Error', latency_ms)
        return jsonify({'match': False, 'message': 'Server Error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)