import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла, если он существует
load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "7825658711:AAGglEpeH55SoLAthkkGUuh0A1AGJH_1R2o")

# Конфигурация для webhook (Render)
WEBHOOK_HOST = os.getenv("WEBHOOK_URL", "https://two1-hu47.onrender.com")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook/")
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Параметры веб-сервера
WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
WEB_SERVER_PORT = int(os.getenv("PORT", 10000))  # Render использует переменную PORT 