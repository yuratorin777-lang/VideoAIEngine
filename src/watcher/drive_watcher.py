import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

class DriveWatcher:
    def __init__(self, service_account_path: str = "service_account.json"):
        scopes = ['https://www.googleapis.com/auth/drive']
        
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(f"Файл ключа не найден по пути: {service_account_path}")
            
        creds = Credentials.from_service_account_file(service_account_path, scopes=scopes)
        self.service = build('drive', 'v3', credentials=creds)

    def get_unprocessed_videos(self, folder_id: str) -> list:
        """
        Ищет файлы видео в указанной папке Google Диска.
        Формирует прямую ссылку на скачивание для каждого файла.
        """
        query = f"'{folder_id}' in parents and mimeType contains 'video/' and trashed = false"
        results = self.service.files().list(
            q=query,
            fields="files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink)",
            pageSize=10
        ).execute()
        
        files = results.get('files', [])
        video_list = []

        for f in files:
            file_id = f.get('id')
            # Прямая ссылка на скачивание для Vercel Proxy (как в test_gdrive.py)
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            
            video_list.append({
                'id': file_id,
                'name': f.get('name'),
                'mimeType': f.get('mimeType'),
                'webViewLink': download_url,  # Передаем прямую ссылку
                'original_link': f.get('webViewLink')
            })
            
        return video_list

    def scan_input_folder(self, folder_id: str) -> list:
        """Совместимость с pipeline.py"""
        return self.get_unprocessed_videos(folder_id)

    def move_file(self, file_id: str, current_folder_id: str, target_folder_id: str):
        """
        Перемещает файл из одной папки Google Диска в другую.
        """
        try:
            file = self.service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents', []))
            
            self.service.files().update(
                fileId=file_id,
                addParents=target_folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            return True
        except Exception as e:
            print(f"Ошибка при перемещении файла {file_id}: {e}")
            return False
