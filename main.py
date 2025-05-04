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

nest_asyncio.apply()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("MEMEZVUKACH")
MEMES_JSON = "memes.json"
AUDIO_DIR = "meme_audios"
os.makedirs(AUDIO_DIR, exist_ok=True)

MEME_SOUNDS = [
    ("vine_boom", "https://myinstants.com/media/sounds/vine_boom.mp3", "https://soundbuttons.net/sounds/1617/vine_boom.mp3"),
    ("airhorn", "https://myinstants.com/media/sounds/airhorn.mp3", "https://soundbuttons.net/sounds/1415/airhorn.mp3"),
    ("anime_wow", "https://myinstants.com/media/sounds/anime_wow.mp3", "https://soundbuttons.net/sounds/1819/anime_wow.mp3")
]

user_phrase_history = {}
EMOJIS = {"welcome": "🚀", "help": "🔍", "search": "🔥", "random": "🎲", "audio": "🎸", "loading": "⏳", "error": "😕", "success": "🌟", "meme": "🦄", "vibe": "🦁"}
MENU_KEYBOARD = ReplyKeyboardMarkup([["🔥 Найти Шедевр", "🎲 Случайный Вайб"], ["🔍 Гид по Мемам"]], resize_keyboard=True)

async_client = AsyncClient()
PHOTO_PRESET = """Ты бот, который получает название мемного животного из группы итальянских мемов (например, Bombardier Crocodile (Бомбардиро Крокодило)). Найди одно фото этого мема или ссылку на документацию с фото, используя английское и русское название. Верни только одну ссылку. Если ничего не найдено, верни 'Фото не найдено 😕'. Только ссылка или указанный текст."""
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

def generate_funny_phrase(user_id):
    if user_id not in user_phrase_history:
        user_phrase_history[user_id] = []
    user_phrases = user_phrase_history[user_id]
    
    prompt = "Сгенерируй мемную фразу в стиле TikTok, до 50 символов, про итальянских мемных животных."
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}"
    
    logger.info(f"Sending request for phrase for user {user_id}")
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=10)
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
    
    backup_phrases = ["Кроко-босс! 🐊", "Тралала-взрыв! 🎉", "Барабум-вайб! 🦁", "Трули-туса! 🦄"]
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

async def find_meme_emoji(meme_name_english, meme_name_russian):
    try:
        query = f"{meme_name_english} ({meme_name_russian})"
        response = await async_client.chat.completions.create(
            model="gpt-4",
            provider=g4f.Provider.Bing,
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

async def find_meme_photo(meme_name_english, meme_name_russian):
    try:
        query = f"{meme_name_english} ({meme_name_russian}) итальянский мем"
        response = await async_client.chat.completions.create(
            model="gpt-4",
            provider=g4f.Provider.Bing,
            messages=[{"role": "system", "content": PHOTO_PRESET}, {"role": "user", "content": query}],
            web_search=True,
            stream=False
        )
        photo_url = response.choices[0].message.content.strip()
        logger.info(f"Photo URL from g4f for {query}: {photo_url}")
        if photo_url != "Фото не найдено 😕" and photo_url.startswith("http"):
            return photo_url
        logger.warning(f"No photo found for {query}")
        return "Фото не найдено 😕"
    except Exception as e:
        logger.error(f"Photo search error for {query}: {e}")
        return "Фото не найдено 😕"

async def gradual_reply(context, chat_id, message_id, text):
    words = text.split()
    current_text = ""
    for word in words:
        current_text += word + " "
        await context.bot.edit_message_text(text=current_text.strip(), chat_id=chat_id, message_id=message_id)
        await asyncio.sleep(0.05)

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
            response = requests.get(url, stream=True, timeout=15)
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
    
    prompt = (
        f"Озвучь с точным итальянским TikTok-вайбом, как в мемах, с пафосом и энергией: {text}. "
        f"Добавь фразу: '{funny_phrase}'"
    )
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai-audio&voice=onyx&attitude=excited"
    
    logger.info(f"Sending audio request to API for text: {text}")
    for attempt in range(3):
        try:
            response = requests.get(url, stream=True, timeout=15)
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
                        effect_audio = AudioSegment.from_mp3(effect_file.name) + 5
                        combined = main_audio + effect_audio
                        await asyncio.sleep(0.5)
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
    
    logger.error("Failed to generate audio after 3 attempts")
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
    try:
        msg = await update.message.reply_text(f"Выбираю шедевр... ⏳🦄")
        await asyncio.sleep(1)
        
        memes = load_memes()
        if not memes:
            await msg.edit_text(f"Мемы не найдены! 😕 Попробуй позже.", reply_markup=MENU_KEYBOARD)
            return
        
        meme = random.choice(memes)
        user_id = update.effective_user.id
        response = await prepare_meme_response(meme, user_id)
        await msg.delete()
        await send_meme_response(update, context, response, meme)
        
    except Exception as e:
        logger.error(f"Random meme error: {e}")
        await update.message.reply_text(f"Мем ускользнул! 😕🦁 Го ещё раз!", reply_markup=MENU_KEYBOARD)

async def search_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Назови шедевр или опиши его! 🦁🔥", reply_markup=MENU_KEYBOARD)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "🔥 Найти Шедевр":
        return await search_meme(update, context)
    elif text == "🎲 Случайный Вайб":
        return await random_meme(update, context)
    elif text == "🔍 Гид по Мемам":
        return await help_command(update, context)
    
    try:
        msg = await update.message.reply_text(f"Ищу твой мем... ⏳🎸")
        await asyncio.sleep(1)
        
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
        
        user_id = update.effective_user.id
        response = await prepare_meme_response(meme, user_id)
        await msg.delete()
        await send_meme_response(update, context, response, meme)
        
    except Exception as e:
        logger.error(f"Handle text error: {e}")
        await update.message.reply_text(f"Ошибка поиска! 😕🚀 Пробуй снова.", reply_markup=MENU_KEYBOARD)

async def prepare_meme_response(meme, user_id):
    funny_phrase = generate_funny_phrase(user_id)
    voice_text = f"{meme['name_english']}"
    
    logger.info(f"Preparing response for meme '{meme['name']}' for user {user_id}")
    
    audio_task = asyncio.create_task(generate_meme_audio(voice_text, f"{AUDIO_DIR}/temp_{user_id}.mp3", funny_phrase))
    photo_task = asyncio.create_task(find_meme_photo(meme["name_english"], meme["name"]))
    emoji_task = asyncio.create_task(find_meme_emoji(meme["name_english"], meme["name"]))
    
    audio_success, photo_url, emoji = await asyncio.gather(audio_task, photo_task, emoji_task)
    
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
                msg = await update.message.reply_voice(voice=audio_file, caption="⏳", reply_markup=response["reply_markup"])
                await gradual_reply(context, update.effective_chat.id, msg.message_id, response["text"])
            logger.info(f"Voice message sent successfully")
            os.remove(response["voice_file"])
        else:
            msg = await update.message.reply_text("⏳", reply_markup=response["reply_markup"])
            await gradual_reply(context, update.effective_chat.id, msg.message_id, response["text"])
        
        await update.message.reply_text(response["link"], reply_markup=response["reply_markup"])
    except Exception as e:
        logger.error(f"Send meme response error: {e}")
        emoji = random.choice(["🦈", "🦄", "🦁", "🎸", "🌟"])
        msg = await update.message.reply_text("⏳", reply_markup=response["reply_markup"])
        await gradual_reply(context, update.effective_chat.id, msg.message_id,
            f"{emoji} {meme['name_english']}, {meme['name']} 🦄\n\n{meme['description']}\n\n"
            f"Мем без вайба! 😕 🌟🎉"
        )
        await update.message.reply_text("Фото не найдено 😕", reply_markup=response["reply_markup"])

def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN not set in environment variables")
        raise ValueError("TELEGRAM_TOKEN is required")
    
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        logger.info("Webhook deleted successfully")
    except Exception as e:
        logger.error(f"Failed to delete webhook: {e}")
    
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
    
    logger.info("Бот готов зажигать TikTok-вайб!")
    keep_alive()
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        raise

if __name__ == "__main__":
    main()
