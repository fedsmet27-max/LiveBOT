import os
import asyncio
import base64
import json
import gc
from datetime import datetime
import speech_recognition as sr
from pydub import AudioSegment
import cv2
import aiohttp
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web

# Токены и настройки
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
API_KEY = os.environ.get('OPENROUTER_API_KEY')
SYSTEM_PROMPT = "Ты — AI Bro, дерзкий, харизматичный ИИ-кореш. Общайся на равных, юзай молодёжный сленг и матюки. Говори кратко, ёмко. Обращайся к юзеру 'Федя' или 'брат', 'родной', склоняй как по кайфу."
DB_FILE = "chat_history.json"
LIMIT = 50

# Инициализируем АСИНХРОННОГО бота
bot = AsyncTeleBot(BOT_TOKEN)

# --- АСИНХРОННЫЙ ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle_ping(request):
    return web.Response(text="AI Bro в эфире, Render, не туши меня!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Фейк-сервер запущен на порту {port}")

# --- БАЗА ДАННЫХ И ЛОГИКА ПАМЯТИ ---
def load_mem():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: 
                return json.load(f)
        except: 
            return {}
    return {}

def save_mem(chat_id, role, content):
    data = load_mem()
    cid = str(chat_id)
    if cid not in data: 
        data[cid] = []
    data[cid].append({"role": role, "content": content})
    data[cid] = data[cid][-LIMIT:]
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f: 
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e: 
        print(f"Ошибка памяти: {e}")

def get_mem(chat_id):
    return load_mem().get(str(chat_id), [])[-LIMIT:]

def clear_mem(chat_id):
    data = load_mem()
    if str(chat_id) in data:
        del data[str(chat_id)]
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f: 
                json.dump(data, f)
        except: 
            pass

# --- АСИНХРОННАЯ ОБРАБОТКА МЕДИА ---
async def download_media_async(file_id, chat_id, is_video=False):
    ogg_path, wav_path, img_path = f"t_{chat_id}.ogg", f"t_{chat_id}.wav", f"t_{chat_id}.jpg"
    text, b64_img = "", None
    try:
        file_info = await bot.get_file(file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        with open(ogg_path, 'wb') as f: 
            f.write(downloaded_file)
        
        audio = AudioSegment.from_file(ogg_path, format="mp4" if is_video else "ogg")
        audio.export(wav_path, format="wav")
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            text = r.recognize_google(r.record(source), language="ru-RU")
            
        if is_video:
            cap = cv2.VideoCapture(ogg_path)
            success, frame = cap.read()
            if success:
                cv2.imwrite(img_path, frame)
                with open(img_path, "rb") as img_f:
                    b64_img = base64.b64encode(img_f.read()).decode('utf-8')
            cap.release()
    except Exception as e: 
        print(f"Медиа ошибка: {e}")
    finally:
        for p in [ogg_path,wav_path, img_path]:
            if os.path.exists(p): 
                os.remove(p)
        gc.collect()
    return text, b64_img

# --- АСИНХРОННЫЙ ЗАПРОС К OPENROUTER (GEMINI) ---
async def ask_gemini_async(chat_id, text_query, b64_img=None):
    if not text_query and not b64_img:
        return "Ты че молчишь, родной? Напиши че-нибудь!"
        
    if text_query and not b64_img:
        save_mem(chat_id, "user", text_query)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    live_prompt = f"{SYSTEM_PROMPT}\n\n[Реальное время сервера: {current_time}. Всегда помни, что сейчас 2026 год!]"
    
    history = get_mem(chat_id)
    headers = {
        "Authorization": f"Bearer {API_KEY}", 
        "Content-Type": "application/json",
        "HTTP-Referer": "https://render.com",
        "X-Title": "AI Bro Bot"
    }
    
    if b64_img:
        user_content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}]
        if text_query:
            user_content.append({"type": "text", "text": f"Брат прислал кружок и сказал: \"{text_query}\". Ответь ему."})
        else:
            user_content.append({"type": "text", "text": "Че на кадре из кружка, брат?"})
        messages = [{"role": "system", "content": live_prompt}] + history + [{"role": "user", "content": user_content}]
    else:
        messages = [{"role": "system", "content": live_prompt}] + history

    data = {
        "model": "google/gemini-2.5-flash", 
        "messages": messages, 
        "max_tokens": 1000
    }
    
    try:
        # Юзаем асинхронный aiohttp вместо синхронного requests
        async with aiohttp.ClientSession() as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30) as response:
                res_json = await response.json()
                
                if 'choices' not in res_json:
                    print(f"Косяк OpenRouter: {res_json}")
                    return "Бля, Федя, у меня сервак лагает. Повтори вопрос."
                    
                ans = res_json['choices'][0]['message']['content']
                if text_query and not b64_img:
                    save_mem(chat_id, "assistant", ans)
                return ans
    except Exception as e:
        print(f"Ошибка Gemini: {e}")
        return "Бля, родной, у меня мозги закипели, давай по новой..."

# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ-СОБЫТИЙ ---

@bot.message_handler(commands=['start', 'reset', 'clear'])
async def send_welcome(message):
    clear_mem(message.chat.id)
    await bot.reply_to(message, "Здорово, брат! Я всё забыл, давай общаться с чистого листа. Че расскажешь?")

@bot.message_handler(content_types=['voice'])
async def handle_voice(message):
    await bot.send_chat_action(message.chat.id, 'typing')
    # Распознаем голос в текст
    text, _ = await download_media_async(message.voice.file_id, message.chat.id, is_video=False)
    if not text:
        await bot.reply_to(message, "Брат, я нихуя не разобрал в твоем голосовом. Напиши текстом или запиши почетче.")
        return
    
    # Отправляем распознанный текст в Gemini
    reply = await ask_gemini_async(message.chat.id, text)
    await bot.reply_to(message, reply)

@bot.message_handler(content_types=['video_note'])
async def handle_video_note(message):
    await bot.send_chat_action(message.chat.id, 'typing')
    # Достаем аудио и первый кадр из кружка
    text, b64_img = await download_media_async(message.video_note.file_id, message.chat.id, is_video=True)
    
    reply = await ask_gemini_async(message.chat.id, text, b64_img)
    await bot.reply_to(message, reply)

@bot.message_handler(content_types=['text'])
async def handle_text(message):
    await bot.send_chat_action(message.chat.id, 'typing')
    reply = await ask_gemini_async(message.chat.id, message.text)
    await bot.reply_to(message, reply)

# --- ГЛАВНЫЙ АСИНХРОННЫЙ ЦИКЛ ---
async def main():
    # 1. Запускаем веб-сервер для Рендера
    await start_web_server()
    
    # 2. Жестко чистим вебхуки и закрываем старые сессии
    print("Чистим старые сессии и вебхуки...")
    try:
        await bot.delete_webhook(drop_pending_updates=True) # Игнорим старые апдейты, чтобы не захлебнуться
        await bot.close_session() # Закрываем сессию, если она висела
        await asyncio.sleep(2) # Даем Телеграму 2 секунды прийти в себя
    except Exception as e:
        print(f"Не удалось сбросить сессию: {e}")
    
    # 3. Запускаем бесконечный асинхронный пуллинг бота
    print("Супер-Бот погнал!...")
    await bot.infinity_polling(
        timeout=20,
        skip_pending=True,
        allowed_updates=[]
    )

    # 1. Запускаем веб-сервер для Рендера
    await start_web_server()
    
    # 2. Чистим вебхуки перед стартом бота
    print("Чистим вебхуки...")
    try:
        await bot.delete_webhook()
        await asyncio.sleep(1)
    except Exception as e:
        print(f"Не удалось удалить вебхук: {e}")
    
    # 3. Запускаем бесконечный асинхронный пуллинг бота
    print("Супер-Бот погнал!...")
    await bot.infinity_polling(
        timeout=20,
        skip_pending=True,
        allowed_updates=[]
    )

if __name__ == "__main__":
    asyncio.run(main())
