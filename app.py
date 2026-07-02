import os
import time
import sys
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# ==================== CẤU HÌNH THÔNG TIN API ====================
API_KEY = "TVOlPyMlopjjxFd1KRXVF0e2na6IlIll"
API_SECRET = "lHmbOhuIjFtqw2mXa5OunKLQ9FHDiAEb"
FACESET_OUTER_ID = "registered_face"
AI_API_URL = "https://api-us.faceplusplus.com/facepp/v3/search"
# ================================================================

# Khởi tạo thư mục và database
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

@app.route('/api/recognize', methods=['POST'])
def handle_esp32_request():
    if 'image' not in request.files:
        print("Lỗi: ESP32 gửi request nhưng không kèm dữ liệu ảnh.")
        return jsonify({'match': False, 'message': 'No image file found'}), 400
    
    file = request.files['image']
    img_bytes = file.read()
    print(f"Nhận được ảnh từ ESP32-CAM (Kích thước: {len(img_bytes)} bytes). Đang xử lý...")
    
    # Lưu ảnh xuống ổ đĩa
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
        print("Đang gửi ảnh lên Face++ Cloud để phân tích...")
        response = requests.post(AI_API_URL, data=payload, files=files)
        
        if response.status_code == 200:
            ai_result = response.json()
            
            if 'results' in ai_result and len(ai_result['results']) > 0:
                highest_confidence = ai_result['results'][0]['confidence']
                print(f"Kết quả phân tích AI: Độ trùng khớp cao nhất đạt {highest_confidence}%")
                
                if highest_confidence > 75.0:
                    # Lấy user_id từ API (là chuỗi Hex của tên) và giải mã lại thành tên gốc
                    user_id_hex = ai_result['results'][0].get('user_id', '')
                    person_name = "Chủ nhà"
                    if user_id_hex:
                        try:
                            person_name = bytes.fromhex(user_id_hex).decode('utf-8')
                        except:
                            person_name = user_id_hex
                    
                    print(f">>> XÁC THỰC THÀNH CÔNG: Nhận diện thành viên {person_name}! Gửi lệnh mở cửa.")
                    save_history(web_filepath, 'success', highest_confidence, f'Unlock ({person_name})')
                    return jsonify({'match': True, 'message': 'Unlock'})
                else:
                    print(">>> XÁC THỰC THẤT BẠI: Phát hiện người lạ. Cửa tiếp tục khóa.")
                    save_history(web_filepath, 'failed', highest_confidence, 'Lock (Người lạ)')
                    return jsonify({'match': False, 'message': 'Lock (Stranger)'})
            else:
                print(">>> CẢNH BÁO: Ảnh chụp không phát hiện ra khuôn mặt nào.")
                save_history(web_filepath, 'failed', 0, 'Không tìm thấy khuôn mặt')
                return jsonify({'match': False, 'message': 'Lock (No face detected)'})
                
        else:
            print(f"Lỗi kết nối Face++ API: Mã phản hồi {response.status_code}")
            print(response.text)
            save_history(web_filepath, 'error', 0, 'API Error')
            return jsonify({'match': False, 'message': 'AI Server Error'}), 500
             
    except Exception as e:
        print(f"Lỗi hệ thống Server: {str(e)}")
        save_history(web_filepath, 'error', 0, f'Server Error: {str(e)}')
        return jsonify({'match': False, 'message': f'Server internal error: {str(e)}'}), 500

if __name__ == '__main__':
    print("=== SERVER TRUNG CHUYỂN AI & WEB DASHBOARD ĐANG CHẠY ===")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)