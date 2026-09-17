import os
import requests
import base64

# Актуальный URL твоего прокси на Vercel
VERCEL_PROXY_URL = "https://video-ai-engine.vercel.app/api/gemini"

# Путь к видеофайлу в корневой папке VideoAIEngine
VIDEO_PATH = r"C:\Users\User\Desktop\VideoAIEngine\test_video.mov"

def test_video_analysis():
    if not os.path.exists(VIDEO_PATH):
        print(f"Ошибка: Файл не найден по пути: {VIDEO_PATH}")
        print("Убедись, что файл test_video.mov лежит в папе C:\\Users\\User\\Desktop\\VideoAIEngine\\")
        return

    print(f"1. Чтение и кодирование файла {VIDEO_PATH}...")
    with open(VIDEO_PATH, "rb") as f:
        video_bytes = f.read()
        video_b64 = base64.b64encode(video_bytes).decode('utf-8')

    print("2. Отправка запроса на Vercel Proxy (https://video-ai-engine.vercel.app/api/gemini)...")
    payload = {
        "prompt": "Опиши подробно, что происходит на этом видео.",
        "fileData": {
            "mimeType": "video/quicktime",
            "data": video_b64
        }
    }

    try:
        response = requests.post(VERCEL_PROXY_URL, json=payload, timeout=90)
        print(f"Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n--- Успешный ответ от Gemini ---")
            text_output = result.get("text") or result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text")
            print(text_output if text_output else result)
        else:
            print("Ошибка от прокси:", response.text)

    except Exception as e:
        print(f"Ошибка соединения: {e}")

if __name__ == "__main__":
    test_video_analysis()
