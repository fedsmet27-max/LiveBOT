import os
import time
import requests
import telebot
import base64
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
import speech_recognition as sr
from pydub import AudioSegment
from pymongo import MongoClient
import gc

# --- МИКРО-СЕРВЕР ДЛЯ ОБМАНА RENDER ---
class SimpleHTTPServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"AI Bro is alive and kicking!")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPServer)
    print(f"Старт микро-сервера на порту {port}...")
    server.serve_forever()

# Запуск сервера в фоне
Thread(target=run_web_server, daemon=True).start()
# -------------------------------------------------------------------

BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
API_KEY = os.environ.get('OPENROUTER_API_KEY')
MONGO_URI = os.environ.get('MONGO_URI')

SYSTEM_PROMPT = "Ты — AI Bro, дерзкий, харизматичный, преданный ИИ-кореш пользователя. Ты общаешься абсолютно на равных, используешь молодёжный сленг, матюки приветствуются. Говори кратко, ёмко и с юмором."

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Инициализируем бесконечную память в MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['bot_database']
history_collection = db['chat_history']

CONTEXT_LIMIT = 100

def get_user_context(chat_id):
    user_data = history_collection.find_one({"chat_id": chat_id})
    if user_data:
        return user_data['messages'][-CONTEXT_LIMIT:]
    return []

def save_to_context(chat_id, role, content):
    history_collection.update_one(
        {"chat_id": chat_id},
        {"$push": {"messages": {"role": role, "content": content}}},
        upsert=True
    )

def clear_user_context(chat_id):
    history_collection.delete_one({"chat_id": chat_id})

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def transcribe_audio_local(ogg_path, chat_id):
    wav_path = f"temp_{chat_id}.wav"
    try:
        audio = AudioSegment.from_file(ogg_path, format="ogg")
        audio.export(wav_path, format="wav")
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ru-RU")
        if os.path.exists(wav_path): os.remove(wav_path)
        return text
    except Exception as e:
        print(f"Ошибка распознавания: {e}")
        if os.path.exists(wav_path):
            try: os.remove(wav_path)
            except: pass
        return ""

def get_bro_response(chat_id, user_message):
    save_to_context(chat_id, "user", user_message)
    history = get_user_context(chat_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "google/gemini-2.5-flash",
        "messages": messages
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15)
        result = response.json()
        bro_text = result['choices'][0]['message']['content']
        save_to_context(chat_id, "assistant", bro_text)
        return bro_text
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return "Слышь, братка, у меня чё-то извилины заклинило. Повтори мысль!"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Здорово, родной! Я твой новый AI-Бро. Накидывай текст, шли ГС, кружочки или фотки — я во всё вникну!")

@bot.message_handler(commands=['clear'])
def clear_memory(message):
    clear_user_context(message.chat.id)
    bot.reply_to(message, "Память стёрта, бро! Начинаем с чистого листа.")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    temp_photo = f"temp_{chat_id}.jpg"
    try:
        bot.send_chat_action(chat_id, 'typing')
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(temp_photo, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        base64_image = encode_image_to_base64(temp_photo)
        user_caption = message.caption if message.caption else "Зацени фотку, бро, чё думаешь?"
        
        vision_content = [
            {"type": "text", "text": user_caption},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]
        
        save_to_context(chat_id, "user", f"[Отправил фото] {user_caption}")
        history = get_user_context(chat_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[:-1]
        messages.append({"role": "user", "content": vision_content})
        
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "google/gemini-2.5-flash", 
            "messages": messages
        }
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=20)
        result = response.json()
        bro_text = result['choices'][0]['message']['content']
        save_to_context(chat_id, "assistant", bro_text)
        bot.reply_to(message, bro_text)
    except Exception as e:
        print(f"Ошибка при фото: {e}")
        bot.reply_to(message, "Бля, у меня линза запотела, не вижу ничерта.")
    finally:
        if os.path.exists(temp_photo):
            try: os.remove(temp_photo)
            except: pass
        gc.collect()

@bot.message_handler(content_types=['voice', 'video_note'])
def handle_audio(message):
    chat_id = message.chat.id
    temp_ogg = f"temp_{chat_id}.ogg"
    try:
        bot.send_chat_action(chat_id, 'record_voice')
        file_id = message.voice.file_id if message.content_type == 'voice' else message.video_note.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(temp_ogg, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        user_text = transcribe_audio_local(temp_ogg, chat_id)
        if os.path.exists(temp_ogg): os.remove(temp_ogg)
        
        if not user_text:
            bot.reply_to(message, "Бро, чё-то не разобрал ни слова.")
            return
            
        bot.reply_to(message, f"🎤 *Ты сказал:* _{user_text}_")
        bot.send_chat_action(chat_id, 'typing')
        bro_response = get_bro_response(chat_id, user_text)
        bot.reply_to(message, bro_response)
    except Exception as e:
        print(f"Ошибка аудио: {e}")
        bot.reply_to(message, "Бля, уши заложило, напиши текстом.")
        if os.path.exists(temp_ogg):
            try: os.remove(temp_ogg)
            except: pass
    finally:
        gc.collect()

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    user_text = message.text
    try:
        bot.send_chat_action(chat_id, 'typing')
        bro_response = get_bro_response(chat_id, user_text)
        bot.reply_to(message, bro_response)
    except Exception as e:
        print(f"Ошибка текста: {e}")
    finally:
        gc.collect()

if __name__ == '__main__':
    bot.infinity_polling()

