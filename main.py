# -*- coding: utf-8 -*-
import json
import random
import os
import time
import requests
import urllib.parse
import difflib
import logging
import tempfile
import asyncio
from contextlib import contextmanager
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from pydub import AudioSegment
from background import keep_alive
import g4f
from g4f.client import AsyncClient

# Логи и конфиг
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("MEMEZVUKACH")
MEMES_JSON = "memes.json"
AUDIO_DIR = "meme_audios"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Мемные звуковые эффекты
MEME_SOUNDS = [
    ("scream", "https://freesound.org/data/previews/269/269764_4299048-lq.mp3"),
    ("burp", "https://freesound.org/data/previews/136/136181_2396973-lq.mp3"),
    ("cry", "https://freesound.org/data/previews/193/193353_2431407-lq.mp3"),
    ("laugh", "https://freesound.org/data/previews/203/203714_2619675-lq.mp3"),
    ("drake", "https://freesound.org/data/previews/364/364918_5910492-lq.mp3"),
    ("airhorn", "https://freesound.org/data/previews/154/154955_2701569-lq.mp3"),
    ("vine_boom", "https://freesound.org/data/previews/622/622181_11866629-lq.mp3"),
    ("anime_wow", "https://freesound.org/data/previews/156/156859_2538033-lq.mp3")
]

# История фраз для каждого пользователя
user_phrase_history = {}

# Эмодзи для интерфейса
EMOJIS = {
    "welcome": "🚀",
    "help": "🔍",
    "search": "🔥",
    "random": "🎲",
    "audio": "🎸",
    "loading": "⏳",
    "error": "😕",
    "success": "🌟",
    "meme": "🦄",
    "vibe": "🦁"
}
EMOJI_MAP = {
    "акула": "🦈", "кот": "😺", "собака": "🐶", "динозавр": "🦖",
    "поезд": "🚂", "ракета": "🚀", "алкоголь": "🍺", "танц": "🕺",
    "крича": "🗣️", "бомба": "💣", "космос": "🪐", "пустыня": "🏜️",
    "город": "🏙️", "лес": "🌴", "море": "🌊", "еда": "🍕",
    "фрукт": "🍍", "кофей": "☕", "магия": "🧙", "взрыв": "💥",
    "кринж": "😹", "угар": "🎉", "жесть": "🦁", "абсурд": "🦄",
    "похер": "🦊", "пушка": "🌟"
}

# Меню с эмодзи
MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔥 Найти Шедевр", "🎲 Случайный Вайб"],
        ["🔍 Гид по Мемам"]
    ],
    resize_keyboard=True
)

# Инициализация g4f клиента для поиска фото
async_client = AsyncClient()
PHOTO_PRESET = """Ты бот, который получает название мемного животного из группы итальянских мемов (например, Bombardier Crocodile (Бомбардиро Крокодило)). Верни только одну ссылку на фото этого животного или на сайт с ним. Если фото не найдено, верни 'Фото не найдено 😕'. Ничего не объясняй, только ссылка или указанный текст."""

# Управление временными файлами
@contextmanager
def temp_audio_file():
    mp3_fd, mp3_path = tempfile.mkstemp(suffix=".mp3", dir=AUDIO_DIR)
    try:
        yield mp3_path
    finally:
        time.sleep(2)
        try:
            os.close(mp3_fd)
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
                logger.info(f"Deleted temp file: {mp3_path}")
        except Exception as e:
            logger.warning(f"Failed to delete temp file {mp3_path}: {e}")

# Генерация эмодзи по описанию
def generate_emoji(description):
    description = description.lower()
    for word, emoji in EMOJI_MAP.items():
        if word in description:
            logger.info(f"Selected emoji '{emoji}' for keyword '{word}' in description")
            return emoji
    default_emoji = random.choice(["🦄", "🌟", "🦁", "🦊", "🎸"])
    logger.info(f"No matching keyword found, selected default emoji '{default_emoji}'")
    return default_emoji

# Генерация фразы
def generate_funny_phrase(user_id):
    if user_id not in user_phrase_history:
        user_phrase_history[user_id] = []
    user_phrases = user_phrase_history[user_id]
    
    prompt = "Сгенерируй короткую, остроумную фразу на русском в стиле мемного юмора, не длиннее 50 символов."
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}"
    
    logger.info(f"Sending request for phrase for user {user_id}")
    for attempt in range(5):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            phrase = response.text.strip()
            if phrase and len(phrase) <= 50 and phrase not in user_phrases:
                filter_url = f"https://www.purgomalum.com/service/containsprofanity?text={urllib.parse.quote(phrase)}"
                filter_response = requests.get(filter_url, timeout=5)
                if filter_response.text.lower() == "false":
                    logger.info(f"Generated phrase for user {user_id}: [filtered]")
                    user_phrases.append(phrase)
                    if len(user_phrases) > 20:
                        user_phrases.pop(0)
                    return phrase
            logger.warning(f"Invalid or repeated phrase for user {user_id}: [filtered]")
        except Exception as e:
            logger.error(f"Phrase generation error (attempt {attempt + 1}) for user {user_id}: {e}")
    
    backup_phrases = [
        "Шедевр в эфире! 🌟",
        "Мемный взрыв! 🎉",
        "Вайб на миллион! 🦁",
        "Это просто пушка! 🦄"
    ]
    available_phrases = [p for p in backup_phrases if p not in user_phrases]
    if not available_phrases:
        user_phrases.clear()
        available_phrases = backup_phrases
    phrase = random.choice(available_phrases)
    user_phrases.append(phrase)
    if len(user_phrases) > 20:
        user_phrases.pop(0)
    logger.info(f"Selected backup phrase for user {user_id}: {phrase}")
    return phrase

# Поиск фото через g4f
async def find_meme_photo(meme_name_english, meme_name_russian):
    try:
        query = f"{meme_name_english} ({meme_name_russian})"
        response = await async_client.chat.completions.create(
            model="searchgpt",
            provider=g4f.Provider.PollinationsAI,
            messages=[
                {"role": "system", "content": PHOTO_PRESET},
                {"role": "user", "content": query}
            ],
            web_search=False,
            stream=False
        )
        photo_url = response.choices[0].message.content.strip()
        logger.info(f"Photo URL for {query}: {photo_url}")
        return photo_url if photo_url != "Фото не найдено 😕" else "Фото не найдено 😕"
    except Exception as e:
        logger.error(f"Photo search error for {query}: {e}")
        return "Фото не найдено 😕"

# Загрузка мемов
def load_memes():
    try:
        if not os.path.exists(MEMES_JSON):
            logger.error(f"Memes file {MEMES_JSON} not found")
            return []
        with open(MEMES_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("memes", [])
    except Exception as e:
        logger.error(f"Load memes error: {e}")
        return []

# Поиск ближайшего мема по названию
def find_closest_meme(query, memes):
    query = query.lower().strip()
    logger.info(f"Searching for meme by name: {query}")
    names = [m["name"].lower() for m in memes]
    closest = difflib.get_close_matches(query, names, n=1, cutoff=0.3)
    return next((m for m in memes if m["name"].lower() == closest[0]), None) if closest else None

# Поиск мема по описанию
def find_meme_by_description(query, memes):
    query = query.lower().strip()
    logger.info(f"Searching for meme by description: {query}")
    descriptions = [(m, m["description"].lower()) for m in memes]
    best_match = None
    best_ratio = 0.0
    for meme, desc in descriptions:
        ratio = difflib.SequenceMatcher(None, query, desc).ratio()
        if ratio > best_ratio and ratio > 0.5:
            best_ratio = ratio
            best_match = meme
    if best_match:
        logger.info(f"Found meme by description: {best_match['name']} (ratio: {best_ratio})")
    return best_match

# Загрузка мемного звука
def download_meme_sound(sound_url, filename):
    try:
        response = requests.get(sound_url, stream=True, timeout=10)
        response.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        file_size = os.path.getsize(filename)
        logger.info(f"Downloaded meme sound to {filename}, size: {file_size} bytes")
        return True
    except Exception as e:
        logger.error(f"Failed to download meme sound {sound_url}: {e}")
        return False

# Генерация аудио с мемными эффектами
async def generate_meme_audio(text, filename, funny_phrase):
    sound_effect = random.choice(MEME_SOUNDS)
    effect_name, effect_url = sound_effect
    
    prompt = (
        f"Озвучь с итальянским вайбом, энергично и с юмором: {text}. "
        f"Добавь короткую фразу: '{funny_phrase}'"
    )
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai-audio&voice=echo&attitude=excited"
    
    logger.info(f"Sending audio request to API for text: {text}")
    for attempt in range(5):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = os.path.getsize(filename)
            logger.info(f"Generated audio file {filename}, size: {file_size} bytes")
            if file_size < 1000:
                logger.warning(f"Generated audio file {filename} too small: {file_size} bytes")
                return False
            
            with tempfile.NamedTemporaryFile(suffix=".mp3", dir=AUDIO_DIR, delete=False) as effect_file:
                if download_meme_sound(effect_url, effect_file.name):
                    try:
                        main_audio = AudioSegment.from_mp3(filename)
                        effect_audio = AudioSegment.from_mp3(effect_file.name)
                        combined = main_audio + effect_audio
                        combined.export(filename, format="mp3")
                        logger.info(f"Successfully added meme sound effect '{effect_name}' to {filename}")
                    except Exception as e:
                        logger.warning(f"Failed to overlay meme sound: {e}")
            
            final_size = os.path.getsize(filename)
            logger.info(f"Final audio generated: {filename}, size: {final_size} bytes")
            return True
        except requests.HTTPError as e:
            logger.error(f"Audio API HTTP error (attempt {attempt + 1}): {e}")
        except Exception as e:
            logger.error(f"Audio API error (attempt {attempt + 1}): {e}")
    
    logger.error("Failed to generate audio after 5 attempts")
    return False

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Готов к мемному вайбу! 🚀🦄\n\n"
        "Назови мем или выбери случайный.\n"
        "Погнали за шедеврами! 🎸",
        reply_markup=MENU_KEYBOARD
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Гид по Мемам 🔍🌟\n\n"
        "Я бот, зажигающий мемные вайбы с итальянским шармом 🎸\n\n"
        "Что умею:\n"
        "- Найти мем по названию или описанию\n"
        "- Выдать случайный шедевр\n"
        "- Озвучить названия с прикольным акцентом\n"
        "- Показать фото мемных героев\n\n"
        "Команды:\n"
        "/start — старт вайба\n"
        "/help — этот гид\n"
        "/random — случайный мем\n\n"
        "Готов к движу? 🦁🎉",
        reply_markup=MENU_KEYBOARD
    )

# Команда /random
async def random_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await update.message.reply_text(
            f"Выбираю шедевр... ⏳🦄"
        )
        await asyncio.sleep(1.5)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(
                f"Мемы не найдены! 😕 Попробуй позже.",
                reply_markup=MENU_KEYBOARD
            )
            return
        
        meme = random.choice(memes)
        user_id = update.effective_user.id
        response = await prepare_meme_response(meme, user_id)
        await msg.delete()
        await send_meme_response(update, context, response, meme)
        
    except Exception as e:
        logger.error(f"Random meme error: {e}")
        await update.message.reply_text(
            f"Мем ускользнул! 😕🦁 Пробуй ещё!",
            reply_markup=MENU_KEYBOARD
        )

# Поиск мема
async def search_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Назови шедевр или опиши его! 🦁🔥",
        reply_markup=MENU_KEYBOARD
    )

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "🔥 Найти Шедевр":
        return await search_meme(update, context)
    elif text == "🎲 Случайный Вайб":
        return await random_meme(update, context)
    elif text == "🔍 Гид по Мемам":
        return await help_command(update, context)
    
    try:
        msg = await update.message.reply_text(
            f"Ищу твой мем... ⏳🎸"
        )
        await asyncio.sleep(1.5)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(
                f"Мемы не найдены! 😕🔍 Попробуй другое.",
                reply_markup=MENU_KEYBOARD
            )
            return
        
        meme = find_closest_meme(text, memes)
        if not meme or difflib.SequenceMatcher(None, text.lower(), meme["name"].lower()).ratio() < 0.6:
            meme = find_meme_by_description(text, memes) or meme
        
        if not meme:
            await msg.edit_text(
                f"Мем не найден! 😕🦄 Попробуй другое.",
                reply_markup=MENU_KEYBOARD
            )
            return
        
        user_id = update.effective_user.id
        response = await prepare_meme_response(meme, user_id)
        await msg.delete()
        await send_meme_response(update, context, response, meme)
        
    except Exception as e:
        logger.error(f"Handle text error: {e}")
        await update.message.reply_text(
            f"Ошибка поиска! 😕🚀 Пробуй снова.",
            reply_markup=MENU_KEYBOARD
        )

# Подготовка ответа
async def prepare_meme_response(meme, user_id):
    emoji = generate_emoji(meme["description"])
    funny_phrase = generate_funny_phrase(user_id)
    voice_text = f"{meme['name_english']}"
    
    logger.info(f"Preparing response for meme '{meme['name']}' for user {user_id} with emoji '{emoji}'")
    
    # Параллельное выполнение генерации аудио и поиска фото
    audio_task = asyncio.create_task(generate_meme_audio(voice_text, f"{AUDIO_DIR}/temp_{user_id}.mp3", funny_phrase))
    photo_task = asyncio.create_task(find_meme_photo(meme["name_english"], meme["name"]))
    
    audio_success, photo_url = await asyncio.gather(audio_task, photo_task)
    
    try:
        return {
            "type": "voice" if audio_success else "text",
            "voice_text": voice_text,
            "voice_file": f"{AUDIO_DIR}/temp_{user_id}.mp3" if audio_success else None,
            "caption": (
                f"{emoji} Озвучка... 🎸\n"
                f"{meme['name_english']}, {meme['name']}\n\n"
                f"{meme['description']}\n\n"
                f"{photo_url}\n\n"
                f"{funny_phrase} Ещё мем? 🌟"
            ),
            "text": (
                f"{emoji} {meme['name_english']}, {meme['name']} 🦄\n\n"
                f"{meme['description']}\n\n"
                f"{photo_url}\n\n"
                f"{funny_phrase} Аудио не вышло, но вайб есть! 🎉 Ещё?"
            ),
            "reply_markup": MENU_KEYBOARD
        }
    except Exception as e:
        logger.error(f"Prepare meme response error for user {user_id}: {e}")
        return {
            "type": "text",
            "text": (
                f"{emoji} {meme['name_english']}, {meme['name']} 🦄\n\n"
                f"{meme['description']}\n\n"
                f"{photo_url}\n\n"
                f"{funny_phrase} Мем без озвучки! 😕 Ещё?"
            ),
            "reply_markup": MENU_KEYBOARD
        }

# Отправка ответа
async def send_meme_response(update: Update, context: ContextTypes.DEFAULT_TYPE, response, meme):
    try:
        if response["type"] == "voice":
            with open(response["voice_file"], "rb") as audio_file:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id,
                    action="record_voice"
                )
                await update.message.reply_voice(
                    voice=audio_file,
                    caption=response["caption"],
                    reply_markup=response["reply_markup"]
                )
            logger.info(f"Voice message sent successfully")
            os.remove(response["voice_file"])
        else:
            await update.message.reply_text(
                response["text"],
                reply_markup=response["reply_markup"]
            )
    except Exception as e:
        logger.error(f"Send meme response error: {e}")
        emoji = generate_emoji(meme["description"])
        await update.message.reply_text(
            f"{emoji} {meme['name_english']}, {meme['name']} 🦄\n\n"
            f"{meme['description']}\n\n"
            f"Фото не найдено 😕\n\n"
            f"Мем без вайба! 😕 Погнали дальше? 🌟",
            reply_markup=MENU_KEYBOARD
        )

# Основной цикл
def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN not set in environment variables")
        raise ValueError("TELEGRAM_TOKEN is required")
    
    logger.info("MEMEZVUKACH стартует...")
    
    try:
        app = Application.builder().token(TOKEN).build()
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        raise
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("random", random_meme))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("Бот готов зажигать вайб!")
    keep_alive()
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        raise

if __name__ == "__main__":
    main()
