# test_story.py
from pathlib import Path
from src.graphics.overlay_generator import OverlayGenerator

# Инициализируем генератор
generator = OverlayGenerator()

# Подготавливаем данные для сторис
context = {
    # Путь к картинке фона (кадр или изображение)
    "background_path": "04_LIBRARY/brands/dance_kids/backgrounds/default.jpg",
    # Путь к логотипу
    "logo_path": "04_LIBRARY/brands/dance_kids/logo.png",
    # Заголовок сторис
    "title": "Открыт набор в группу Dance Kids!",
    # Дополнительный текст / Описание
    "text": "Занятия по вторникам и четвергам в 18:00.\nПервое занятие — бесплатно!",
    # Текст на кнопке / призыв к действию
    "cta": "Записаться в директ"
}

# Генерируем PNG
output_path = generator.generate_image(
    template_name="story.html",
    context=context,
    output_path="temp_downloads/test_story_result.png"
)

print(f"Сторис успешно сгенерирована: {output_path}")