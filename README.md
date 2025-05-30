# Telegram-бот "Игра в 21"

Telegram-бот, позволяющий двум пользователям в групповом чате сыграть между собой в упрощенную версию карточной игры "21" (Блэкджек).

## Описание

Бот предоставляет возможность устроить карточную игру в 21 очко внутри группового чата Telegram. Игра автоматически начинается, когда к ней присоединяются два игрока. Каждый игрок получает личные сообщения от бота с информацией о своих картах и возможных действиях.

## Функциональность

- Начало игры по команде `/start_21` в групповом чате
- Присоединение к игре через нажатие кнопки
- Автоматическая раздача карт
- Игровой процесс по правилам "21" с взятием дополнительных карт или остановкой
- Учет значений карт согласно правилам игры (туз может быть 1 или 11 очков)
- Определение победителя по стандартным правилам
- Отмена игры, если не набирается необходимое количество игроков

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/username/telegram-blackjack-bot.git
cd telegram-blackjack-bot
```

2. Установите необходимые зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` в корневой директории проекта и добавьте токен вашего бота:
```
BOT_TOKEN=your_telegram_bot_token_here
```

## Локальный запуск (Polling)

Для локальной разработки и тестирования:

```bash
python main.py
```

## Деплой на Render.com

### Подготовка

1. Создайте аккаунт на [Render.com](https://render.com/)
2. Свяжите свой репозиторий GitHub с Render
3. В настройках проекта на Render укажите:

Переменные окружения:
- `BOT_TOKEN` - токен бота Telegram
- `WEBHOOK_HOST` - URL вашего приложения на Render (например, https://your-app-name.onrender.com)

### Автоматический деплой

1. Используйте готовый файл `render.yaml` для настройки деплоя:
```bash
render blueprint render.yaml
```

2. Или настройте вручную новый веб-сервис:
   - **Environment**: Python
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `python main.py --webhook`

### После деплоя

1. Получите URL вашего приложения на Render (https://your-app-name.onrender.com)
2. Бот автоматически настроит вебхуки при запуске

## Использование

1. Добавьте бота в групповой чат
2. Отправьте команду `/start_21`, чтобы начать игру
3. Участники нажимают кнопку "Присоединиться" для участия
4. После присоединения двух игроков, игра автоматически начинается
5. Каждый игрок получает в личном чате информацию о своих картах и кнопки действий
6. По окончании игры, бот объявляет результаты в групповом чате

## Требования

- Python 3.8+
- aiogram 3.2.0+
- python-dotenv
- aiohttp

## Примечания

- Бот требует возможности отправлять личные сообщения участникам игры
- Бот поддерживает только одну активную игру в каждом чате
- Игра рассчитана только на двух участников 