import json
import logging
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)


class VercelGatewayClient:
    """
    Клиент для взаимодействия с Vercel API Gateway (Gemini Vision proxy).
    Отвечает за отправку видео на анализ, предварительную валидацию размера файла
    и безопасную обработку сетевых ошибок.
    """

    DEFAULT_TIMEOUT = 300  # 5 минут на обработку длинных видео
    MIN_FILE_SIZE_BYTES = 1024  # Минимальный размер файла (1 KB), меньше которого файл считается поврежденным

    def __init__(self, proxy_url: str, default_timeout: int = DEFAULT_TIMEOUT):
        """
        :param proxy_url: URL эндпоинта Vercel Gateway.
        :param default_timeout: Таймаут ожидания ответа сервера в секундах.
        """
        self.proxy_url = proxy_url.strip() if proxy_url else ""
        self.default_timeout = default_timeout

    def request_video_analysis(
        self,
        drive_url: str,
        prompt: str,
        file_size_bytes: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Запрашивает анализ видео у Vercel Gateway.

        :param drive_url: Прямая ссылка или Google Drive URL видеофайла.
        :param prompt: Инструкция / промпт для анализа видео через Gemini.
        :param file_size_bytes: Размер файла в байтах (из метаданных Google Drive).
        :param timeout: Кастомный таймаут для запроса (секунды).
        :return: Dict вида {"success": True, "data": ...} или {"success": False, "error": ...}
        """

        # ---------------------------------------------------------
        # 1. ВАЛИДАЦИЯ URL И ПРОМПТА
        # ---------------------------------------------------------

        if not self.proxy_url:
            error_msg = "Не задан proxy_url для VercelGatewayClient."
            logger.error(f"[VercelClient] {error_msg}")
            return {"success": False, "error": error_msg}

        if not drive_url or not isinstance(drive_url, str) or not drive_url.strip():
            error_msg = "Отсутствует или невалиден drive_url файла."
            logger.error(f"[VercelClient] {error_msg}")
            return {"success": False, "error": error_msg}

        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            error_msg = "Передан пустой промпт для анализа."
            logger.error(f"[VercelClient] {error_msg}")
            return {"success": False, "error": error_msg}

        # ---------------------------------------------------------
        # 2. ЖЕСТКАЯ ПРОВЕРКА РАЗМЕРА ФАЙЛА (Google Drive Guard)
        # ---------------------------------------------------------

        if file_size_bytes is not None:
            try:
                size = int(file_size_bytes)
                if size < self.MIN_FILE_SIZE_BYTES:
                    error_msg = (
                        f"Файл не загрузился или поврежден (размер {size} B < "
                        f"минимального порога {self.MIN_FILE_SIZE_BYTES} B). "
                        "Пайплайн остановлен."
                    )
                    logger.error(f"[VercelClient] {error_msg}")
                    return {"success": False, "error": error_msg}
            except (ValueError, TypeError):
                logger.warning(
                    f"[VercelClient] Передан некорректный file_size_bytes: {file_size_bytes}. Проверка пропускается."
                )

        # ---------------------------------------------------------
        # 3. ПОДГОТОВКА И ОТПРАВКА ЗАПРОСА
        # ---------------------------------------------------------

        payload = {
            "prompt": prompt.strip(),
            "videoUrl": drive_url.strip()
        }

        req_timeout = timeout if timeout is not None else self.default_timeout

        try:
            logger.info(f"[VercelClient] Отправка запроса в Gateway: {drive_url}")

            response = requests.post(
                self.proxy_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=req_timeout,
            )

            # ---------------------------------------------------------
            # 4. ОБРАБОТКА УСПЕШНОГО ОТВЕТА (200 OK)
            # ---------------------------------------------------------

            if response.status_code == 200:
                try:
                    res_json = response.json()
                    parsed_data = res_json.get("text") or res_json.get("data") or res_json

                    if not parsed_data:
                        logger.warning("[VercelClient] Сервер вернул 200 OK, но поле с ответом пустое.")
                        return {
                            "success": True,
                            "data": "",
                            "raw_response": res_json
                        }

                    return {
                        "success": True,
                        "data": parsed_data,
                        "raw_response": res_json
                    }

                except json.JSONDecodeError:
                    # Если Vercel прокси вернул plain text вместо JSON
                    return {
                        "success": True,
                        "data": response.text.strip()
                    }

            # ---------------------------------------------------------
            # 5. ОБРАБОТКА HTTP ОШИБОК (Non-200)
            # ---------------------------------------------------------

            error_details = (
                f"Vercel Gateway вернул ошибку HTTP {response.status_code}: {response.text}"
            )
            logger.error(f"[VercelClient] {error_details}")
            return {
                "success": False,
                "error": error_details,
                "status_code": response.status_code
            }

        # ---------------------------------------------------------
        # 6. ИСКЛЮЧЕНИЯ СЕТИ И ТАЙМАУТОВ
        # ---------------------------------------------------------

        except requests.exceptions.Timeout:
            error_msg = (
                f"Превышен таймаут ожидания ответа Vercel Gateway ({req_timeout} сек)."
            )
            logger.error(f"[VercelClient] {error_msg}")
            return {"success": False, "error": error_msg}

        except requests.exceptions.ConnectionError as e:
            error_msg = f"Ошибка соединения с Vercel Gateway: {str(e)}"
            logger.error(f"[VercelClient] {error_msg}")
            return {"success": False, "error": error_msg}

        except requests.exceptions.RequestException as e:
            error_msg = f"Сетевая ошибка при обращении к Vercel Gateway: {str(e)}"
            logger.error(f"[VercelClient] {error_msg}")
            return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"Непредвиденная ошибка в VercelGatewayClient: {str(e)}"
            logger.error(f"[VercelClient] {error_msg}")
            return {"success": False, "error": error_msg}