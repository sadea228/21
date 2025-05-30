import asyncio
import logging
import os
import sys
from typing import Dict, Optional
import time

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from config import BOT_TOKEN, WEBHOOK_PATH, WEBHOOK_URL, WEB_SERVER_HOST, WEB_SERVER_PORT
from game import Game, active_games
from keyboards import get_join_keyboard, get_game_actions_keyboard

# Настройка логирования
logging.basicConfig(level=logging.INFO)
# Попробуем включить более подробное логирование для aiohttp.access, чтобы видеть все запросы к вебхуку
logging.getLogger('aiohttp.access').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__) # Используем именованный логгер для нашего кода

# Словарь для хранения таймеров ожидания второго игрока
join_timers: Dict[int, float] = {}

# Время ожидания второго игрока в секундах
JOIN_TIMEOUT = 60.0

# Словарь для хранения ID последнего сообщения с клавиатурой для каждого игрока
last_keyboard_messages: Dict[int, int] = {}

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.errors()
async def errors_handler(event):
    """Обработчик ошибок для необработанных обновлений."""
    # ErrorEvent содержит исключение и update (если доступно)
    exception = getattr(event, 'exception', None)
    update = getattr(event, 'update', None)
    update_id = update.update_id if update else 'N/A'
    logger.exception(f"Ошибка при обработке запроса (update_id={update_id}): {exception}", exc_info=True)
    # SimpleRequestHandler автоматически отправит 200 OK Telegram, даже если здесь возникла ошибка.

@dp.message(Command("start", ignore_mention=True))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    logger.info(f"Команда /start от пользователя {message.from_user.id} в чате {message.chat.id}")
    await message.answer(
        "🎴 *Добро пожаловать в игру \"21\"!*\n\n"
        "Чтобы начать игру в групповом чате, используйте команду /start_21.\n"
        "Чтобы проверить статус текущей игры, используйте /game_status.\n"
        "Для получения правил игры, используйте /help.\n\n"
        "✅ Теперь вы можете получать личные сообщения от бота во время игры.",
        parse_mode="Markdown"
    )

@dp.message(Command("start_21", ignore_mention=True))
async def cmd_start_game(message: types.Message):
    """Обработчик команды /start_21 - начало новой игры"""
    logger.info(f"Команда /start_21 от пользователя {message.from_user.id} в чате {message.chat.id}")
    # Проверяем, что команда отправлена в групповом чате
    if message.chat.type not in ["group", "supergroup"]:
        logger.warning(f"/start_21 вызвана не в группе пользователем {message.from_user.id}")
        await message.answer("⚠️ Эта команда работает только в групповых чатах!")
        return

    chat_id = message.chat.id
    
    # Проверка на существующую игру в чате
    if chat_id in active_games:
        game = active_games[chat_id]
        if not game.finished:
            await message.answer("⚠️ В этом чате уже идет игра!")
            return
        else:
            # Удаляем завершенную игру
            del active_games[chat_id]
    
    # Создаем новую игру
    active_games[chat_id] = Game(chat_id)
    
    # Запускаем таймер ожидания второго игрока
    join_timers[chat_id] = time.time()
    
    bot_username = (await bot.get_me()).username
    
    await message.answer(
        f"🎮 *Начата новая игра в 21!*\n"
        f"👥 *Игроки:* 0/2\n"
        f"⏳ *Ожидаем игроков...*\n\n"
        f"Нажмите кнопку, чтобы присоединиться.\n\n"
        f"❗️ *Важно:* Перед началом игры каждый участник должен начать личный диалог с ботом: "
        f"https://t.me/{bot_username}",
        parse_mode="Markdown",
        reply_markup=get_join_keyboard()
    )
    
    # Запускаем таймер ожидания второго игрока
    asyncio.create_task(wait_for_second_player(chat_id, message.message_id))

@dp.message(Command("game_status", ignore_mention=True))
async def cmd_game_status(message: types.Message):
    """Обработчик команды /game_status - показывает текущий статус игры"""
    logger.info(f"Команда /game_status от пользователя {message.from_user.id} в чате {message.chat.id}")
    chat_id = message.chat.id
    
    # Проверяем, что команда отправлена в групповом чате
    if message.chat.type not in ["group", "supergroup"]:
        logger.warning(f"/game_status вызвана не в группе пользователем {message.from_user.id}")
        await message.answer("⚠️ Эта команда работает только в групповых чатах!")
        return
    
    # Проверяем наличие активной игры
    if chat_id not in active_games:
        try:
            await message.answer(
                "ℹ️ В этом чате нет активной игры. Начните новую игру командой /start\_21",
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
            await message.answer("ℹ️ В этом чате нет активной игры. Начните новую игру командой /start_21")
        return
    
    game = active_games[chat_id]
    
    # Если игра еще не началась (ожидание игроков)
    if not game.started:
        players_count = len(game.players)
        
        # Формируем список присоединившихся игроков
        players_info = ""
        if players_count > 0:
            players_list = "\n".join([f"👤 `{player.username}`" for player in game.players.values()])
            players_info = f"👥 *Присоединившиеся игроки ({players_count}/2):*\n{players_list}\n"
        
        # Информация о времени ожидания
        time_info = ""
        if chat_id in join_timers:
            elapsed = time.time() - join_timers[chat_id]
            remaining = max(0, JOIN_TIMEOUT - elapsed)
            time_info = f"⏱ *Осталось времени:* {int(remaining)} сек.\n"
        
        status_message = (
            f"📊 *Статус игры:* Ожидание игроков\n"
            f"{players_info}"
            f"{time_info}\n"
            f"⚠️ Для начала игры необходимо минимум 2 игрока.\n"
            f"🎮 Нажмите кнопку ниже, чтобы присоединиться:"
        )
        
        try:
            await message.answer(status_message, parse_mode="Markdown", reply_markup=get_join_keyboard())
        except TelegramBadRequest as e:
            logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
            clean_message = status_message.replace("*", "").replace("`", "").replace("\\_", "_")
            await message.answer(clean_message, reply_markup=get_join_keyboard())
    else:
        # Если игра уже идет
        if game.finished:
            # Если игра завершена
            try:
                await message.answer(
                    f"📊 *Статус игры:* Завершена\n\n{game.get_status_message()}",
                    parse_mode="Markdown"
                )
            except TelegramBadRequest as e:
                logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                status_message = f"📊 Статус игры: Завершена\n\n{game.get_status_message().replace('*', '')}"
                await message.answer(status_message)
        else:
            # Если игра активна
            current_player = game.players.get(game.current_player_id)
            player_name = current_player.username if current_player else "Неизвестный"
            
            # Формируем список игроков с их статусами
            players_info = []
            for player in game.players.values():
                status = "🎮"
                if player.user_id == game.current_player_id:
                    status = "🎯"  # текущий ход
                elif player.busted:
                    status = "💥"  # перебор
                elif player.stopped:
                    status = "✋"  # остановился
                
                players_info.append(f"{status} `{player.username}`: {player.get_score()} очков")
            
            players_list = "\n".join(players_info)
            
            status_message = (
                f"📊 *Статус игры:* Активна\n"
                f"👥 *Игроки:*\n{players_list}\n\n"
                f"🎯 *Текущий ход:* `{player_name}`"
            )
            
            try:
                await message.answer(status_message, parse_mode="Markdown")
            except TelegramBadRequest as e:
                logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                clean_message = status_message.replace("*", "").replace("`", "").replace("\\_", "_")
                await message.answer(clean_message)

@dp.message(Command("help", ignore_mention=True))
async def cmd_help(message: types.Message):
    """Обработчик команды /help - показывает правила игры и доступные команды"""
    logger.info(f"Команда /help от пользователя {message.from_user.id} в чате {message.chat.id}")
    help_text = (
        "🎮 *Правила игры \"21\"*\n\n"
        "Цель игры: набрать 21 очко или количество очков, максимально близкое к 21, но не больше.\n\n"
        "*Ценность карт:*\n"
        "• Карты от 2 до 10 - по номиналу\n"
        "• Валет (J), Дама (Q), Король (K) - 10 очков\n"
        "• Туз (A) - 11 очков или 1 очко (если 11 приведёт к перебору)\n\n"
        "*Ход игры:*\n"
        "1. В игре участвуют 2 игрока\n"
        "2. Каждый игрок получает по 2 карты\n"
        "3. Игроки по очереди могут взять дополнительные карты или остановиться\n"
        "4. Если сумма карт игрока превышает 21, он проигрывает (перебор)\n"
        "5. Когда оба игрока закончили брать карты, сравнивается сумма очков\n"
        "6. Побеждает игрок с наибольшим количеством очков (не более 21)\n\n"
        "*Доступные команды:*\n"
        "• /start\_21 - начать новую игру (только в групповом чате)\n"
        "• /game\_status - проверить текущий статус игры\n"
        "• /help - показать правила и доступные команды\n\n"
        "❗️ *Важно:* Перед началом игры каждый участник должен начать личный диалог с ботом, чтобы получать информацию о своих картах."
    )
    try:
        await message.answer(help_text, parse_mode="Markdown")
    except TelegramBadRequest as e:
        logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
        clean_text = help_text.replace("*", "").replace("`", "").replace("\\_", "_")
        await message.answer(clean_text)

async def wait_for_second_player(chat_id: int, message_id: int):
    """Функция ожидания второго игрока с таймером"""
    await asyncio.sleep(JOIN_TIMEOUT)
    
    # Проверяем, что игра все еще существует и не начата
    if chat_id in active_games and not active_games[chat_id].started:
        game = active_games[chat_id]
        
        # Если присоединился только один игрок, отменяем игру
        if len(game.players) < 2:
            # Формируем список присоединившихся игроков
            players_count = len(game.players)
            players_info = ""
            if players_count > 0:
                # Экранируем специальные символы Markdown в именах пользователей
                players_list = "\n".join([f"👤 `{player.username}`" for player in game.players.values()])
                players_info = f"\n\n👥 *Присоединившиеся игроки ({players_count}/2):*\n{players_list}"
            
            timeout_message = (
                f"⏱ *Время ожидания истекло!*\n"
                f"Для начала игры необходимо минимум 2 игрока.{players_info}\n\n"
                f"Игра отменена. Начните новую игру командой /start\\_21"
            )
            
            try:
                await bot.send_message(chat_id, timeout_message, parse_mode="Markdown")
            except TelegramBadRequest as e:
                # Если не удалось отправить с Markdown, отправляем без форматирования
                logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                clean_message = timeout_message.replace("*", "").replace("`", "").replace("\\_", "_")
                await bot.send_message(chat_id, clean_message)
            
            del active_games[chat_id]
            
            # Удаляем таймер
            if chat_id in join_timers:
                del join_timers[chat_id]

@dp.callback_query(F.data == "join_game")
async def process_join_callback(callback: types.CallbackQuery):
    """Обработчик нажатия на кнопку присоединения к игре"""
    logger.info(f"Колбэк 'join_game' от пользователя {callback.from_user.id} в чате {callback.message.chat.id if callback.message else 'N/A'}")
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    username = callback.from_user.first_name
    
    # Проверяем существование игры
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена или уже завершена.", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    # Проверяем, не начата ли уже игра
    if game.started:
        await callback.answer("⚠️ Игра уже началась!", show_alert=True)
        return
    
    # Проверяем, не присоединился ли пользователь ранее
    if user_id in game.players:
        await callback.answer("ℹ️ Вы уже присоединились к игре!", show_alert=True)
        return
    
    # Добавляем игрока
    can_start = game.add_player(user_id, username)
    
    await callback.answer(f"✅ Вы присоединились к игре!", show_alert=False)
    
    bot_username = (await bot.get_me()).username
    
    # Формируем список присоединившихся игроков
    players_list = "\n".join([f"👤 `{player.username}`" for player in game.players.values()])
    players_count = len(game.players)
    
    join_message = (
        f"👤 Игрок `{username}` присоединился к игре!\n\n"
        f"📊 *Статус игры:*\n"
        f"👥 *Игроки ({players_count}/2):*\n{players_list}\n"
    )
    
    # Добавляем информацию о недостающих игроках и времени ожидания
    if players_count < 2:
        join_message += f"⏳ *Ожидаем еще {2 - players_count} игрока...*\n"
        
        # Добавляем информацию о времени ожидания
        if chat_id in join_timers:
            elapsed = time.time() - join_timers[chat_id]
            remaining = max(0, JOIN_TIMEOUT - elapsed)
            join_message += f"⏱ *Осталось времени:* {int(remaining)} сек.\n"
    
    # Попытаемся проверить, может ли бот отправлять сообщения пользователю
    try:
        await bot.send_chat_action(user_id, "typing")
        # Если успешно, то пользователь уже взаимодействовал с ботом
    except Exception:
        # Пользователь еще не начал диалог с ботом
        join_message += f"\n❗️ `{username}`, пожалуйста, начните личный диалог с ботом перед началом игры: https://t.me/{bot_username}"
    
    # Пытаемся изменить существующее сообщение или отправляем новое
    try:
        await callback.message.edit_text(
            join_message,
            parse_mode="Markdown",
            reply_markup=get_join_keyboard() if players_count < 2 else None
        )
    except Exception as e:
        logging.error(f"Ошибка при обновлении сообщения: {e}")
        try:
            await bot.send_message(chat_id, join_message, parse_mode="Markdown")
        except TelegramBadRequest as e:
            # Если не удалось отправить с Markdown, отправляем без форматирования
            logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
            clean_message = join_message.replace("*", "").replace("`", "").replace("\\_", "_")
            await bot.send_message(chat_id, clean_message)
    
    # Если набралось 2 игрока, начинаем игру
    if can_start:
        game.start_game()
        
        # Удаляем таймер ожидания
        if chat_id in join_timers:
            del join_timers[chat_id]
        
        # Объявляем о начале игры
        players_str = ", ".join([f"`{player.username}`" for player in game.players.values()])
        start_message = f"🎲 *Игра начинается!*\n👥 Участники: {players_str}"
        start_message += f"\n\n❗️ Убедитесь, что вы начали личный диалог с ботом: https://t.me/{bot_username}"
        
        try:
            await bot.send_message(chat_id, start_message, parse_mode="Markdown")
        except TelegramBadRequest as e:
            # Если не удалось отправить с Markdown, отправляем без форматирования
            logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
            clean_message = start_message.replace("*", "").replace("`", "").replace("\\_", "_")
            await bot.send_message(chat_id, clean_message)
        
        # Отправляем информацию о картах каждому игроку в личку
        await send_cards_info_to_players(game)
        
        # Сообщаем о ходе первого игрока
        current_player = game.players.get(game.current_player_id)
        if current_player:
            try:
                await bot.send_message(
                    chat_id, 
                    f"🎯 Ход игрока `{current_player.username}`. Проверьте личные сообщения от бота!",
                    parse_mode="Markdown"
                )
            except TelegramBadRequest as e:
                logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                await bot.send_message(
                    chat_id, 
                    f"🎯 Ход игрока {current_player.username}. Проверьте личные сообщения от бота!"
                )

async def send_cards_info_to_players(game: Game):
    """Отправляет информацию о картах игрокам в личные сообщения"""
    for user_id, player in game.players.items():
        try:
            message = (
                f"🎴 *Ваши карты:* {player.get_cards_str()}\n"
                f"🔢 *Сумма очков:* {player.get_score()}"
            )
            
            # Добавляем клавиатуру с действиями, если сейчас ход этого игрока
            keyboard = None
            if game.current_player_id == user_id:
                message += "\n\n🎯 *Сейчас ваш ход*. Выберите действие:"
                keyboard = get_game_actions_keyboard()
            
            # Отправляем новое сообщение и сохраняем его ID
            sent_message = await bot.send_message(
                user_id, 
                message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            # Если есть клавиатура, сохраняем ID сообщения
            if keyboard:
                last_keyboard_messages[user_id] = sent_message.message_id
                
        except Exception as e:
            # Обрабатываем все возможные ошибки, включая TelegramForbiddenError
            error_message = (
                f"⚠️ Не удалось отправить личное сообщение игроку *{player.username}*. "
                f"Пожалуйста, начните диалог с ботом перед началом игры: "
                f"https://t.me/{(await bot.get_me()).username}"
            )
            await bot.send_message(game.chat_id, error_message, parse_mode="Markdown")
            logging.error(f"Ошибка при отправке сообщения игроку {user_id}: {e}")

@dp.callback_query(F.data == "hit")
async def process_hit_callback(callback: types.CallbackQuery):
    """Обработчик нажатия на кнопку 'Взять ещё'"""
    logger.info(f"Колбэк 'hit' от пользователя {callback.from_user.id} в ЛС (сообщение {callback.message.message_id if callback.message else 'N/A'})")
    user_id = callback.from_user.id
    
    # Проверяем, является ли это сообщение последним с клавиатурой
    if user_id in last_keyboard_messages and callback.message.message_id != last_keyboard_messages[user_id]:
        await callback.answer("⚠️ Используйте кнопки из последнего сообщения!", show_alert=True)
        return
    
    # Ищем игру, в которой участвует пользователь
    game = find_game_by_user_id(user_id)
    if not game:
        await callback.answer("⚠️ Игра не найдена или уже завершена.", show_alert=True)
        return
    
    # Проверяем, может ли игрок взять карту
    success, card = game.hit(user_id)
    if not success:
        await callback.answer("⚠️ Вы не можете взять карту сейчас.", show_alert=True)
        return
    
    player = game.players[user_id]
    
    await callback.answer(f"🃏 Вы взяли карту {card}!", show_alert=False)
    
    # Сообщаем в групповой чат о взятии карты
    try:
        await bot.send_message(
            game.chat_id,
            f"🃏 Игрок `{player.username}` берет еще карту.",
            parse_mode="Markdown"
        )
    except TelegramBadRequest as e:
        logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
        await bot.send_message(
            game.chat_id,
            f"🃏 Игрок {player.username} берет еще карту."
        )
    
    # Проверяем, может ли бот отправлять сообщения пользователю
    if not await can_message_user(user_id):
        bot_username = (await bot.get_me()).username
        try:
            await bot.send_message(
                game.chat_id,
                f"❗️ `{player.username}`, бот не может отправить вам личное сообщение. "
                f"Пожалуйста, начните диалог с ботом: https://t.me/{bot_username}",
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
            await bot.send_message(
                game.chat_id,
                f"❗️ {player.username}, бот не может отправить вам личное сообщение. "
                f"Пожалуйста, начните диалог с ботом: https://t.me/{bot_username}"
            )
    else:
        # Обновляем информацию о картах
        message = (
            f"🎴 *Ваши карты:* {player.get_cards_str()}\n"
            f"🔢 *Сумма очков:* {player.get_score()}"
        )
        
        # Проверяем на перебор
        if player.busted:
            try:
                await bot.send_message(
                    game.chat_id,
                    f"💥 Игрок `{player.username}` перебрал! Сумма очков: *{player.get_score()}*",
                    parse_mode="Markdown"
                )
            except TelegramBadRequest as e:
                logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                await bot.send_message(
                    game.chat_id,
                    f"💥 Игрок {player.username} перебрал! Сумма очков: {player.get_score()}"
                )
            
            # Отправляем игроку в ЛС обновление о переборе и убираем клавиатуру
            try:
                # Убираем клавиатуру с предыдущего сообщения
                if user_id in last_keyboard_messages:
                    try:
                        await bot.edit_message_reply_markup(
                            chat_id=user_id,
                            message_id=last_keyboard_messages[user_id],
                            reply_markup=None
                        )
                    except Exception:
                        pass  # Игнорируем ошибки при удалении клавиатуры

                # Отправляем новое сообщение с информацией о переборе
                bust_message = (
                    f"💥 *Перебор!*\n"
                    f"🎴 *Ваши карты:* {player.get_cards_str()}\n"
                    f"🔢 *Сумма очков:* {player.get_score()}\n\n"
                    f"Вы взяли слишком много карт и проиграли."
                )
                try:
                    await bot.send_message(user_id, bust_message, parse_mode="Markdown")
                except TelegramBadRequest as e:
                    logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                    clean_message = bust_message.replace("*", "").replace("`", "").replace("\\_", "_")
                    await bot.send_message(user_id, clean_message)
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения о переборе игроку {user_id}: {e}")
            
            # Проверяем, завершилась ли игра
            if game.finished:
                try:
                    await bot.send_message(
                        game.chat_id,
                        game.get_status_message(),
                        parse_mode="Markdown"
                    )
                except TelegramBadRequest as e:
                    logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                    clean_message = game.get_status_message().replace("*", "").replace("`", "").replace("\\_", "_")
                    await bot.send_message(game.chat_id, clean_message)
                return
            
            # Переход хода
            game.next_turn()
            current_player = game.players.get(game.current_player_id)
            if current_player:
                try:
                    await bot.send_message(
                        game.chat_id,
                        f"🎯 Ход переходит к игроку `{current_player.username}`.",
                        parse_mode="Markdown"
                    )
                except TelegramBadRequest as e:
                    logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                    await bot.send_message(
                        game.chat_id,
                        f"🎯 Ход переходит к игроку {current_player.username}."
                    )
                await update_player_message(game, current_player.user_id)
            return
        
        # Если игрок не перебрал, предлагаем действия
        keyboard = get_game_actions_keyboard()
        message += "\n\n🎯 *Выберите действие:*"
        
        try:
            # Пытаемся обновить текущее сообщение
            await callback.message.edit_text(message, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            # Если не удалось отредактировать сообщение, отправляем новое
            try:
                # Удаляем старую клавиатуру, если она есть
                if user_id in last_keyboard_messages:
                    try:
                        await bot.edit_message_reply_markup(
                            chat_id=user_id,
                            message_id=last_keyboard_messages[user_id],
                            reply_markup=None
                        )
                    except Exception:
                        pass  # Игнорируем ошибки при удалении клавиатуры
                
                # Отправляем новое сообщение и сохраняем его ID
                sent_message = await bot.send_message(
                    user_id, 
                    message, 
                    reply_markup=keyboard, 
                    parse_mode="Markdown"
                )
                last_keyboard_messages[user_id] = sent_message.message_id
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения игроку {user_id}: {e}")
                bot_username = (await bot.get_me()).username
                try:
                    await bot.send_message(
                        game.chat_id,
                        f"❗️ `{player.username}`, бот не может отправить вам личное сообщение. "
                        f"Пожалуйста, начните диалог с ботом: https://t.me/{bot_username}",
                        parse_mode="Markdown"
                    )
                except TelegramBadRequest as e:
                    logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                    await bot.send_message(
                        game.chat_id,
                        f"❗️ {player.username}, бот не может отправить вам личное сообщение. "
                        f"Пожалуйста, начните диалог с ботом: https://t.me/{bot_username}"
                    )

@dp.callback_query(F.data == "stand")
async def process_stand_callback(callback: types.CallbackQuery):
    """Обработчик нажатия на кнопку 'Остановиться'"""
    logger.info(f"Колбэк 'stand' от пользователя {callback.from_user.id} в ЛС (сообщение {callback.message.message_id if callback.message else 'N/A'})")
    user_id = callback.from_user.id
    
    # Проверяем, является ли это сообщение последним с клавиатурой
    if user_id in last_keyboard_messages and callback.message.message_id != last_keyboard_messages[user_id]:
        await callback.answer("⚠️ Используйте кнопки из последнего сообщения!", show_alert=True)
        return
    
    # Ищем игру, в которой участвует пользователь
    game = find_game_by_user_id(user_id)
    if not game:
        await callback.answer("⚠️ Игра не найдена или уже завершена.", show_alert=True)
        return
    
    # Проверяем, может ли игрок остановиться
    success = game.stand(user_id)
    if not success:
        await callback.answer("⚠️ Вы не можете остановиться сейчас.", show_alert=True)
        return
    
    player = game.players[user_id]
    
    await callback.answer("✋ Вы остановились!", show_alert=False)
    
    # Сообщаем в групповой чат об остановке
    try:
        await bot.send_message(
            game.chat_id,
            f"✋ Игрок `{player.username}` останавливается.",
            parse_mode="Markdown"
        )
    except TelegramBadRequest as e:
        logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
        await bot.send_message(
            game.chat_id,
            f"✋ Игрок {player.username} останавливается."
        )
    
    # Убираем клавиатуру после остановки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    
    # Проверяем, завершена ли игра
    if game.finished:
        try:
            await bot.send_message(
                game.chat_id,
                game.get_status_message(),
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
            clean_message = game.get_status_message().replace("*", "").replace("`", "").replace("\\_", "_")
            await bot.send_message(game.chat_id, clean_message)
        return
    
    # Переходим к следующему игроку
    game.next_turn()
    current_player = game.players.get(game.current_player_id)
    if current_player:
        try:
            await bot.send_message(
                game.chat_id,
                f"🎯 Ход переходит к игроку `{current_player.username}`.",
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
            await bot.send_message(
                game.chat_id,
                f"🎯 Ход переходит к игроку {current_player.username}."
            )
        await update_player_message(game, current_player.user_id)

async def can_message_user(user_id: int) -> bool:
    """Проверяет, может ли бот отправлять сообщения пользователю"""
    try:
        await bot.send_chat_action(user_id, "typing")
        return True
    except Exception:
        return False

async def update_player_message(game: Game, user_id: int):
    """Обновляет сообщение с информацией о картах игрока"""
    player = game.players.get(user_id)
    if not player:
        return

    # Проверяем, может ли бот отправлять сообщения пользователю
    if not await can_message_user(user_id):
        bot_username = (await bot.get_me()).username
        try:
            await bot.send_message(
                game.chat_id,
                f"❗️ `{player.username}`, бот не может отправить вам личное сообщение. "
                f"Пожалуйста, начните диалог с ботом: https://t.me/{bot_username} "
                f"и затем нажмите любую кнопку действия.",
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
            await bot.send_message(
                game.chat_id,
                f"❗️ {player.username}, бот не может отправить вам личное сообщение. "
                f"Пожалуйста, начните диалог с ботом: https://t.me/{bot_username} "
                f"и затем нажмите любую кнопку действия."
            )
        return

    message = (
        f"🎴 *Ваши карты:* {player.get_cards_str()}\n"
        f"🔢 *Сумма очков:* {player.get_score()}"
    )
    
    # Если сейчас ход этого игрока и он еще не завершил игру
    if game.current_player_id == user_id and not player.stopped and not player.busted:
        message += "\n\n🎯 *Сейчас ваш ход*. Выберите действие:"
        keyboard = get_game_actions_keyboard()
        
        try:
            # Удаляем старую клавиатуру, если она есть
            if user_id in last_keyboard_messages:
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=user_id,
                        message_id=last_keyboard_messages[user_id],
                        reply_markup=None
                    )
                except Exception:
                    pass  # Игнорируем ошибки при удалении клавиатуры
            
            # Отправляем новое сообщение и сохраняем его ID
            try:
                sent_message = await bot.send_message(
                    user_id, 
                    message, 
                    reply_markup=keyboard, 
                    parse_mode="Markdown"
                )
                last_keyboard_messages[user_id] = sent_message.message_id
            except TelegramBadRequest as e:
                logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                clean_message = message.replace("*", "").replace("`", "").replace("\\_", "_")
                sent_message = await bot.send_message(
                    user_id, 
                    clean_message, 
                    reply_markup=keyboard
                )
                last_keyboard_messages[user_id] = sent_message.message_id
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения игроку {user_id}: {e}")
            bot_username = (await bot.get_me()).username
            try:
                await bot.send_message(
                    game.chat_id,
                    f"❗️ `{player.username}`, бот не может отправить вам личное сообщение. "
                    f"Пожалуйста, начните диалог с ботом: https://t.me/{bot_username}",
                    parse_mode="Markdown"
                )
            except TelegramBadRequest as e:
                logging.error(f"Ошибка при отправке форматированного сообщения: {e}")
                await bot.send_message(
                    game.chat_id,
                    f"❗️ {player.username}, бот не может отправить вам личное сообщение. "
                    f"Пожалуйста, начните диалог с ботом: https://t.me/{bot_username}"
                )

def find_game_by_user_id(user_id: int) -> Optional[Game]:
    """Находит игру, в которой участвует пользователь"""
    for game in active_games.values():
        if user_id in game.players and not game.finished:
            return game
    return None

@dp.message(Command("clear", ignore_mention=True))
async def cmd_clear(message: types.Message):
    """Команда для принудительного завершения игры. Только @sadea12."""
    logger.info(f"Команда /clear от пользователя {message.from_user.id} в чате {message.chat.id}")
    if message.from_user.username != "sadea12":
        await message.answer("⚠️ У вас нет прав для использования этой команды.")
        return
    chat_id = message.chat.id
    # Проверяем наличие игры
    if chat_id not in active_games:
        await message.answer("ℹ️ В этом чате нет активной игры.")
        return
    # Отменяем таймер ожидания, если он есть
    if chat_id in join_timers:
        del join_timers[chat_id]
    # Удаляем игру
    del active_games[chat_id]
    await message.answer("🛑 Игра была принудительно завершена.")

@dp.message()
async def unhandled_message_handler(message: types.Message):
    logging.warning(f"Получено необработанное сообщение: '{message.text}' от пользователя {message.from_user.id} в чате {message.chat.id}")
    # Можно добавить ответ пользователю для отладки, но пока ограничимся логом
    # await message.answer("Получил ваше сообщение, но не нашел обработчик команды.")

async def on_startup(bot: Bot) -> None:
    """Действия при запуске бота"""
    logger.info("Выполняется on_startup...")
    await bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook установлен на {WEBHOOK_URL}")
    # Устанавливаем команды бота для отображения в меню
    private_commands = [
        types.BotCommand(command="start", description="Начать диалог с ботом"),
        types.BotCommand(command="help", description="Правила игры и список команд")
    ]
    group_commands = [
        types.BotCommand(command="start_21", description="Начать новую игру в 21"),
        types.BotCommand(command="game_status", description="Проверить статус текущей игры"),
        types.BotCommand(command="help", description="Правила игры и список команд"),
        types.BotCommand(command="clear", description="Принудительно завершить игру (только @sadea12)"),
    ]
    await bot.set_my_commands(private_commands, scope=types.BotCommandScopeDefault())
    await bot.set_my_commands(group_commands, scope=types.BotCommandScopeAllGroupChats())
    logger.info("Команды бота установлены для разных типов чатов")

def start_webhook():
    """Запуск бота с использованием webhook (для деплоя на Render)"""
    # Настраиваем веб-приложение
    app = web.Application()
    # Регистрируем on_startup хук aiohttp, чтобы установить webhook и команды в одной event loop
    async def _on_app_startup(app):
        logger.info("Запуск on_startup(bot) через app.on_startup")
        try:
            await on_startup(bot)
        except Exception as e:
            logger.error(f"Ошибка при выполнении on_startup: {e}", exc_info=True)
    app.on_startup.append(_on_app_startup)
    
    # Настройка вебхука и регистрация обработчика обновлений
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        # Сюда можно передать пользовательские аргументы, если нужно, они будут доступны в хэндлерах
        # например: handle_unknown_updates=True (хотя по умолчанию True)
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    logger.info(f"SimpleRequestHandler зарегистрирован для пути {WEBHOOK_PATH}")
    
    # Добавляем обработчик корневого маршрута для healthcheck
    async def health_check(request):
        # Логируем health check запросы, чтобы видеть, что Render их делает
        logger.debug(f"Health check запрос от {request.remote} к {request.path}")
        return web.Response(text=f"Бот работает. Aiogram Webhook (SimpleRequestHandler) активен. Путь: {WEBHOOK_URL}")
    
    app.router.add_get("/", health_check)
    logger.info(f"Health check зарегистрирован для пути /")
    
    # Диагностическая информация
    logger.info(f"Используется BOT_TOKEN (маскировано): ...{BOT_TOKEN[-5:]}")
    logger.info(f"Webhook URL (из config): {WEBHOOK_URL}")
    logger.info(f"Webhook PATH (из config): {WEBHOOK_PATH}")
    # logger.info(f"Полный путь Webhook: {WEBHOOK_URL}") # Это дублирует предыдущую строку
    logger.info(f"Веб-сервер запускается на {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    
    # Настройка веб-сервера aiogram (если используется setup_application)
    # setup_application(app, dp, bot=bot) # Закомментировано, так как используем SimpleRequestHandler.register выше
    # logger.info("setup_application(app, dp, bot=bot) выполнен (если раскомментировано)")
    
    # Запуск веб-сервера без обработки сигналов, чтобы при SIGTERM не вызывались on_shutdown-хуки
    # Это специфичная настройка, если вы уверены, что она нужна.
    # Для более "чистого" завершения aiogram бота, обычно handle_signals=True (по умолчанию).
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, handle_signals=False, shutdown_timeout=0, access_log=None) 
    # access_log=None, чтобы не дублировать логи с logging.getLogger('aiohttp.access').setLevel(logging.DEBUG)
    # если хотите стандартный формат логов aiohttp, уберите access_log=None и .setLevel(logging.DEBUG) выше

if __name__ == "__main__":
    # Запуск бота только в режиме webhook
    # Добавим лог перед проверкой условий
    logger.info(f"Запуск __main__. IS_RENDER: {os.environ.get('IS_RENDER')}, sys.argv: {sys.argv}")
    if os.environ.get('IS_RENDER') or '--webhook' in sys.argv:
        logger.info("Запуск бота в режиме webhook (для деплоя)")
        # Вызов on_startup теперь происходит внутри start_webhook, если это необходимо для aiogram 3.x стиля
        # dp.startup.register(on_startup) # Если on_startup должен вызываться при старте Dispatcher
        # Однако, set_webhook обычно вызывается один раз при запуске приложения.
        # В aiogram 3.x on_startup часто используется для регистрации в dp.startup.
        # Но так как у вас start_webhook() и есть on_startup(bot), который вы могли бы вызвать перед web.run_app,
        # давайте убедимся, что set_webhook вызывается.
        # Мы уже вызываем on_startup внутри dp.startup.register(on_startup) или напрямую.
        # В вашем случае on_startup() устанавливает вебхук и команды.
        # Это должно быть сделано до того, как веб-сервер начнет принимать запросы.
        # Самый простой способ - вызвать его перед run_app, но убедившись, что bot и dp инициализированы.
        
        # Переносим вызов on_startup внутрь start_webhook перед запуском app
        # dp.startup.register(on_startup) # Если хотите, чтобы on_startup вызывался при старте диспетчера
        
        start_webhook() # Внутри этой функции теперь должен быть вызов on_startup
    else:
        logger.error("Локальный запуск не разрешен текущей конфигурацией. Установите IS_RENDER или используйте --webhook.")
        sys.exit(1) 