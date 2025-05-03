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

# Локальный список угарных фраз с лёгким матом
FUNNY_PHRASES = [
    "Ёпт, башню рвёт, херня! 🤯",
    "Фигня полная, но угар! 😝",
    "Чё за хрень, мать её?! 💥",
    "Кринж, но пипец топ! 💀",
    "Ору, как псих, ёпт! 🗣️",
    "Блин, разнос, хер с ним! 🔥",
    "Блэ, мем порвал жопу! 🍑",
    "Нафиг мозг, жги, чёрт! 🦍",
    "Похер всё, я в агонии! 🏆",
    "Пипец, а не мем, блин! 😵",
    "Го в тренды, херня эта! 🌈",
    "Чё за дичь, но пушка! 💣",
    "Мозг в ауте, угар, ёпт! 🦒",
    "Блин, ору, пипец! 😣",
    "Кринж уровня бог, херня! 💿",
    "Жесть, держись, чёрт! ⚡",
    "Похер всё, мем тащит! 🦄",
    "Это не мем, это пипец! 😈",
    "Трындец, башка в шоке! 🪐",
    "Блин, где мой фильтр, ёпт?! 🦈",
    "Огонь, мать её, жги! 🔥",
    "Пипец, я в астрале! 🌌",
    "Херня, но ржака, блэ! 😝",
    "Мем порвал, как туз! 🃏",
    "Чё за дичь, но топ, ёпт! 🦖",
    "Блин, я в ауте, херня! 💀",
    "Кринж, но ору, чёрт! 🗣️",
    "Похер, это разрыв! 💥",
    "Блэ, мем жёсткий, ёпт! 🍺",
    "Нафиг всё, я в шоке! 😵",
    "Пипец, держи, блин! 🦒",
    "Тусим, херня, пипец! 🪩",
    "Мозг офф, угар он! 🌟",
    "Фиг с ним, это топ! 🚀",
    "Жесть, я в кринже, ёпт! 😣",
    "Пипец, мем унёс! 🦄",
    "Блин, это нереал, чёрт! 😈",
    "Ору, как псих, блэ! 🗣️",
    "Кринж, но пипец! 💀",
    "Нафиг всё, жги, ёпт! 🔥",
    "Херня, но пушка, блин! 💣",
    "Похер, я в трансе! 🪐",
    "Блэ, мем разъебал! 🍑",
    "Трындец, я в агонии! 🦍",
    "Блин, разнос, херня! 🏆",
    "Чё за дичь, пипец! 😵",
    "Мем порвал, как бог! 🌈",
    "Фигня, но угар, ёпт! 😝",
    "Пипец, я в шоке! 💥",
    "Топ, мать её, топ! 🦄"
]

# Мемные звуковые эффекты
MEME_SOUNDS = [
    ("scream", "https://freesound.org/data/previews/269/269764_4299048-lq.mp3"),  # Громкий ор
    ("burp", "https://freesound.org/data/previews/136/136181_2396973-lq.mp3"),   # Рыгание
    ("cry", "https://freesound.org/data/previews/193/193353_2431407-lq.mp3"),    # Плач
    ("laugh", "https://freesound.org/data/previews/203/203714_2619675-lq.mp3")   # Угарный смех
]

# История фраз для каждого пользователя
user_phrase_history = {}

# Эмодзи для мемов
EMOJIS = {
    "start": "😈",
    "help": "🦖",
    "search": "🤟",
    "random": "🪩",
    "audio": "🎙️",
    "loading": "👾",
    "error": "😣",
    "success": "🔥",
    "meme": "🦄"
}
EMOJI_MAP = {
    "акула": "🦈", "кот": "😼", "собака": "🐶", "динозавр": "🦖",
    "поезд": "🚂", "ракета": "🚀", "алкоголь": "🍺", "танц": "🕺",
    "крича": "🗣️", "бомба": "💣", "космос": "🪐", "пустыня": "🏜️",
    "город": "🏙️", "лес": "🌴", "море": "🌊", "еда": "🍔",
    "фрукт": "🍍", "кофе": "☕", "магия": "✨", "взрыв": "💥",
    "кринж": "💀", "угар": "🦒", "жесть": "🔥", "абсурд": "😝"
}

# Меню с эмодзи
MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["❓Найти мем🔍", "🎲Рандом🎲"],
        ["🚀Помощь🆘"]
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
    default_emoji = random.choice(["🦒", "💀", "😝", "🔥"])
    logger.info(f"No matching keyword found, selected default emoji '{default_emoji}'")
    return default_emoji

# Генерация угарной фразы с лёгким матом
def generate_funny_phrase(user_id):
    if user_id not in user_phrase_history:
        user_phrase_history[user_id] = []
    user_phrases = user_phrase_history[user_id]
    
    prompt = "Сгенерируй короткую, дерзкую, абсурдную фразу на русском в стиле TikTok с лёгким матом (например, 'ёпт', 'херня', 'пипец'), без жёсткого мата, угарную."
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}"
    
    logger.info(f"Sending request for funny phrase for user {user_id}: {url}")
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            phrase = response.text.strip()
            if phrase and len(phrase) <= 100 and phrase not in user_phrases:
                # Фильтрация через PurgoMalum
                filter_url = f"https://www.purgomalum.com/service/containsprofanity?text={urllib.parse.quote(phrase)}"
                filter_response = requests.get(filter_url, timeout=5)
                if filter_response.text.lower() == "false":
                    logger.info(f"Generated funny phrase for user {user_id}: {phrase}")
                    user_phrases.append(phrase)
                    if len(user_phrases) > 20:
                        user_phrases.pop(0)
                    return phrase
            logger.warning(f"Invalid or repeated funny phrase for user {user_id}: {phrase}")
        except Exception as e:
            logger.error(f"Funny phrase generation error (attempt {attempt + 1}) for user {user_id}: {e}", exc_info=True)
    
    available_phrases = [p for p in FUNNY_PHRASES if p not in user_phrases]
    if not available_phrases:
        user_phrases.clear()
        available_phrases = FUNNY_PHRASES
    phrase = random.choice(available_phrases)
    user_phrases.append(phrase)
    if len(user_phrases) > 20:
        user_phrases.pop(0)
    logger.info(f"Selected local funny phrase for user {user_id}: {phrase}")
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
        logger.error(f"Load memes error: {e}", exc_info=True)
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
        logger.info(f"Downloaded meme sound {sound_url} to {filename}, size: {file_size} bytes")
        return True
    except Exception as e:
        logger.error(f"Failed to download meme sound {sound_url}: {e}")
        return False

# Генерация аудио с мемными эффектами
def generate_meme_audio(text, filename):
    sound_effect = random.choice(MEME_SOUNDS)
    effect_name, effect_url = sound_effect
    effect_prompt = {
        "scream": ", потом орёт как псих, АААА!",
        "burp": ", потом громко рыгает, БУРП!",
        "cry": ", потом плачет как ребёнок, УУУ!",
        "laugh": ", потом ржёт как дебил, ХАХА!"
    }[effect_name]
    
    prompt = (
        f"Озвучь как дерзкий итальянский пацан с TikTok-вайбом, с абсурдной энергией, лёгким матом (ёпт, херня, пипец), и угаром: {text}{effect_prompt}"
    )
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai-audio&voice=echo&attitude=aggressive"
    
    logger.info(f"Sending audio request to API: {url}")
    for attempt in range(3):
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
            logger.error(f"Audio API HTTP error (attempt {attempt + 1}): {e}, response: {e.response.text}")
        except Exception as e:
            logger.error(f"Audio API error (attempt {attempt + 1}): {e}", exc_info=True)
    
    logger.error("Failed to generate audio after 3 attempts")
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
        logger.error(f"Convert error: {e}", exc_info=True)
        return False

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJIS['start']} MEMEZVUKACH врывается, ёпт!\n\n"
        "Бро, мемы на максималках! Вбей название или жми:\n"
        "❓ Найти мем — ищу по вайбу\n"
        "🎲 Рандом — угарный движ\n"
        "🚀 Помощь — как не лажануть\n\n"
        "Го жечь, пацан! 🔥",
        reply_markup=MENU_KEYBOARD
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJIS['help']} MEMEZVUKACH: гайд для тусы\n\n"
        "Кидаю мемы и ору их с лёгким матом, херня!\n\n"
        "Команды:\n"
        f"/start — врываемся в угар {EMOJIS['start']}\n"
        f"/help — этот гайд {EMOJIS['help']}\n"
        f"/random — рандомный мем с озвучкой {EMOJIS['random']}\n\n"
        "❓ Найти мем — вбей название или описание\n"
        "🎲 Рандом — мемный сюрприз\n"
        f"{EMOJIS['audio']} Озвучка — пипец угар!\n\n"
        "Го жечь, пацан! 🔥",
        reply_markup=MENU_KEYBOARD
    )

# Команда /random
async def random_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await update.message.reply_text(
            f"Копаем мемчик, ёпт... {EMOJIS['loading']}"
        )
        await asyncio.sleep(1.5)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(
                f"{EMOJIS['error']} Мемы кончились, херня! Кидай что-нибудь! 😣",
                reply_markup=MENU_KEYBOARD
            )
            return
        
        meme = random.choice(memes)
        user_id = update.effective_user.id
        response = await prepare_meme_response(meme, user_id)
        await msg.delete()
        await send_meme_response(update, context, response, meme)
        
    except Exception as e:
        logger.error(f"Random meme error: {e}", exc_info=True)
        await update.message.reply_text(
            f"{EMOJIS['error']} Чёт сломалось, пипец! Го заново? 😣",
            reply_markup=MENU_KEYBOARD
        )

# Поиск мема
async def search_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJIS['search']} Вбей название мема или описание, ёпт!",
        reply_markup=MENU_KEYBOARD
    )

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "❓Найти мем🔍":
        return await search_meme(update, context)
    elif text == "🎲Рандом🎲":
        return await random_meme(update, context)
    elif text == "🚀Помощь🆘":
        return await help_command(update, context)
    
    try:
        msg = await update.message.reply_text(
            f"Ищу твой мем, ёпт... {EMOJIS['loading']}"
        )
        await asyncio.sleep(1.5)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(
                f"{EMOJIS['error']} Мемы не найдены, херня! Кидай другой! 😣",
                reply_markup=MENU_KEYBOARD
            )
            return
        
        meme = find_closest_meme(text, memes)
        if not meme or difflib.SequenceMatcher(None, text.lower(), meme["name"].lower()).ratio() < 0.6:
            meme = find_meme_by_description(text, memes) or meme
        
        if not meme:
            await msg.edit_text(
                f"{EMOJIS['error']} Не нашёл мем, пипец! Попробуй другой! 😣",
                reply_markup=MENU_KEYBOARD
            )
            return
        
        user_id = update.effective_user.id
        response = await prepare_meme_response(meme, user_id)
        await msg.delete()
        await send_meme_response(update, context, response, meme)
        
    except Exception as e:
        logger.error(f"Handle text error: {e}", exc_info=True)
        await update.message.reply_text(
            f"{EMOJIS['error']} Сломалось, херня! Попробуй ещё раз! 😣",
            reply_markup=MENU_KEYBOARD
        )

# Подготовка ответа
async def prepare_meme_response(meme, user_id):
    emoji = generate_emoji(meme["description"])
    funny_phrase = generate_funny_phrase(user_id)
    voice_text = f"{meme['name']}! {meme['tiktok_phrase']}, {funny_phrase}"
    
    logger.info(f"Preparing response for meme '{meme['name']}' for user {user_id} with emoji '{emoji}' and voice text: {voice_text}")
    
    try:
        return {
            "type": "voice",
            "voice_text": voice_text,
            "caption": (
                f"{emoji} {meme['name']}\n\n"
                f"{meme['description']}\n\n"
                f"{EMOJIS['success']} Го ещё мемас, ёпт? 🔥"
            ),
            "reply_markup": MENU_KEYBOARD
        }
    except Exception as e:
        logger.error(f"Prepare meme response error for user {user_id}: {e}", exc_info=True)
        return {
            "type": "text",
            "text": (
                f"{EMOJIS['error']} Чёт сломалось, пипец!\n\n"
                f"{emoji} {meme['name']}\n{meme['description']}\n\n"
                "Го заново, херня? 😣"
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
                        logger.info(f"Voice message sent successfully with caption: {response['caption']}")
                        return
                
                logger.warning("Audio generation failed, sending text response")
                emoji = generate_emoji(meme["description"])
                await update.message.reply_text(
                    f"{emoji} {meme['name']}\n\n"
                    f"{meme['description']}\n\n"
                    f"{EMOJIS['error']} API аудио сломался, херня! Мем пушка! 😣",
                    reply_markup=response["reply_markup"]
                )
        else:
            await update.message.reply_text(
                response["text"],
                reply_markup=response["reply_markup"]
            )
    except Exception as e:
        logger.error(f"Send meme response error: {e}", exc_info=True)
        emoji = generate_emoji(meme["description"])
        await update.message.reply_text(
            f"{EMOJIS['error']} Сломалось, пипец!\n\n"
            f"{emoji} {meme['name']}\n{meme['description']}\n\n"
            "Го ещё, херня? 😣",
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
        logger.error(f"Failed to initialize bot: {e}", exc_info=True)
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
        logger.error(f"Polling error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
