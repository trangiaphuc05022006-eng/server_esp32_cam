#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>

// ================= CẤU HÌNH WIFI & SERVER =================
const char* ssid = "Phuc Ngo";
const char* password = "aimabiet126";

// Đã chuyển sang dùng DHCP. Các dòng cấp IP tĩnh đã được vô hiệu hóa để tự động nhận mạng từ hotspot
// IPAddress local_IP(192, 168, 143, 50);      // IP của ESP32
// IPAddress gateway(192, 168, 143, 242);      // Gateway của hotspot
// IPAddress subnet(255, 255, 255, 0);

// Địa chỉ IP Server Dashboard (IP tĩnh của PC)
// Sửa thành đường dẫn thực tế Render cung cấp cho bạn (Lưu ý URL API phải khớp)
const char* server_url = "https://server-esp32-cam.onrender.com/api/recognize";

unsigned long last_capture_time = 0;
const unsigned long cooldown_time = 10000; // 10 giây

unsigned long last_ping_time = 0;
const unsigned long ping_interval = 15000; // 15 giây (Cập nhật trạng thái kết nối lên server)

// ================= ĐỊNH NGHĨA CHÂN (THEO PCB KICAD) =================
#define PIN_RELAY_BASE 12   // R4 -> Transistor 2N2222 -> Mở Relay cửa
#define PIN_LDR        13   // DigitalRead (tránh ADC2 khi WiFi bật)
#define PIN_LED        2    // LED tín hiệu trên PCB (D3)
#define PIN_SDA        14   // I2C SDA cho LCD
#define PIN_SCL        15   // I2C SCL cho LCD

// LCD address (default 0x27, may be 0x3F on some modules)
uint8_t LCD_ADDRESS = 0x27;
LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);

// ================= CẤU HÌNH CAMERA (AI‑THINKER) =================
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

void scanI2C() {
  Serial.println("Scanning I2C bus...");
  byte error, address;
  int nDevices = 0;
  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("Found I2C device at address 0x");
      if (address < 16) Serial.print("0");
      Serial.print(address, HEX);
      Serial.println(" !");
      nDevices++;
      LCD_ADDRESS = address; // use the found address for LCD
    }
  }
  if (nDevices == 0) Serial.println("No I2C devices found");
  else {
    Serial.print("Using LCD address 0x");
    Serial.println(LCD_ADDRESS, HEX);
  }
}

void initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  // Kích thước ảnh xuất ra
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Khởi tạo Camera LỖI: 0x%x\n", err);
  }
}

// ... rest of file unchanged ...




// ================= CẤU HÌNH CAMERA (AI‑THINKER) =================
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22



void sendImageToServer() {
  digitalWrite(PIN_LED, HIGH);                 // bật LED báo đang chụp
  lcd.clear(); lcd.setCursor(0, 0);
  lcd.print("Dang phan tich...");

  // ---- XÓA ẢNH CŨ TRONG BỘ ĐỆM ----
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb) { esp_camera_fb_return(fb); }

  // Lấy ảnh mới nhất
  fb = esp_camera_fb_get();

  if (!fb) {
    Serial.println("Chụp ảnh thất bại do lỗi phần cứng hoặc hết RAM!");
    digitalWrite(PIN_LED, LOW);
    return;
  }

  if (WiFi.status() == WL_CONNECTED) {
    WiFiClientSecure client;
    client.setInsecure(); // Bỏ qua xác minh chứng chỉ SSL
    client.setHandshakeTimeout(20000); // 20s timeout để tránh treo khi handshake với Render
    
    String boundary = "----ESP32CAMBoundary";
    String head = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"image\"; filename=\"capture.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
    String tail = "\r\n--" + boundary + "--\r\n";

    size_t totalLen = head.length() + fb->len + tail.length();
    
    // RẤT QUAN TRỌNG: Dùng PSRAM để chứa ảnh. Vì WiFiClientSecure cần tới ~40KB RAM nội bộ để mã hóa SSL.
    // Nếu dùng malloc thông thường có thể chiếm hết RAM nội bộ khiến SSL bị crash hoặc treo cứng (treo LED).
    uint8_t *buf = (uint8_t *)ps_malloc(totalLen);
    if (!buf) buf = (uint8_t *)malloc(totalLen); // dự phòng
    if (!buf) {
      Serial.println("Hết RAM để tạo Buffer gửi file!");
      esp_camera_fb_return(fb);
      digitalWrite(PIN_LED, LOW);
      return;
    }

    memcpy(buf, head.c_str(), head.length());
    memcpy(buf + head.length(), fb->buf, fb->len);
    memcpy(buf + head.length() + fb->len, tail.c_str(), tail.length());

    int httpResponseCode = 0;
    int retries = 0;
    while (retries <= 3) {
      HTTPClient http;
      http.setTimeout(20000); // 20s timeout chờ Render thức dậy
      http.begin(client, server_url);
      http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
      
      Serial.printf("Đang gửi POST request (Lần %d)...\n", retries + 1);
      httpResponseCode = http.POST(buf, totalLen);
      
      if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.println("Phản hồi từ Server: " + response);

        StaticJsonDocument<200> doc;
        if (!deserializeJson(doc, response)) {
          bool is_match = doc["match"];
          if (is_match) {
            lcd.clear(); lcd.setCursor(0, 0); lcd.print("XAC THUC DUNG!");
            lcd.setCursor(0, 1); lcd.print("MO CUA...");
            digitalWrite(PIN_RELAY_BASE, HIGH);
            delay(3000);
            digitalWrite(PIN_RELAY_BASE, LOW);
          } else {
            lcd.clear(); lcd.setCursor(0, 0); lcd.print("NGUOI LA!");
            lcd.setCursor(0, 1); lcd.print("CUA CAMS VAO");
          }
        }
        http.end();
        break; // Thành công thì thoát vòng lặp retry
      } else {
        Serial.printf("Loi gui du lieu (%s). Đang chờ 4s...\n", http.errorToString(httpResponseCode).c_str());
        lcd.clear(); lcd.setCursor(0, 0); lcd.print("Dang thu lai...");
        http.end(); // BẮT BUỘC PHẢI ĐÓNG KẾT NỐI TRƯỚC KHI RETRY
        
        if (retries < 3) {
            delay(4000); // Chờ 4s cho Render khởi động
        } else {
            lcd.clear(); lcd.print("Loi ket noi Web");
        }
        retries++;
      }
    }
    free(buf);
  }

  // Giải phóng bộ nhớ ảnh
  esp_camera_fb_return(fb);
  digitalWrite(PIN_LED, LOW);
  delay(1500);
  lcd.clear(); lcd.print("He thong san sang");
}

void testServerConnection() {
  Serial.println("========== TEST KET NOI SERVER ==========");
  lcd.clear(); lcd.setCursor(0, 0); lcd.print("Check Server...");
  
  WiFiClientSecure client;
  client.setInsecure(); // Bỏ qua SSL
  client.setHandshakeTimeout(20000);

  HTTPClient http;
  http.setTimeout(20000);
  
  // Dùng link trang chủ để test thử GET request
  String test_url = "https://server-esp32-cam.onrender.com/";
  Serial.println("Dang thu truy cap: " + test_url);
  http.begin(client, test_url);
  
  int httpResponseCode = http.GET();
  
  if (httpResponseCode > 0) {
    Serial.printf(">>> KET NOI THANH CONG! Ma phan hoi: %d\n", httpResponseCode);
    lcd.clear(); lcd.setCursor(0, 0); lcd.print("Server OK!");
    lcd.setCursor(0, 1); lcd.print("HTTP: "); lcd.print(httpResponseCode);
  } else {
    Serial.printf(">>> KET NOI THAT BAI! Ma loi: %s\n", http.errorToString(httpResponseCode).c_str());
    lcd.clear(); lcd.setCursor(0, 0); lcd.print("Server FAILED!");
    lcd.setCursor(0, 1); lcd.print("Loi ket noi");
  }
  
  http.end();
  Serial.println("=========================================");
  delay(4000);
}

void pingServer() {
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClientSecure client;
    client.setInsecure();
    client.setHandshakeTimeout(10000);
    
    HTTPClient http;
    http.setTimeout(10000);
    
    String ping_url = "https://server-esp32-cam.onrender.com/api/ping";
    http.begin(client, ping_url);
    http.GET();
    http.end();
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("--- ESP32 CAM START ---");

  pinMode(PIN_RELAY_BASE, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_LDR, INPUT);          // Đọc LDR bằng Digital

  digitalWrite(PIN_RELAY_BASE, LOW);
  digitalWrite(PIN_LED, LOW);

  Wire.begin(PIN_SDA, PIN_SCL);
  lcd.init(); lcd.backlight();
  lcd.setCursor(0, 0); lcd.print("Dang khoi dong...");

  // Đã bỏ cấu hình IP tĩnh để thiết bị tự động lấy IP (DHCP) từ mạng WiFi
  
// Scan I2C bus to find LCD address (helps if default 0x27 fails)
scanI2C();
// If scan finds a different address, edit the LCD_ADDRESS constant above accordingly.
// Re-initialize LCD with the (possibly updated) address.
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Ket noi WiFi: ");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  Serial.print("WiFi ket noi thanh cong! IP: ");
  Serial.println(WiFi.localIP());
  lcd.setCursor(0, 1); lcd.print("Wifi Connected!");
  delay(1000);

  // Test xem ESP32 có thực sự nối được ra Internet và tới Render không
  testServerConnection();

  initCamera();
  lcd.clear(); lcd.print("He thong san sang");
}

void loop() {
  // Đọc trạng thái LDR (LOW = bị che)
  int ldr_state = digitalRead(PIN_LDR);
  unsigned long current_time = millis();

  // Gửi ping định kỳ để server biết ESP32 vẫn đang online
  if (current_time - last_ping_time >= ping_interval) {
    last_ping_time = current_time;
    pingServer();
  }

  if (ldr_state == LOW) {
    if (current_time - last_capture_time >= cooldown_time) {
      Serial.println("Phat hien bong toi! Tien hanh chup hinh...");
      last_capture_time = current_time;
      sendImageToServer();
    }
  }
  delay(100);
}
