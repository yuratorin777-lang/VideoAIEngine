import os
import requests
import base64

# 1. Замени URL на твою реальную ссылку из Vercel Dashboard
VERCEL_PROXY_URL = "https://your-project-name.vercel.app/api/gemini"

# 2. Указываем файл .MOV
VIDEO_PATH = "test_video.mov"  # Или любое другое имя твоего .mov файла

def test_video_analysis():
    if not os.path.exists(VIDEO_PATH):
        print(f"Ошибка: Файл {VIDEO_PATH} не найден в папке проекта!")
        return

    print("1. Чтение и кодирование .MOV видеофайла...")
    with open(VIDEO_PATH, "rb") as f:
        video_bytes = f.read()
        video_b64 = base64.b64encode(video_bytes).decode('utf-8')

    print("2. Отправка запроса на Vercel Proxy...")
    payload = {
        "prompt": "Опиши подробно, что происходит на этом видео.",
        "fileData": {
            "mimeType": "video/quicktime",  # Важно: для .mov используем video/quicktime
            "data": video_b64
        }
    }

    try:
        response = requests.post(VERCEL_PROXY_URL, json=payload, timeout=60)
        
        print(f"Статус ответа: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("\n--- Ответ от Gemini ---")
            print(result.get("text") or result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text"))
        else:
            print("Ошибка от прокси:", response.text)

    except Exception as e:
        print(f"Ошибка соединения: {e}")

if __name__ == "__main__":
    test_video_analysis()