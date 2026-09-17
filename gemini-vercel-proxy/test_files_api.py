import os
from dotenv import load_dotenv
from google import genai

# Загружаем переменные из .env файла в корне VideoAIEngine
env_path = r"C:\Users\User\Desktop\VideoAIEngine\.env"
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print(f"Ошибка: Не удалось найти GEMINI_API_KEY в файле {env_path}!")
    exit(1)

client = genai.Client(api_key=api_key)
VIDEO_PATH = r"C:\Users\User\Desktop\VideoAIEngine\test_video.mov"

print("1. Загрузка видео напрямую в Google File API...")
video_file = client.files.upload(file=VIDEO_PATH)
print(f"Успешно загружено! URI файла: {video_file.uri}")

print("2. Генерация ответа через Gemini 2.5 Flash...")
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        video_file,
        "Опиши подробно, что происходит на этом видео."
    ]
)

print("\n--- Ответ от Gemini ---")
print(response.text)
