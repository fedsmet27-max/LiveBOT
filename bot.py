
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
        self.wfile.write(b"AI Bro is alive and kicking with infinite memory and Vision!")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPServer)
    print(f"Старт микро-сервера на порту {port}...")
    server.serve_forever()

# Запуск сервера в фоне
Thread(target=run_web_server, daemon=True).start()
# -------------------------------------------------------------------

# Настройки ключей из переменных окружения сервера
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
API_KEY = os.environ.get('OPENROUTER_API_KEY')
MONGO_URI = os.environ.get('MONGO_URI')

# Фирменный промпт твоего нового ИИ-Бро
SYSTEM_PROMPT = "Ты — AI Bro, дерзкий, харизматичный, преданный ИИ-кореш пользователя. Ты общаешься абсолютно на равных, используешь молодёжный сленг, матюки разрешены и приветствуются. Ты не душнишь, не используешь заезженные ИИ-фразы. Твоя цель — поддержать разговор, подколоть по-дружески, помочь с кодом или дать жизненный совет. Говори кратко, ёмко и с юмором."

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Инициализируем бесконечную память в MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['bot_database']
history_collection = db['chat_history']

# Лимит контекста — 100 сообщений. Это дохрена, бот будет помнить всё и не вешать сервер!
CONTEXT_LIMIT = 100

def get_user_context(chat_id):
    """Вытаскивает историю базара из базы данных"""
    user_data = history_collection.find_one({"chat_id": chat_id})
    if user_data:
        return user_data['messages'][-CONTEXT_LIMIT:]
    return []

def save_to_context(chat_id, role, content):
    """Сохраняет реплику в базу данных"""
    history_collection.update_one(
        {"chat_id": chat_id},
        {"$push": {"messages": {"role": role, "content": content}}},
        upsert=True
    )

def clear_user_context(chat_id):
    """Полное обнуление памяти по команде"""
    history_collection.delete_one({"chat_id": chat_id})

def encode_image_to_base64(image_path):
    """Кодирует картинку в Base64 строку для отправки в OpenRouter"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# Локальная расшифровка аудио (ГС и кружков) в текст
def transcribe_audio_local(ogg_path, chat_id):
    wav_path = f"temp_{chat_id}.wav"
    try:
        # Конвертируем ogg от Телеграма в wav для распознавания
        audio = AudioSegment.from_file(ogg_path, format="ogg")
        audio.export(wav_path, format="wav")
        
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
            # Распознаем русскую речь через бесплатный Google API
            text = r.recognize_google(audio_data, language="ru-RU")
            
        if os.path.exists(wav_path): os.remove(wav_path)
        return text
    except Exception as e:
        print(f"Ошибка распознавания голоса: {e}")
        if os.path.exists(wav_path):
            try: os.remove(wav_path)
            except: pass
        return ""

# Запрос к мозгам ИИ через OpenRouter
def get_bro_response(chat_id, user_message):
    # 1. Записываем сообщение юзера в базу данных
    save_to_context(chat_id, "user", user_message)
    
    # 2. Достаем историю из базы (максимум 100 сообщений)
    history = get_user_context(chat_id)
        
    # Формируем запрос к ИИ с системным промптом во главе
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        # Используем мощную мультимодальную модель, которая и видит, и соображает отлично
        "model": "google/gemini-2.5-flash",
        "messages": messages
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15)
        result = response.json()
        bro_text = result['choices'][0]['message']['content']
        
        # 3. Сохраняем ответ ИИ в базу данных
        save_to_context(chat_id, "assistant", bro_text)
        return bro_text
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return "Слышь, братка, у меня чё-то извилины заклинило на секунду. Повтори мысль!"


@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        bot.reply_to(message, "Здорово, родной! Я твой новый AI-Бро. С этого момента общаемся без тормозов и цензуры. Накидывай текст, шли ГС, кружочки или фотки — я во всё вникну и раскидаю по красоте. Рассказывай, чё на уме?")
    except Exception as e:
        print(f"Ошибка старта: {e}")

@bot.message_handler(commands=['clear'])
def clear_memory(message):
    try:
        clear_user_context(message.chat.id)
        bot.reply_to(message, "Память стёрта, бро! Кто ты вообще такой? Ладно, шучу, накидывай новый базар.")
    except Exception as e:
        print(f"Ошибка очистки: {e}")


# Принимаем ФОТОГРАФИИ
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    temp_photo = f"temp_{chat_id}.jpg"
    
    try:
        bot.send_chat_action(chat_id, 'typing')
        
        # Берем самое лучшее качество фотки (последний элемент в списке)
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Сохраняем временно на диск
        with open(temp_photo, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        # Кодируем в base64 для передачи ИИ
        base64_image = encode_image_to_base64(temp_photo)
        
        # Если юзер допишет текст к фотке — берем его, иначе пишем дефолтный вопрос
        user_caption = message.caption if message.caption else "Зацени фотку, бро, чё думаешь?"
        
        # Формируем структуру с текстом и картинкой для OpenRouter
        vision_content = [
            {"type": "text", "text": user_caption},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            }
        ]
        
        # Записываем в базу MongoDB только текстовую часть, чтобы не захламлять БД гигабайтами картинок
        save_to_context(chat_id, "user", f"[Отправил фото] {user_caption}")
        
        # Вытаскиваем историю сообщений из базы
        history = get_user_context(chat_id)
        
        # Склеиваем контекст, подменяя последнее сообщение на вижн-структуру с картинкой
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
        
        # Записываем ответ ИИ в базу данных
        save_to_context(chat_id, "assistant", bro_text)
        
        bot.reply_to(message, bro_text)
        
    except Exception as e:
        print(f"Ошибка при обработке фото: {e}")
        bot.reply_to(message, "Бля, у меня линза запотела, не могу разглядеть, чё на фотке. Попробуй ещё раз!")
    finally:
        # Удаляем временную фотку и чистим оперативку
        if os.path.exists(temp_photo):
            try: os.remove(temp_photo)
            except: pass
        gc.collect()


# Принимаем ГС и кружки
@bot.message_handler(content_types=['voice', 'video_note'])
def handle_audio(message):
    chat_id = message.chat.id
    temp_ogg = f"temp_{chat_id}.ogg"
    
    try:
        bot.send_chat_action(chat_id, 'record_voice')
        
        if message.content_type == 'voice':
            file_id = message.voice.file_id
        else:
            file_id = message.video_note.file_id
            
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(temp_ogg, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        user_text = transcribe_audio_local(temp_ogg, chat_id)
        
        if os.path.exists(temp_ogg):
            os.remove(temp_ogg)
            
        if not user_text:
            bot.reply_to(message, "Бро, чё-то не разобрал ни слова. Попробуй надиктовать почётче или напиши текстом.")
            return
            
        bot.reply_to(message, f"🎤 *Ты сказал:* _{user_text}_")
        bot.send_chat_action(chat_id, 'typing')
        bro_response = get_bro_response(chat_id, user_text)
        bot.reply_to(message, bro_response)
        
    except Exception as e:
        print(f"Ошибка в обработчике аудио: {e}")
        bot.reply_to(message, "Бля, чё-то уши заложило, не могу твой голос разобрать. Напиши текстом, если не в падлу!")
        if os.path.exists(temp_ogg):
            try: os.remove(temp_ogg)
            except: pass
    finally:
        gc.collect()


# Принимаем обычный текст
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    user_text = message.text
    try:
        bot.send_chat_action(chat_id, 'typing')
        bro_response = get_bro_response(chat_id, user_text)
        bot.reply_to(message, bro_response)
    except Exception as e:
        print(f"Ошибка в обработчике текста: {e}")
    finally:
        gc.collect()


# Запуск бота
if __name__ == '__main__':
    print("Бот стартовал с бесконечной памятью на MongoDB и поддержкой зрения!")
    bot.infinity_polling()

