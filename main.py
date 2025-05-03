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
    ("scream", "https://freesound.org/data/previews/269/269764_4299048-lq.mp3"),  # Громкий ор
    ("burp", "https://freesound.org/data/previews/136/136181_2396973-lq.mp3"),   # Рыгание
    ("cry", "https://freesound.org/data/previews/193/193353_2431407-lq.mp3"),    # Плач
    ("laugh", "https://freesound.org/data/previews/203/203714_2619675-lq.mp3"),  # Угарный смех
    ("drake", "https://freesound.org/data/previews/364/364918_5910492-lq.mp3"),  # Drake "Yawn"
    ("airhorn", "https://freesound.org/data/previews/154/154955_2701569-lq.mp3"), # Airhorn
    ("vine_boom", "https://freesound.org/data/previews/622/622181_11866629-lq.mp3"), # Vine Boom
    ("anime_wow", "https://freesound.org/data/previews/156/156859_2538033-lq.mp3") # Anime Wow
]

# История фраз для каждого пользователя
user_phrase_history = {}

# Эмодзи для мемов
EMOJIS = {
    "welcome": "🚀",
    "help": "ℹ️",
    "search": "🔥",
    "random": "🎰",
    "audio": "🎙️",
    "loading": "⏳",
    "error": "😅",
    "success": "💥",
    "meme": "🎉",
    "action": "🧨",
    "fail": "🫠",
    "vibe": "😎"
}
EMOJI_MAP = {
    "акула": "🦈", "кот": "😼", "собака": "🐶", "динозавр": "🦖",
    "поезд": "🚂", "ракета": "🚀", "алкоголь": "🍺", "танц": "🕺",
    "крича": "🗣️", "бомба": "💣", "космос": "🪐", "пустыня": "🏜️",
    "город": "🏙️", "лес": "🌴", "море": "🌊", "еда": "🍔",
    "фрукт": "🍍", "кофе": "☕", "магия": "✨", "взрыв": "💥",
    "кринж": "😬", "угар": "😂", "жесть": "🦍", "абсурд": "🤪",
    "взлёт": "🛫", "жара": "🌞", "похер": "😏", "пушка": "🎯",
    "игра": "🎮", "диск": "💿", "приключение": "🪂", "вкус": "🍕"
}

# Меню с эмодзи
MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔥 Найти мем", "🎰 Случайный мем"],
        ["ℹ️ Как работает"]
    ],
    resize_keyboard=True
)

# Управление временными файлами
@contextmanager
def temp_audio_files():
    mp3_fd, mp3_path = tempfile.mkstemp(suffix=".mp3", dir=AUDIO_DIR)
    ogg_fd, ogg_path = tempfile.mkstemp(suffix=".ogg", dir=AUDIO_DIR)
    try:
        yield mp3_path, ogg_path
    finally:
        time.sleep(2)
        for fd, path in [(mp3_fd, mp3_path), (ogg_fd, ogg_path)]:
            try:
                os.close(fd)
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Deleted temp file: {path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {path}: {e}")

# Генерация эмодзи по описанию
def generate_emoji(description):
    description = description.lower()
    for word, emoji in EMOJI_MAP.items():
        if word in description:
            logger.info(f"Selected emoji '{emoji}' for keyword '{word}' in description")
            return emoji
    default_emoji = random.choice(["😂", "😬", "🤪", "🦍", "🍉"])
    logger.info(f"No matching keyword found, selected default emoji '{default_emoji}'")
    return default_emoji

# Генерация дерзкой фразы без мата
def generate_funny_phrase(user_id):
    if user_id not in user_phrase_history:
        user_phrase_history[user_id] = []
    user_phrases = user_phrase_history[user_id]
    
    prompt = "Сгенерируй короткую, дерзкую, абсурдную фразу на русском в стиле TikTok, с лёгким сленгом (например, 'похер', 'нахер', 'фигня'), без мата, угарную, не длиннее 50 символов."
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}"
    
    logger.info(f"Sending request for funny phrase for user {user_id}")
    for attempt in range(5):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            phrase = response.text.strip()
            if phrase and len(phrase) <= 50 and phrase not in user_phrases:
                # Фильтрация через PurgoMalum
                filter_url = f"https://www.purgomalum.com/service/containsprofanity?text={urllib.parse.quote(phrase)}"
                filter_response = requests.get(filter_url, timeout=5)
                if filter_response.text.lower() == "false":
                    logger.info(f"Generated funny phrase for user {user_id}: [filtered]")
                    user_phrases.append(phrase)
                    if len(user_phrases) > 20:
                        user_phrases.pop(0)
                    return phrase
            logger.warning(f"Invalid or repeated funny phrase for user {user_id}: [filtered]")
        except Exception as e:
            logger.error(f"Funny phrase generation error (attempt {attempt + 1}) for user {user_id}: {e}")
    
    # Запасная фраза без мата
    backup_phrases = [
        "Гори, бро, это пушка! 🎯",
        "Фигня, но угар! 😂",
        "Похер, мем топ! 💣",
        "Нахер, жги ещё! 🦍"
    ]
    available_phrases = [p for p in backup_phrases if p not in user_phrases]
    if not available_phrases:
        user_phrases.clear()
        available_phrases = backup_phrases
    phrase = random.choice(available_phrases)
    user_phrases.append(phrase)
    if len(user_phrases) > 20:
        user_phrases.pop(0)
    logger.info(f"Selected backup funny phrase for user {user_id}: {phrase}")
    return phrase

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
def generate_meme_audio(text, filename):
    sound_effect = random.choice(MEME_SOUNDS)
    effect_name, effect_url = sound_effect
    
    prompt = (
        f"Озвучь как дерзкий итальянский пацан с TikTok-вайбом, с абсурдной энергией и лёгким сленгом (похер, нахер, фигня), без мата: {text}"
    )
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai-audio&voice=echo&attitude=aggressive"
    
    logger.info(f"Sending audio request to API")
    for attempt in range(5):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = os.path.getsize(filename)
            if file_size < 1000:
                logger.warning(f"Generated audio file {filename} too small: {file_size} bytes")
                return False
            
            # Наложение мемного звука
            with tempfile.NamedTemporaryFile(suffix=".mp3", dir=AUDIO_DIR, delete=False) as effect_file:
                if download_meme_sound(effect_url, effect_file.name):
                    try:
                        main_audio = AudioSegment.from_mp3(filename)
                        effect_audio = AudioSegment.from_mp3(effect_file.name)
                        # Наложение эффекта в конце
                        combined = main_audio + effect_audio
                        combined.export(filename, format="mp3")
                        logger.info(f"Added meme sound effect '{effect_name}' to {filename}")
                    except Exception as e:
                        logger.warning(f"Failed to overlay meme sound: {e}")
            
            logger.info(f"Audio generated: {filename}, size: {os.path.getsize(filename)} bytes")
            return True
        except requests.HTTPError as e:
            logger.error(f"Audio API HTTP error (attempt {attempt + 1}): {e}")
        except Exception as e:
            logger.error(f"Audio API error (attempt {attempt + 1}): {e}")
    
    logger.error("Failed to generate audio after 5 attempts")
    return False

# Конвертация в OGG
def convert_to_ogg(mp3_path, ogg_path):
    try:
        audio = AudioSegment.from_mp3(mp3_path)
        audio = audio.set_frame_rate(44100).set_channels(1)
        audio.export(ogg_path, format="ogg", codec="libopus", bitrate="64k")
        file_size = os.path.getsize(ogg_path)
        logger.info(f"Converted to OGG: {ogg_path}, size: {file_size} bytes")
        return file_size > 1000
    except Exception as e:
        logger.error(f"Convert error: {e}")
        return False

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJIS['welcome']} MemeZvukach: твой мемный движ! 🎉🦍\n\n"
        "Бро, врываемся в TikTok-вайб! 😎💿\n"
        f"🔥 Найди мем по названию или вайбу 🧨\n"
        f"🎰 Крути рандом для угара 🎮\n"
        f"ℹ️ Разбери, как жечь как босс 🌞\n\n"
        "Погнали ловить мемы! 💥🍕",
        reply_markup=MENU_KEYBOARD
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJIS['help']} Как жечь с MemeZvukach? 🚀🎯\n\n"
        "Я твой мемный кореш, кидаю мемы с угарной озвучкой! 😂🪂\n\n"
        "Что умею:\n"
        f"🔥 Найти мем — вбей название или вайб 🌩️\n"
        f"🎰 Случайный мем — сюрприз с TikTok-огнём 🎉\n"
        f"{EMOJIS['audio']} Озвучка — дерзкий пацан + мемные звуки 🎙️💣\n\n"
        "Команды:\n"
        f"/start — врываемся в движ! {EMOJIS['welcome']}\n"
        f"/help — этот гайд по угару {EMOJIS['help']}\n"
        f"/random — рандомный мемный взрыв {EMOJIS['random']}\n\n"
        "Го тусить, бро! 😎🍉",
        reply_markup=MENU_KEYBOARD
    )

# Команда /random
async def random_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await update.message.reply_text(
            f"Копаю мемный клад... {EMOJIS['loading']}🧨"
        )
        await asyncio.sleep(1.5)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(
                f"{EMOJIS['error']} Мемы кончились, фигня! 😅 Вбей что-нибудь! 🫠",
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
            f"{EMOJIS['error']} Чёт мем не взлетел, давай ещё раз! 😅🫠",
            reply_markup=MENU_KEYBOARD
        )

# Поиск мема
async def search_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJIS['search']} Вбей мем или его вайб, бро! 😎🔥",
        reply_markup=MENU_KEYBOARD
    )

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "🔥 Найти мем":
        return await search_meme(update, context)
    elif text == "🎰 Случайный мем":
        return await random_meme(update, context)
    elif text == "ℹ️ Как работает":
        return await help_command(update, context)
    
    try:
        msg = await update.message.reply_text(
            f"Ищу твой мем, держись... {EMOJIS['loading']}🌩️"
        )
        await asyncio.sleep(1.5)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(
                f"{EMOJIS['error']} Мемы не найдены, похер! 😅 Вбей другой! 🫠",
                reply_markup=MENU_KEYBOARD
            )
            return
        
        meme = find_closest_meme(text, memes)
        if not meme or difflib.SequenceMatcher(None, text.lower(), meme["name"].lower()).ratio() < 0.6:
            meme = find_meme_by_description(text, memes) or meme
        
        if not meme:
            await msg.edit_text(
                f"{EMOJIS['error']} Мем ускользнул, фигня! 😅 Давай другой! 🫠",
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
            f"{EMOJIS['error']} Что-то пошло не так, нахер! 😅 Го заново! 🫠",
            reply_markup=MENU_KEYBOARD
        )

# Подготовка ответа
async def prepare_meme_response(meme, user_id):
    emoji = generate_emoji(meme["description"])
    funny_phrase = generate_funny_phrase(user_id)
    voice_text = f"{meme['name']}! {meme['tiktok_phrase']}, {funny_phrase}"
    
    logger.info(f"Preparing response for meme '{meme['name']}' for user {user_id} with emoji '{emoji}'")
    
    try:
        return {
            "type": "voice",
            "voice_text": voice_text,
            "caption": (
                f"{emoji} {meme['name']} 🎉\n\n"
                f"{meme['description']} 📜\n\n"
                f"{EMOJIS['success']} Ещё мемчик, бро? 💥😎"
            ),
            "reply_markup": MENU_KEYBOARD
        }
    except Exception as e:
        logger.error(f"Prepare meme response error for user {user_id}: {e}")
        return {
            "type": "text",
            "text": (
                f"{EMOJIS['error']} Мем сломался, фигня! 😅\n\n"
                f"{emoji} {meme['name']} 🎉\n{meme['description']} 📜\n\n"
                f"Го заново, бро? 🫠"
            ),
            "reply_markup": MENU_KEYBOARD
        }

# Отправка ответа
async def send_meme_response(update: Update, context: ContextTypes.DEFAULT_TYPE, response, meme):
    try:
        if response["type"] == "voice":
            with temp_audio_files() as (mp3_path, ogg_path):
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id,
                    action="record_voice"
                )
                audio_success = False
                if generate_meme_audio(response["voice_text"], mp3_path):
                    if convert_to_ogg(mp3_path, ogg_path):
                        audio_success = True
                        with open(ogg_path, "rb") as audio_file:
                            await update.message.reply_voice(
                                voice=audio_file,
                                caption=response["caption"],
                                reply_markup=response["reply_markup"]
                            )
                        logger.info(f"Voice message sent successfully")
                        return
                
                logger.warning("Audio generation failed, sending text response")
                emoji = generate_emoji(meme["description"])
                await update.message.reply_text(
                    f"{emoji} {meme['name']} 🎉\n\n"
                    f"{meme['description']} 📜\n\n"
                    f"{EMOJIS['error']} Аудио не зашло, похер! 😅 Мем пушка! 🫠",
                    reply_markup=response["reply_markup"]
                )
        else:
            await update.message.reply_text(
                response["text"],
                reply_markup=response["reply_markup"]
            )
    except Exception as e:
        logger.error(f"Send meme response error: {e}")
        emoji = generate_emoji(meme["description"])
        await update.message.reply_text(
            f"{EMOJIS['error']} Мем потерялся, фигня! 😅\n\n"
            f"{emoji} {meme['name']} 🎉\n{meme['description']} 📜\n\n"
            f"Го дальше, бро? 💥😎",
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
    
    logger.info("Бот готов жечь мемы!")
    keep_alive()  # Запускаем Flask для "keep alive"
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        raise

if __name__ == "__main__":
    main()
