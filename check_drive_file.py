import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


SERVICE_ACCOUNT_PATH = "service_account.json"
PROCESSED_FOLDER_ID = "1zKRnJmUorf9PQB5ycJ0UsUd_O9yARWD0"
TARGET_NAME = "document_5199710952995467039.mp4"


def main():
    scopes = ["https://www.googleapis.com/auth/drive"]

    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_PATH,
        scopes=scopes,
    )

    service = build(
        "drive",
        "v3",
        credentials=credentials,
    )

    query = (
        f"'{PROCESSED_FOLDER_ID}' in parents "
        f"and name = '{TARGET_NAME}' "
        f"and trashed = false"
    )

    response = (
        service.files()
        .list(
            q=query,
            fields="files(id,name,mimeType,size,parents,trashed)",
            pageSize=100,
        )
        .execute()
    )

    files = response.get("files", [])

    print()
    print("=" * 60)
    print(" DRIVE FILE CHECK")
    print("=" * 60)

    if not files:
        print("❌ Файл не найден через Drive API")
        return

    for file in files:
        print(f"Name:     {file.get('name')}")
        print(f"ID:       {file.get('id')}")
        print(f"MIME:     {file.get('mimeType')}")
        print(f"Size:     {file.get('size')}")
        print(f"Parents:  {file.get('parents')}")
        print(f"Trashed:  {file.get('trashed')}")
        print("-" * 60)


if __name__ == "__main__":
    main()