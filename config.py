import os
from dotenv import load_dotenv

# Временно жёстко задаём токен для локального тестирования
BOT_TOKEN = "7825658711:AAGglEpeH55SoLAthkkGUuh0A1AGJH_1R2o"

# Конфигурация для webhook (Render)
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://your-app-name.onrender.com")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", f"/webhook/{BOT_TOKEN}")
WEBHOOK_URL = WEBHOOK_HOST

# Параметры веб-сервера
WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
WEB_SERVER_PORT = int(os.getenv("PORT", 8000))  # Render использует переменную PORT 