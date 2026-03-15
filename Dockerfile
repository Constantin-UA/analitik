# Базовий образ (Slim версія для економії місця)
FROM python:3.11-slim

# Встановлюємо системні залежності для компіляції pandas та інших C-бібліотек
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Забороняємо Python створювати .pyc файли та буферизувати stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Робоча директорія всередині контейнера
WORKDIR /app

# Спочатку копіюємо ТІЛЬКИ requirements.txt (для кешування шару Docker)
COPY requirements.txt .

# Встановлюємо залежності без кешу pip (робимо образ меншим)
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь інший код
COPY . .

# Команда запуску
CMD ["python", "bot.py"]