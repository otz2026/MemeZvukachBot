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
import nest_asyncio
from contextlib import contextmanager
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pydub import AudioSegment
from background import keep_alive
import g4f
from g4f.client import AsyncClient
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
from functools import lru_cache
from collections import defaultdict
from datetime import datetime, timedelta

nest_asyncio.apply()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("MEMEZVUKACH")
MEMES_JSON = "memes.json"
AUDIO_DIR = "meme_audios"
os.makedirs(AUDIO_DIR, exist_ok=True)

MEME_SOUNDS = [
    ("vine_boom", "https://myinstants.com/media/sounds/vine-boom.mp3", "https://soundboardguy.com/sounds/vine-boom.mp3"),
    ("airhorn", "https://myinstants.com/media/sounds/airhorn.mp3", "https://soundboardguy.com/sounds/airhorn.mp3"),
    ("anime_wow", "https://myinstants.com/media/sounds/anime-wow.mp3", "https://soundboardguy.com/sounds/anime-wow.mp3"),
    ("dramatic", "https://myinstants.com/media/sounds/dramatic.mp3", "https://soundboardguy.com/sounds/dramatic.mp3"),
    ("tada", "https://myinstants.com/media/sounds/tada.mp3", "https://soundboardguy.com/sounds/tada.mp3"),
    ("explosion", "https://myinstants.com/media/sounds/explosion.mp3", "https://soundboardguy.com/sounds/explosion.mp3"),
    ("scream", "https://myinstants.com/media/sounds/scream.mp3", "https://soundboardguy.com/sounds/scream.mp3")
]

user_phrase_history = {}
user_requests = defaultdict(list)
user_bans = {}
EMOJIS = {"welcome": "🚀", "help": "🔍", "search": "🔥", "random": "🎲", "audio": "🎸", "loading": "⏳", "error": "😕", "success": "🌟", "meme": "🦄", "vibe": "🦁"}
MENU_KEYBOARD = ReplyKeyboardMarkup([["🔥 Найти Шедевр", "🎲 Случайный Вайб"], ["🔍 Гид по Мемам"]], resize_keyboard=True)

async_client = AsyncClient()
semaphore = asyncio.Semaphore(5)
PHOTO_PRESET = """Ты бот, который получает название мемного животного из группы итальянских мемов (например, Bombardier Crocodile (Бомбардиро Крокодило)). Найди одно фото этого мема или ссылку на документацию с фото в высоком разрешении (не менее 1600x1200 пикселей), используя английское и русское название. Верни только одну ссылку. Если ничего не найдено, верни 'Фото не найдено 😕'. Только ссылка или указанный текст."""
EMOJI_PRESET = """Верни один яркий мемный эмодзи для мема {name_english} ({name}). Только эмодзи, без текста."""

# Кэш мемов
_memes_cache = None

@contextmanager
def temp_audio_file():
    mp3_fd, mp3_path = tempfile.mkstemp(suffix=".mp3", dir=AUDIO_DIR)
    try:
        yield mp3_path
    finally:
        time.sleep(1)
        try:
            os.close(mp3_fd)
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
                logger.info(f"Deleted temp file: {mp3_path}")
        except Exception as e:
            logger.warning(f"Failed to delete temp file {mp3_path}: {e}")

async def check_user_spam(user_id):
    now = datetime.now()
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < timedelta(seconds=10)]
    user_requests[user_id].append(now)
    
    if user_id in user_bans and user_bans[user_id] > now:
        ban_duration = (user_bans[user_id] - now).total_seconds()
        return False, f"Чилл, мемный босс! 😎 Слишком много вайба, отдохни {int(ban_duration)} сек."
    
    if len(user_requests[user_id]) > 5:
        ban_duration = 60 if user_id not in user_bans else 300
        user_bans[user_id] = now + timedelta(seconds=ban_duration)
        return False, f"Чилл, мемный босс! 😎 Слишком много вайба, отдохни {ban_duration} сек."
    
    return True, None

async def generate_funny_phrase(meme):
    tiktok_phrase = meme.get("tiktok_phrase", "")
    if tiktok_phrase:
        return tiktok_phrase
    
    backup_phrases = [
        "Кроко-трап! 🐊💥", "Банана-туса! 🍌🎉", "Кофе-босс! ☕🔥", "Гусино-турбо! 🦢🚀",
        "Тралала-бэнг! 🎤💥", "Пчела-бомба! 🐝💣", "Капибара-вайб! 🦫🌈", "Тигро-арбуз! 🐅🍉"
    ]
    return random.choice(backup_phrases)

async def find_meme_emoji(meme_name_english, meme_name_russian):
    async with semaphore:
        try:
            query = f"{meme_name_english} ({meme_name_russian})"
            response = await async_client.chat.completions.create(
                model="meta-llama-3.1-405b-instruct",
                provider=g4f.Provider.DeepInfra,
                messages=[{"role": "system", "content": EMOJI_PRESET}, {"role": "user", "content": query}],
                web_search=False,
                stream=False
            )
            emoji = response.choices[0].message.content.strip()
            valid_emojis = ["🦈", "🐊", "🦁", "🦄", "🐧", "🦖", "🎉", "🎸", "🌟", "🍕", "🦊", "🚀"]
            if emoji in valid_emojis:
                logger.info(f"Emoji for {query}: {emoji}")
                return emoji
            logger.warning(f"Invalid emoji for {query}: {emoji}")
        except Exception as e:
            logger.error(f"Emoji search error for {query}: {e}")
        return random.choice(["🦈", "🦄", "🦁", "🎸", "🌟"])

@lru_cache(maxsize=100)
def cached_google_search(query):
    try:
        google_url = f"https://www.google.com/search?tbm=isch&q={urllib.parse.quote(query)}&tbs=isz:lt,islt:uxga"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(google_url, headers=headers, timeout=20)
        if response.status_code == 200:
            return response.text
        logger.warning(f"Google search failed for {query}: {response.status_code}")
    except Exception as e:
        logger.error(f"Google search error for {query}: {e}")
    return None

async def find_meme_photo(meme_name_english, meme_name_russian):
    async with semaphore:
        try:
            query = f"{meme_name_english} ({meme_name_russian}) итальянский мем"
            response = await async_client.chat.completions.create(
                model="meta-llama-3.1-405b-instruct",
                provider=g4f.Provider.DeepInfra,
                messages=[{"role": "system", "content": PHOTO_PRESET}, {"role": "user", "content": query}],
                web_search=True,
                stream=False
            )
            photo_url = response.choices[0].message.content.strip()
            logger.info(f"Photo URL from g4f for {query}: {photo_url}")
            if photo_url != "Фото не найдено 😕" and photo_url.startswith("http"):
                if await check_image_quality(photo_url):
                    return photo_url
        except Exception as e:
            logger.error(f"Photo search error for {query}: {e}")
        
        try:
            google_html = cached_google_search(query)
            if google_html:
                soup = BeautifulSoup(google_html, "html.parser")
                img_tags = soup.find_all("img")
                for img in img_tags[1:]:
                    src = img.get("src")
                    if src and src.startswith("http"):
                        if await check_image_quality(src):
                            logger.info(f"Google Images URL for {query}: {src}")
                            return src
        except Exception as e:
            logger.error(f"Google Images search error for {query}: {e}")
        
        logger.warning(f"No photo found for {query}")
        return "Фото не найдено 😕"

async def check_image_quality(url):
    try:
        response = requests.get(url, timeout=10, stream=True)
        response.raise_for_status()
        content_length = int(response.headers.get("Content-Length", 0))
        if content_length < 100000:
            logger.warning(f"Image {url} too small: {content_length} bytes")
            return False
        
        img = Image.open(BytesIO(response.content))
        width, height = img.size
        if width >= 1600 and height >= 1200:
            logger.info(f"Image {url} meets quality requirements: {width}x{height}, {content_length} bytes")
            return True
        logger.warning(f"Image {url} resolution too low: {width}x{height}")
        return False
    except Exception as e:
        logger.error(f"Error checking image quality for {url}: {e}")
        return False

def load_memes():
    global _memes_cache
    if _memes_cache is not None:
        return _memes_cache
    try:
        if not os.path.exists(MEMES_JSON):
            logger.error(f"Memes file {MEMES_JSON} not found")
            return []
        with open(MEMES_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            _memes_cache = data.get("memes", [])
            return _memes_cache
    except Exception as e:
        logger.error(f"Load memes error: {e}")
        return []

def find_closest_meme(query, memes):
    query = query.lower().strip()
    logger.info(f"Searching for meme by name: {query}")
    names = [m["name"].lower() for m in memes]
    closest = difflib.get_close_matches(query, names, n=1, cutoff=0.3)
    return next((m for m in memes if m["name"].lower() == closest[0]), None) if closest else None

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

def download_meme_sound(sound_url, fallback_url, filename):
    for url in [sound_url, fallback_url]:
        try:
            response = requests.get(url, stream=True, timeout=20)
            response.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            file_size = os.path.getsize(filename)
            logger.info(f"Downloaded meme sound from {url} to {filename}, size: {file_size} bytes")
            return True
        except Exception as e:
            logger.error(f"Failed to download meme sound from {url}: {e}")
    return False

async def generate_meme_audio(text, filename, funny_phrase):
    sound_effect = random.choice(MEME_SOUNDS)
    effect_name, effect_url, effect_fallback_url = sound_effect
    
    prompt = f"{funny_phrase} {text}"
    if len(prompt) > 150:
        prompt = prompt[:150]
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai-audio&voice=onyx&attitude=excited"
    
    logger.info(f"Sending audio request to API")
    async with semaphore:
        for attempt in range(2):
            try:
                response = requests.get(url, stream=True, timeout=20)
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
                    if download_meme_sound(effect_url, effect_fallback_url, effect_file.name):
                        try:
                            main_audio = AudioSegment.from_mp3(filename)
                            effect_audio = AudioSegment.from_mp3(effect_file.name) + 10
                            combined = main_audio + effect_audio
                            await asyncio.sleep(1.5)
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
    
    logger.error("Failed to generate audio after 2 attempts")
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Врываемся в мемный вайб! 🚀🦄\n\nНазови мем или выбери рандом.\nГо за шедеврами! 🎸🌟",
        reply_markup=MENU_KEYBOARD
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Гид по Мемам 🔍🌟\n\nЯ бот, зажигающий TikTok-вайб с итальянскими мемами! 🦁🎸\n\n"
        f"Что могу:\n- Найти мем по названию или описанию\n- Выдать рандомный шедевр\n- Озвучить с пафосным TikTok-вайбом\n"
        f"- Показать фотки мемных героев\n\nКоманды:\n/start — врываемся\n/help — этот вайб\n/random — рандомный мем\n\n"
        f"Погнали за движем! 🎉🦈",
        reply_markup=MENU_KEYBOARD
    )

async def random_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    can_proceed, ban_message = await check_user_spam(user_id)
    if not can_proceed:
        await update.message.reply_text(ban_message, reply_markup=MENU_KEYBOARD)
        return
    
    msg = await update.message.reply_text("🔎 Ищу мемный вайб... ⏳🦄")
    try:
        memes = load_memes()
        if not memes:
            await msg.edit_text(f"Мемы не найдены! 😕 Попробуй позже.", reply_markup=MENU_KEYBOARD)
            return
        
        meme = random.choice(memes)
        response = await prepare_meme_response(meme, user_id, update)
        await msg.delete()
        await send_meme_response(update, context, response, meme)
        
    except Exception as e:
        logger.error(f"Random meme error: {e}")
        await msg.delete()
        await update.message.reply_text(f"Мем ускользнул! 😕🦁 Го ещё раз!", reply_markup=MENU_KEYBOARD)

async def search_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Назови шедевр или опиши его! 🦁🔥", reply_markup=MENU_KEYBOARD)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    can_proceed, ban_message = await check_user_spam(user_id)
    if not can_proceed:
        await update.message.reply_text(ban_message, reply_markup=MENU_KEYBOARD)
        return
    
    if text == "🔥 Найти Шедевр":
        return await search_meme(update, context)
    elif text == "🎲 Случайный Вайб":
        return await random_meme(update, context)
    elif text == "🔍 Гид по Мемам":
        return await help_command(update, context)
    
    msg = await update.message.reply_text("🔎 Ищу мемный вайб... ⏳🎸")
    try:
        memes = load_memes()
        if not memes:
            await msg.edit_text(f"Мемы не найдены! 😕🔍 Попробуй другое.", reply_markup=MENU_KEYBOARD)
            return
        
        meme = find_closest_meme(text, memes)
        if not meme or difflib.SequenceMatcher(None, text.lower(), meme["name"].lower()).ratio() < 0.6:
            meme = find_meme_by_description(text, memes) or meme
        
        if not meme:
            await msg.edit_text(f"Мем не найден! 😕🦄 Попробуй другое.", reply_markup=MENU_KEYBOARD)
            return
        
        response = await prepare_meme_response(meme, user_id, update)
        await msg.delete()
        await send_meme_response(update, context, response, meme)
        
    except Exception as e:
        logger.error(f"Handle text error: {e}")
        await msg.delete()
        await update.message.reply_text(f"Ошибка поиска! 😕🚀 Пробуй снова.", reply_markup=MENU_KEYBOARD)

async def prepare_meme_response(meme, user_id, update):
    funny_phrase = await generate_funny_phrase(meme)
    voice_text = f"{meme['name_english']}"
    
    logger.info(f"Preparing response for meme '{meme['name']}' for user {user_id}")
    
    audio_msg = await update.message.reply_text("🎙️ Записываю TikTok-бэнгер... ⏳🔊")
    audio_task = asyncio.create_task(generate_meme_audio(voice_text, f"{AUDIO_DIR}/temp_{user_id}.mp3", funny_phrase))
    photo_msg = await update.message.reply_text("🖼️ Подбираю шедевральную фотку... ⏳📸")
    photo_task = asyncio.create_task(find_meme_photo(meme["name_english"], meme["name"]))
    emoji_task = asyncio.create_task(find_meme_emoji(meme["name_english"], meme["name"]))
    
    audio_success, photo_url, emoji = await asyncio.gather(audio_task, photo_task, emoji_task)
    
    await audio_msg.delete()
    await photo_msg.delete()
    
    try:
        return {
            "type": "voice" if audio_success else "text",
            "voice_text": voice_text,
            "voice_file": f"{AUDIO_DIR}/temp_{user_id}.mp3" if audio_success else None,
            "text": (
                f"{emoji} Озвучка... 🎸\n"
                f"{meme['name_english']}, {meme['name']}\n\n"
                f"{meme['description']}\n\n"
                f"{funny_phrase} 🌟🎉"
            ),
            "link": photo_url,
            "reply_markup": MENU_KEYBOARD
        }
    except Exception as e:
        logger.error(f"Prepare meme response error for user {user_id}: {e}")
        return {
            "type": "text",
            "text": (
                f"{emoji} {meme['name_english']}, {meme['name']} 🦄\n\n"
                f"{meme['description']}\n\n"
                f"{funny_phrase} 🌟🎉"
            ),
            "link": "Фото не найдено 😕",
            "reply_markup": MENU_KEYBOARD
        }

async def send_meme_response(update: Update, context: ContextTypes.DEFAULT_TYPE, response, meme):
    try:
        if response["type"] == "voice":
            with open(response["voice_file"], "rb") as audio_file:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
                await update.message.reply_voice(voice=audio_file, caption=response["text"], reply_markup=response["reply_markup"])
            logger.info(f"Voice message sent successfully")
            os.remove(response["voice_file"])
        else:
            await update.message.reply_text(response["text"], reply_markup=response["reply_markup"])
        
        await update.message.reply_text(response["link"], reply_markup=response["reply_markup"])
    except Exception as e:
        logger.error(f"Send meme response error: {e}")
        emoji = random.choice(["🦈", "🦄", "🦁", "🎸", "🌟"])
        await update.message.reply_text(
            f"{emoji} {meme['name_english']}, {meme['name']} 🦄\n\n{meme['description']}\n\n"
            f"Мем без вайба! 😕 🌟🎉",
            reply_markup=response["reply_markup"]
        )
        await update.message.reply_text("Фото не найдено 😕", reply_markup=response["reply_markup"])

async def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN not set in environment variables")
        raise ValueError("TELEGRAM_TOKEN is required")
    
    try:
        # Проверка состояния бота
        response = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=10)
        if response.status_code == 200:
            logger.info("Bot is accessible: %s", response.json())
        else:
            logger.error("Failed to access bot: %s", response.text)
            raise ValueError("Bot initialization failed")
        
        # Очистка вебхуков
        for _ in range(3):  # Повтор для надежности
            requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
            requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url=", timeout=10)
            await asyncio.sleep(1)
        logger.info("Webhook deleted and reset successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Telegram API: {e}")
        raise
    
    logger.info("MEMEZVUKACH стартует...")
    
    try:
        app = Application.builder().token(TOKEN).concurrent_updates(False).build()
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        raise
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("random", random_meme))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("Бот готов зажигать TikTok-вайб!")
    keep_alive()
    await asyncio.sleep(10)  # Увеличенная задержка для очистки
    try:
        await app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
