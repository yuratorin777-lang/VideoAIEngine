import io
import json
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

SERVICE_ACCOUNT_PATH = BASE_DIR / "service_account.json"

MONTAGE_PLAN_PATH = (
    BASE_DIR
    / "06_COMPOSER"
    / "montage_plan.json"
)

DOWNLOAD_DIR = BASE_DIR / "temp_downloads"


# ============================================================
# GOOGLE DRIVE
# ============================================================

PROCESSED_FOLDER_ID = "1zKRnJmUorf9PQB5ycJ0UsUd_O9yARWD0"

SCOPES = [
    "https://www.googleapis.com/auth/drive"
]


class DriveDownloader:
    """
    Скачивает исходные видео из Google Drive / PROCESSED
    на основании file_id из montage_plan.json.
    """

    def __init__(
        self,
        service_account_path: Path = SERVICE_ACCOUNT_PATH,
        download_dir: Path = DOWNLOAD_DIR,
    ):
        self.service_account_path = Path(service_account_path)
        self.download_dir = Path(download_dir)

        if not self.service_account_path.exists():
            raise FileNotFoundError(
                f"Файл service_account.json не найден: "
                f"{self.service_account_path}"
            )

        self.download_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        credentials = Credentials.from_service_account_file(
            str(self.service_account_path),
            scopes=SCOPES,
        )

        self.service = build(
            "drive",
            "v3",
            credentials=credentials,
        )

    # ========================================================
    # PLAN
    # ========================================================

    def load_montage_plan(self) -> dict:
        """Загружает montage_plan.json."""

        if not MONTAGE_PLAN_PATH.exists():
            raise FileNotFoundError(
                f"montage_plan.json не найден: "
                f"{MONTAGE_PLAN_PATH}"
            )

        with open(
            MONTAGE_PLAN_PATH,
            "r",
            encoding="utf-8",
        ) as f:
            plan = json.load(f)

        if not isinstance(plan, dict):
            raise ValueError(
                "montage_plan.json должен содержать JSON object."
            )

        if "cuts" not in plan:
            raise ValueError(
                "В montage_plan.json отсутствует поле 'cuts'."
            )

        if not isinstance(plan["cuts"], list):
            raise ValueError(
                "Поле 'cuts' должно быть массивом."
            )

        return plan

    # ========================================================
    # FILE IDS
    # ========================================================

    def get_required_files(self, plan: dict) -> list:
        """
        Извлекает уникальные исходные файлы из cuts.
        Формирует уникальное имя локального файла на основе file_id.
        """

        files = []
        seen_ids = set()

        for cut in plan.get("cuts", []):
            file_id = cut.get("file_id")
            raw_filename = cut.get("filename", "video.mp4")

            if not file_id:
                raise ValueError(
                    "В одном из cuts отсутствует file_id."
                )

            if file_id in seen_ids:
                continue

            seen_ids.add(file_id)

            # Использование file_id в названии исключает любые коллизии имён
            # и гарантирует точную идентификацию локального файла
            ext = Path(raw_filename).suffix or ".mp4"
            local_filename = f"{file_id}{ext}"

            files.append(
                {
                    "file_id": file_id,
                    "filename": raw_filename,
                    "local_filename": local_filename,
                }
            )

        return files

    # ========================================================
    # DRIVE METADATA
    # ========================================================

    def get_file_metadata(self, file_id: str) -> dict:
        """
        Получает метаданные файла по file_id.
        """

        return (
            self.service.files()
            .get(
                fileId=file_id,
                fields=(
                    "id,"
                    "name,"
                    "mimeType,"
                    "size,"
                    "parents,"
                    "trashed"
                ),
            )
            .execute()
        )

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate_file(
        self,
        metadata: dict,
    ):
        """
        Проверяет, что найден именно нужный видеофайл
        из папки PROCESSED.
        """

        file_id = metadata.get("id")
        mime_type = metadata.get("mimeType")
        parents = metadata.get("parents", [])
        trashed = metadata.get("trashed", False)

        if trashed:
            raise ValueError(
                f"Файл {file_id} находится в корзине."
            )

        if not mime_type or not mime_type.startswith("video/"):
            raise ValueError(
                f"Файл {file_id} не является видео. "
                f"mimeType={mime_type}"
            )

        if PROCESSED_FOLDER_ID not in parents:
            raise ValueError(
                f"Файл {file_id} найден, но не находится "
                f"в папке PROCESSED."
            )

    # ========================================================
    # DOWNLOAD
    # ========================================================

    def download_file(
        self,
        file_id: str,
        filename: str,
        expected_size: int | None = None,
    ) -> Path:
        """
        Скачивает файл через Google Drive API.

        Сначала пишет во временный .part файл,
        затем атомарно переименовывает его.
        """

        destination = self.download_dir / filename
        temp_destination = self.download_dir / (
            f"{filename}.part"
        )

        # ----------------------------------------------------
        # Уже скачан
        # ----------------------------------------------------

        if destination.exists():
            existing_size = destination.stat().st_size

            if expected_size is None:
                if existing_size > 0:
                    print(
                        f"   ✓ Уже существует: {filename}"
                    )
                    return destination

            elif existing_size == expected_size:
                print(
                    f"   ✓ Уже скачан: {filename}"
                )
                return destination

            print(
                f"   ⚠ Размер локального файла отличается. "
                f"Скачиваем заново."
            )

        # ----------------------------------------------------
        # Удаляем незавершённую загрузку
        # ----------------------------------------------------

        if temp_destination.exists():
            temp_destination.unlink()

        print(
            f"   ↓ Скачивание: {filename}"
        )

        request = (
            self.service.files()
            .get_media(fileId=file_id)
        )

        with open(
            temp_destination,
            "wb",
        ) as fh:

            downloader = MediaIoBaseDownload(
                fh,
                request,
                chunksize=10 * 1024 * 1024,
            )

            done = False

            while not done:
                status, done = downloader.next_chunk()

                if status:
                    progress = int(
                        status.progress() * 100
                    )

                    print(
                        f"      {progress}%",
                        end="\r",
                        flush=True,
                    )

        print()

        # ----------------------------------------------------
        # Проверяем скачанный файл
        # ----------------------------------------------------

        if not temp_destination.exists():
            raise RuntimeError(
                f"Файл не был скачан: {filename}"
            )

        downloaded_size = temp_destination.stat().st_size

        if downloaded_size <= 0:
            temp_destination.unlink(
                missing_ok=True
            )

            raise RuntimeError(
                f"Скачан пустой файл: {filename}"
            )

        if (
            expected_size is not None
            and downloaded_size != expected_size
        ):
            temp_destination.unlink(
                missing_ok=True
            )

            raise RuntimeError(
                "Размер скачанного файла не совпадает "
                "с размером файла на Google Drive:\n"
                f"  Файл: {filename}\n"
                f"  Drive: {expected_size}\n"
                f"  Local: {downloaded_size}"
            )

        # ----------------------------------------------------
        # Атомарное завершение
        # ----------------------------------------------------

        temp_destination.replace(destination)

        print(
            f"   ✓ Готово: {destination}"
        )

        return destination

    # ========================================================
    # MAIN DOWNLOAD PROCESS
    # ========================================================

    def download_from_plan(self) -> list[Path]:
        """
        Главный метод:

        montage_plan.json
              ↓
        уникальные file_id
              ↓
        Google Drive PROCESSED
              ↓
        temp_downloads/
        """

        print()
        print("=" * 60)
        print(" VIDEO AI ENGINE — DRIVE DOWNLOADER")
        print("=" * 60)

        print(
            f"[Downloader] План: "
            f"{MONTAGE_PLAN_PATH}"
        )

        plan = self.load_montage_plan()

        required_files = self.get_required_files(
            plan
        )

        print(
            f"[Downloader] Уникальных исходников: "
            f"{len(required_files)}"
        )

        if not required_files:
            print(
                "[Downloader] В montage_plan.json "
                "нет файлов для скачивания."
            )
            return []

        downloaded_files = []

        for index, item in enumerate(
            required_files,
            start=1,
        ):
            file_id = item["file_id"]
            filename = item["filename"]
            local_filename = item["local_filename"]

            print()
            print(
                f"[{index}/{len(required_files)}] "
                f"{filename}"
            )

            print(
                f"   file_id: {file_id}"
            )

            # ------------------------------------------------
            # Получаем metadata
            # ------------------------------------------------

            try:
                metadata = self.get_file_metadata(
                    file_id
                )
            except Exception as e:
                raise RuntimeError(
                    f"Не удалось получить файл "
                    f"{file_id} из Google Drive: {e}"
                ) from e

            # ------------------------------------------------
            # Проверяем
            # ------------------------------------------------

            self.validate_file(
                metadata=metadata,
            )

            expected_size = None

            if metadata.get("size"):
                expected_size = int(
                    metadata["size"]
                )

            print(
                f"   Drive name: {metadata.get('name')}"
            )

            print(
                f"   MIME: {metadata.get('mimeType')}"
            )

            if expected_size is not None:
                print(
                    f"   Size: {expected_size / (1024 * 1024):.2f} MB"
                )

            # ------------------------------------------------
            # Download
            # ------------------------------------------------

            local_path = self.download_file(
                file_id=file_id,
                filename=local_filename,
                expected_size=expected_size,
            )

            downloaded_files.append(
                local_path
            )

        # ====================================================
        # RESULT
        # ====================================================

        print()
        print("=" * 60)
        print(" DOWNLOAD COMPLETE")
        print("=" * 60)

        for path in downloaded_files:
            print(
                f"✓ {path.name}"
            )

        print()
        print(
            f"[Downloader] Файлов готово: "
            f"{len(downloaded_files)}"
        )

        print(
            f"[Downloader] Папка: "
            f"{DOWNLOAD_DIR}"
        )

        return downloaded_files


# ============================================================
# CLI
# ============================================================

def main():
    downloader = DriveDownloader()

    downloader.download_from_plan()


if __name__ == "__main__":
    main()