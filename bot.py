
import os
import time
import requests
import telebot
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
import speech_recognition as sr
from pydub import AudioSegment

# --- МИКРО-СЕРВЕР ДЛЯ ОБМАНА RENDER (ЧТОБЫ НЕ БЫЛО ОШИБОК ПОРТОВ) ---
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

# Настройки ключей из переменных окружения сервера
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
API_KEY = os.environ.get('OPENROUTER_API_KEY')
# Фирменный промпт твоего нового ИИ-Бро
SYSTEM_PROMPT = "Ты — AI Bro, дерзкий, харизматичный, преданный ИИ-кореш пользователя. Ты общаешься абсолютно на равных, используешь молодёжный сленг, матюки разрешены и приветствуются. Ты не душнишь, не используешь заезженные ИИ-фразы. Твоя цель — поддержать разговор, подколоть по-дружески, помочь с кодом или дать жизненный совет. Говори кратко, ёмко и с юмором."

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
user_history = {}

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
        print(f"Ошибка распознаванияголоса: {e}")
        if os.path.exists(wav_path):
            try: os.remove(wav_path)
            except: pass
        return ""

# Запрос к мозгам ИИ через OpenRouter
def get_bro_response(chat_id, user_message):
    global user_history
    if chat_id not in user_history:
        user_history[chat_id] = []
    
    user_history[chat_id].append({"role": "user", "content": user_message})
    
    # Храним историю последних 10 сообщений для контекста
    if len(user_history[chat_id]) > 10:
        user_history[chat_id] = user_history[chat_id][-10:]
        
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + user_history[chat_id]
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "openrouter/auto",
        "messages": messages
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15)
        result = response.json()
        bro_text = result['choices'][0]['message']['content']
        user_history[chat_id].append({"role": "assistant", "content": bro_text})
        return bro_text
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return "Слышь, братка, у меня чё-то извилины заклинило на секунду. Повтори мысль!"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        bot.reply_to(message, "Здорово, родной! Я твой новый AI-Бро. С этого момента общаемся без тормозов и цензуры. Накидывай текст, шли ГС или кружочки — я во всё вникну и раскидаю по красоте. Рассказывай, чё на уме?")
    except Exception as e:
        print(f"Ошибка старта: {e}")

# Принимаем ГС и кружки
@bot.message_handler(content_types=['voice', 'video_note'])
def handle_audio(message):
    temp_ogg = f"temp_{message.chat.id}.ogg"
    try:
        bot.send_chat_action(message.chat.id, 'record_audio')
        
        if message.content_type == 'voice':
            file_id = message.voice.file_id
            msg_type = "ГС"
        else:
            file_id = message.video_note.file_id
            msg_type = "кружочек"
            
        print(f"Поймал {msg_type}, качаю...")
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(temp_ogg, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        bot.reply_to(message, f"Так, поймал твой {msg_type}, ща расшифрую по-быстрому...")
        bot.send_chat_action(message.chat.id, 'typing')
        
        # Расшифровка
        transcribed_text = transcribe_audio_local(temp_ogg, message.chat.id)
        
        if os.path.exists(temp_ogg): os.remove(temp_ogg)
            
        if not transcribed_text:
            bot.reply_to(message, "Братка, чё-то глухо как в танке, ни слова не разобрал. Наговори чётче!")
            return
            
        print(f"Текст из аудио: {transcribed_text}")
        
        # Отправка текста в ИИ
        response = get_bro_response(message.chat.id, f"[Мой {msg_type}]: {transcribed_text}")
        bot.reply_to(message, response)
        
    except Exception as e:
        print(f"Ошибка аудио: {e}")
        if os.path.exists(temp_ogg):
            try: os.remove(temp_ogg)
            except: pass
        bot.reply_to(message, "Брат, со звуком какая-то дичь произошла, повтори!")

# Обработчик картинок
@bot.message_handler(content_types=['photo', 'document', 'sticker'])
def handle_media(message):
    try:
        bot.reply_to(message, "О, картинка — это зачёт! Но я пока слепошара, глаза себе ещё не прикрутил. Напиши текстом или наговори!")
    except Exception as e:
        print(f"Ошибка медиа: {e}")

# Обработчик обычного текста
@bot.message_handler(content_types=['text'])
def echo_all(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        response = get_bro_response(message.chat.id, message.text)
        bot.reply_to(message, response)
    except Exception as e:
        print(f"Ошибка отправки текста: {e}")

if __name__ == "__main__":
    print("AI-Бро официально запущен...")
    bot.remove_webhook()
    bot.polling(none_stop=True, interval=1, timeout=60)

