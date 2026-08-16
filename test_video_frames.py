import os
import cv2
import requests
import base64

VERCEL_PROXY_URL = "https://video-ai-engine.vercel.app/api/gemini"
VIDEO_PATH = r"C:\Users\User\Desktop\VideoAIEngine\test_video.mov"

def analyze_video_via_frames():
    if not os.path.exists(VIDEO_PATH):
        print(f"Ошибка: Файл {VIDEO_PATH} не найден!")
        return

    print("1. Извлечение кадров из видео...")
    cap = cv2.VideoCapture(VIDEO_PATH)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Берем 5 ключевых кадров из видео
    frames_to_extract = 5
    step = max(1, total_frames // frames_to_extract)
    
    parts = [{"text": "Ниже представлены ключевые кадры из видеофайла. Опиши подробно, что происходит на видео."}]
    
    count = 0
    extracted = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if count % step == 0 and extracted < frames_to_extract:
            # Уменьшаем размер кадра для легкой передачи
            resized = cv2.resize(frame, (640, 360))
            _, buffer = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            img_b64 = base64.b64encode(buffer).decode('utf-8')
            
            parts.append({
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": img_b64
                }
            })
            extracted += 1
        count += 1
    
    cap.release()
    print(f"Извлечено {extracted} кадров. Отправка на Vercel Proxy...")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts
            }
        ]
    }

    try:
        response = requests.post(VERCEL_PROXY_URL, json=payload, timeout=60)
        print(f"Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n--- Ответ от Gemini через Vercel Proxy ---")
            text_output = result.get("text") or result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text")
            print(text_output if text_output else result)
        else:
            print("Ошибка от прокси:", response.text)

    except Exception as e:
        print(f"Ошибка соединения: {e}")

if __name__ == "__main__":
    analyze_video_via_frames()
