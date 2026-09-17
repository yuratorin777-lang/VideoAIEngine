import os
import sys
import time
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from src.watcher.drive_watcher import DriveWatcher
from src.gemini.vercel_client import VercelGatewayClient
from src.library.passport_store import PassportStore

# Импортируем ПОЛНУЮ схему промпта из pipeline.py
from src.core.pipeline import PROMPT_SCHEMA

# ID папок Google Диска
INPUT_FOLDER_ID = "12upEDD5YrquwJdzMm5l1_LmGzhmnXhV9"
PROCESSED_FOLDER_ID = "1zKRnJmUorf9PQB5ycJ0UsUd_O9yARWD0"
ERROR_FOLDER_ID = "1y7y22C9VuSURKALbZdUJQFSf9lqe__cq"

VERCEL_PROXY_URL = "https://video-ai-engine.vercel.app/api/gemini"


def main():
    watcher = DriveWatcher(service_account_path="service_account.json")
    client = VercelGatewayClient(proxy_url=VERCEL_PROXY_URL)
    store = PassportStore()

    print("🔍 Сканирование Google Диска...")

    # Блок автоповторов (Retry) для защиты от сбоев соединения
    max_retries = 5
    videos = None

    for attempt in range(1, max_retries + 1):
        try:
            videos = watcher.get_unprocessed_videos(INPUT_FOLDER_ID)
            break  # Если запрос успешный, выходим из цикла
        except Exception as e:
            print(f"⚠️ Сбой сети при сканировании Диска ({e}).")
            if attempt < max_retries:
                print(f"🔄 Пробуем снова через 3 секунды... (Попытка {attempt}/{max_retries})")
                time.sleep(3)
            else:
                print(f"❌ Не удалось подключиться к Google Диску после {max_retries} попыток.")
                return

    if not videos:
        print("⏸ Нет новых видео в папке INPUT.")
        return

    for video in videos:
        file_id = video['id']
        file_name = video['name']
        drive_url = video.get('webViewLink') or video.get('webContentLink')

        print(f"\n🎬 Обработка: {file_name} ({file_id})")
        print("📡 Отправка ссылки и PROMPT_SCHEMA на Vercel Proxy...")

        try:
            # Передаем полную PROMPT_SCHEMA из pipeline.py вместо короткой строки
            response = client.request_video_analysis(drive_url=drive_url, prompt=PROMPT_SCHEMA)
        except Exception as e:
            response = {"success": False, "error": str(e)}

        if response.get("success"):
            passport_data = response.get("data")
            
            video_event = {
                "file_id": file_id,
                "filename": file_name,
            }

            passport_path = store.save_passport(
                video_event=video_event,
                raw_ai_response=passport_data
            )
            print(f"💾 Паспорт успешно сохранен: {passport_path}")

            watcher.move_file(file_id, INPUT_FOLDER_ID, PROCESSED_FOLDER_ID)
            print("📦 Файл перемещен в PROCESSED")
        else:
            error_msg = response.get("error", "Неизвестная ошибка")
            print(f"❌ Ошибка обработки {file_name}: {error_msg}")

            watcher.move_file(file_id, INPUT_FOLDER_ID, ERROR_FOLDER_ID)
            print("⚠️ Файл перемещен в ERROR")


if __name__ == "__main__":
    main()