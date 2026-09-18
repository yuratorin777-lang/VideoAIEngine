import os
from pathlib import Path
from playwright.sync_api import sync_playwright

class OverlayGenerator:
    def __init__(self, templates_dir: str = "src/graphics/templates"):
        self.templates_dir = Path(templates_dir)

    def generate_image(
        self,
        template_name: str,
        context: dict,
        output_path: str,
        viewport: dict | None = None,
        is_landscape: bool = False,
    ) -> str:
        """
        Принимает название шаблона (cover.html/story.html),
        словарь подстановок {{ key }}, сохраняет готовый PNG.
        """
        template_file = self.templates_dir / template_name
        if not template_file.exists():
            raise FileNotFoundError(f"Шаблон не найден: {template_file}")

        html_content = template_file.read_text(encoding="utf-8")
        
        # Подстановка значений в HTML с автоматическим преобразованием путей файлов в URI
        for key, value in context.items():
            val_str = str(value)
            # Если передали существующий путь к файлу, конвертируем в file:// URI
            if isinstance(value, (str, Path)):
                p = Path(value)
                if p.exists() and p.is_file():
                    val_str = p.resolve().as_uri()

            html_content = html_content.replace(f"{{{{ {key} }}}}", val_str)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        temp_html = output_file.with_suffix(".html")
        temp_html.write_text(html_content, encoding="utf-8")

        # Определение размеров viewport по ориентации, если параметр viewport не передан явно
        if viewport is None:
            if is_landscape:
                viewport = {"width": 1920, "height": 1080}
            else:
                viewport = {"width": 1080, "height": 1920}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport=viewport)
            page.goto(temp_html.resolve().as_uri())
            
            # Делаем скриншот с полным совпадением clip по размерам кадра
            page.screenshot(
                path=str(output_file),
                type="png",
                clip={"x": 0, "y": 0, "width": viewport["width"], "height": viewport["height"]}
            )
            browser.close()

        if temp_html.exists():
            temp_html.unlink()

        return str(output_file)