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

# Логи и конфиг
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("MEMEZVUKACH")
MEMES_JSON = "memes.json"
AUDIO_DIR = "meme_audios"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Локальный список прикольных фраз (очищено от мата)
FUNNY_PHRASES = [
    "Пипец, башню рвёт, блэ! 🤯",
    "Фигня, но угар, блин! 😝",
    "Чё за жесть, мать его?! 💥",
    "Кринж, но топчик, пипец! 💀",
    "Ору, как дебил, xiy! 🗣️",
    "Блин, это разнос! 🔥",
    "Блэ, мем порвал всё! 🍑",
    "Нафиг мозг, жги тусу! 🦍",
    "Похер, я в агонии! 🏆",
    "Это пипец, а не мем! 😵",
    "Го в тренды, фиг с ним! 🌈",
    "Чё за фигня, но пушка! 💣",
    "Мозг в отпуске, угар! 🦒",
    "Блин, я ору, пипец! 😣",
    "Кринж уровня бог! 💿",
    "Жесть, блэ, держись! ⚡",
    "Похер всё, мем тащит! 🦄",
    "Это не мем, это пипец! 😈",
    "Трындец, башка в шоке! 🪐",
    "Блин, где мой фильтр?! 🦈",
    "Огонь, мать его, жги! 🔥",
    "Пипец, я в астрале! 🌌",
    "Фигня, но ржака, блэ! 😝",
    "Мем порвал, как туз! 🃏",
    "Чё за дичь, но топ! 🦖",
    "Блин, я в ауте, xiy! 💀",
    "Кринж, но я ору! 🗣️",
    "Похер, это разрыв! 💥",
    "Блэ, мем жёсткий! 🍺",
    "Нафиг, я в шоке! 😵",
    "Это пипец, держи! 🦒",
    "Тусим, блин, пипец! 🪩",
    "Мозг офф, угар он! 🌟",
    "Фиг с ним, это топ! 🚀",
    "Жесть, я в кринже! 😣",
    "Пипец, мем унёс! 🦄",
    "Блин, это нереал! 😈",
    "Ору, как псих, блэ! 🗣️",
    "Кринж, но пипец! 💀",
    "Нафиг всё, жги! 🔥",
    "Это фигня, но пушка! 💣",
    "Похер, я в трансе! 🪐",
    "Блэ, мем разъебал! 🍑",
    "Трындец, я в агонии! 🦍",
    "Блин, это разнос! 🏆",
    "Чё за дичь, пипец! 😵",
    "Мем порвал, как бог! 🌈",
    "Фигня, но угар! 😝",
    "Пипец, я в шоке! 💥",
    "Топ, мать его, топ! 🦄"
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

# Генерация прикольной фразы
def generate_funny_phrase(user_id):
    if user_id not in user_phrase_history:
        user_phrase_history[user_id] = []
    user_phrases = user_phrase_history[user_id]
    
    prompt = "Сгенерируй дерзкую, абсурдную фразу на русском без мата в стиле TikTok, короткую и угарную."
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}"
    
    logger.info(f"Sending request for funny phrase for user {user_id}: {url}")
    for _ in range(3):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            phrase = response.text.strip()
            if phrase and len(phrase) <= 100 and phrase not in user_phrases:
                logger.info(f"Generated funny phrase for user {user_id}: {phrase}")
                user_phrases.append(phrase)
                if len(user_phrases) > 20:
                    user_phrases.pop(0)
                return phrase
            logger.warning(f"Invalid or repeated funny phrase for user {user_id}: {phrase}")
        except Exception as e:
            logger.error(f"Funny phrase generation error for user {user_id}: {e}", exc_info=True)
    
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

# Генерация аудио
def generate_meme_audio(text, filename):
    prompt = (
        "Озвучь это как дерзкий итальянский пацан с TikTok-вайбом, с абсурдной энергией и угаром: {text}"
    ).format(text=text)
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai-audio&voice=echo&attitude=aggressive"
    
    logger.info(f"Sending request to API: {url}")
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
        logger.info(f"Audio generated: {filename}, size: {file_size} bytes")
        return True
    except requests.HTTPError as e:
        logger.error(f"Audio API HTTP error: {e}, response: {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Audio API error: {e}", exc_info=True)
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
        f"{EMOJIS['start']} MEMEZVUKACH врывается!\n\n"
        "Бро, мемы на максималках! Вбей название или жми:\n"
        "❓ Найти мем — ищу по вайбу\n"
        "🎲 Рандом — угарный движ\n"
        "🚀 Помощь — как не лажануть",
        reply_markup=MENU_KEYBOARD
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJIS['help']} MEMEZVUKACH: гайд для тусы\n\n"
        "Кидаю мемы и ору их на максималках!\n\n"
        "Команды:\n"
        f"/start — врываемся в угар {EMOJIS['start']}\n"
        f"/help — этот гайд {EMOJIS['help']}\n"
        f"/random — рандомный мем с озвучкой {EMOJIS['random']}\n\n"
        "❓ Найти мем — вбей название или описание\n"
        "🎲 Рандом — мемный сюрприз\n"
        f"{EMOJIS['audio']} Озвучка — жесть и пипец!\n\n"
        "Го жечь, пацан! 🔥",
        reply_markup=MENU_KEYBOARD
    )

# Команда /random
async def random_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await update.message.reply_text(
            f"Копаем мемчик... {EMOJIS['loading']}"
        )
        await asyncio.sleep(1.5)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(
                f"{EMOJIS['error']} Мемы кончились! Кидай что-нибудь! 😣",
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
            f"{EMOJIS['error']} Чёт сломалось! Го заново? 😣",
            reply_markup=MENU_KEYBOARD
        )

# Поиск мема
async def search_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{EMOJIS['search']} Вбей название мема или описание!",
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
            f"Ищу твой мем... {EMOJIS['loading']}"
        )
        await asyncio.sleep(1.5)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(
                f"{EMOJIS['error']} Мемы не найдены! Кидай другой! 😣",
                reply_markup=MENU_KEYBOARD
            )
            return
        
        meme = find_closest_meme(text, memes)
        if not meme or difflib.SequenceMatcher(None, text.lower(), meme["name"].lower()).ratio() < 0.6:
            meme = find_meme_by_description(text, memes) or meme
        
        if not meme:
            await msg.edit_text(
                f"{EMOJIS['error']} Не нашёл мем! Попробуй другой! 😣",
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
            f"{EMOJIS['error']} Сломалось! Попробуй ещё раз! 😣",
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
                f"{EMOJIS['success']} Го ещё мемас? 🔥"
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
                "Го заново? 😣"
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
                    f"{EMOJIS['error']} API блочит, xiy! Мем пушка! 😣",
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
            f"{EMOJIS['error']} Сломалось, блэ!\n\n"
            f"{emoji} {meme['name']}\n{meme['description']}\n\n"
            "Го ещё? 😣",
            reply_markup=MENU_KEYBOARD
        )

# Основной цикл
def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN", "8154670480:AAGSLclPE5TQwUoKra79XbSNq97ivezUKHM")
    
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
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Polling error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()