import requests

VERCEL_PROXY_URL = "https://video-ai-engine.vercel.app/api/gemini"
DRIVE_VIDEO_URL = "https://drive.google.com/file/d/1LTyOUo-vP2kEvGjrE4wbDK09xKZVeaFR/view?usp=sharing"

payload = {
    "prompt": "Опиши подробно, что происходит на этом видео.",
    "videoUrl": DRIVE_VIDEO_URL
}

print("Отправка ссылки с Google Диска на Vercel Proxy...")
try:
    response = requests.post(VERCEL_PROXY_URL, json=payload, timeout=180)
    print(f"Статус ответа: {response.status_code}")
    
    if response.status_code == 200:
        print("\n--- Успешный ответ от Gemini ---")
        print(response.json().get("text"))
    else:
        print("Ошибка от прокси:", response.text)

except Exception as e:
    print(f"Ошибка соединения: {e}")
