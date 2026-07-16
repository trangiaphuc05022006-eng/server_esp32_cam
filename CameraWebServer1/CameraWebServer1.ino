#include <Arduino.h>
#include <esp_camera.h>

// CẤU HÌNH CHÂN CAMERA AI THINKER
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

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n--- KIỂM TRA CAMERA CÔ LẬP ---");

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
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
  
  config.xclk_freq_hz = 10000000;  
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 15;
  config.fb_count = 1; 
  config.fb_location = CAMERA_FB_IN_PSRAM; 

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("KHOI TAO CAMERA THAT BAI: 0x%x\n", err);
    while(1);
  }
  Serial.println("Phần cứng Camera khởi tạo: OK!");
}

void loop() {
  Serial.print("Đang bấm máy chụp... ");
  unsigned long start = millis();
  
  camera_fb_t *fb = esp_camera_fb_get();
  
  if (!fb) {
    Serial.printf("THẤT BẠI! Mất %ld ms (Timeout kẹt DMA)\n", millis() - start);
  } else {
    Serial.printf("THÀNH CÔNG! Lấy được ảnh dung lượng: %d bytes trong %ld ms\n", fb->len, millis() - start);
    esp_camera_fb_return(fb); // Trả bộ đệm
  }
  
  delay(2000); // Thử lại sau mỗi 2 giây
}