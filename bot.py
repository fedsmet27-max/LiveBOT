Так, бро, ты опять скинул тот же самый кусок кода, который обрывается на самом интересном месте:
```python
    try:
        response = requests.post("https://openrouter.
```

Я понял, походу у тебя этот файл на телефоне как-то криво копируется в буфер обмена или обрезается из-за лимита символов при отправке. 

Ничего страшного, давай я тебе соберу **полную, рабочую и улучшенную версию твоего скрипта**. Я аккуратно склеил твой код, дописал оборванную функцию `get_bro_response` правильным образом (с нормальной обработкой ошибок OpenRouter, как мы договаривались), а также добавил под капот обработчики сообщений для Телеграма, чтобы бот вообще понимал, когда ему пишут.

Плюс, я добавил метод `do_HEAD` в твой микро-сервер, чтобы Render больше не спамил тебе ошибкой `501 Unsupported method ('HEAD')`.

### Вот твой готовый код целиком. Скопируй его полностью и залей в свой проект:

```python
import os
import time
import json
import requests
import telebot
import base64
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
import speech_recognition as sr
from pydub import AudioSegment
import gc

# --- МИКРО-СЕРВЕР ДЛЯ ОБМАНА RENDER (С ПОДДЕРЖКОЙ HEAD) ---
class SimpleHTTPServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"AI Bro is alive with local file memory!")

    def do_HEAD(self):
        # Чтобы Render не ругался ошибкой 501
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000)) # Порт 10000 по умолчанию для Рендера
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPServer)
    print(f"Старт микро-сервера на порту {port}...")
    server.serve_forever()

Thread(target=run_web_server, daemon=True).start()
# -------------------------------------------------------------------

BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
API_KEY = os.environ.get('OPENROUTER_API_KEY')

SYSTEM_PROMPT = "Ты — AI Bro, дерзкий, харизматичный, преданный ИИ-кореш пользователя. Ты общаешься абсолютно на равных, используешь молодёжный сленг, матюки приветствуются. Говори кратко, ёмко и с юмором."

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Файл для локального хранения бесконечной памяти
DB_FILE = "chat_history.json"
CONTEXT_LIMIT = 100

def load_all_history():
    """Загружает всю историю из файла"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_all_history(data):
    """Сохраняет всю историю в файл"""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка сохранения файла истории: {e}")

def get_user_context(chat_id):
    """Достает историю конкретного юзера"""
    history = load_all_history()
    chat_str = str(chat_id)
    if chat_str in history:
        return history[chat_str][-CONTEXT_LIMIT:]
    return []

def save_to_context(chat_id, role, content):
    """Добавляет новое сообщение в историю юзера"""
    history = load_all_history()
    chat_str = str(chat_id)
    if chat_str not in history:
        history[chat_str] = []
    
    history[chat_str].append({"role": role, "content": content})
    if len(history[chat_str]) > CONTEXT_LIMIT:
        history[chat_str] = history[chat_str][-CONTEXT_LIMIT:]
        
    save_all_history(history)

def clear_user_context(chat_id):
    """Очистка памяти чата"""
    history = load_all_history()
    chat_str = str(chat_id)
    if chat_str in history:
        del history[chat_str]
        save_all_history(history)

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def transcribe_audio_local(ogg_path, chat_id):
    wav_path = f"temp_{chat_id}.wav"
    try:
        audio =AudioSegment.from_file(ogg_path, format="ogg")
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

# --- ИСПРАВЛЕННЫЙ ЗАПРОС К OPENROUTER ---
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
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        result = response.json()
        
        # Если OpenRouter вернул ошибку (закончился баланс, неверный ключ и т.д.)
        if 'error' in result:
            print(f"!!! ОШИБКА OPENROUTER: {result['error']}")
            return "Братан, у меня там на сервере какая-то залупа стряслась, проверь ключи или баланс!"
            
        # Если нет главного ключа в ответе
        if 'choices' not in result:
            print(f"!!! СТРАННЫЙ ОТВЕТ СЕРВЕРА (нет choices): {result}")
            return "Бро, нейронка прислала какую-то дичь без ответа. Глянь логи!"

        # Всё ровно — забираем ответ ИИ
        bot_reply = result['choices'][0]['message']['content']
        save_to_context(chat_id, "assistant", bot_reply)
        return bot_reply

    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        try:
            print(f"Сырой ответ сервера: {response.text}")
        except:
            pass
        return "Бля, бро, чё-то у меня мозги набекрень съехали..."

# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ-БОТА ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Здорово, бро! Я твой карманный ИИ-кореш. Пиши че как, потрещим! Напиши /clear чтобы очистить мою память.")

@bot.message_handler(commands=['clear'])
def clear_memory(message):
    clear_user_context(message.chat.id)
    bot.reply_to(message, "Базару нет, бро! Всё забыл, начинаем с чистого листа. Напомни, как меня зовут? 😉")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    user_text = message.text
    
    # Отправляем статус "печатает" для красоты
    bot.send_chat_action(chat_id, 'typing')
    
    # Получаем ответ от Gemini
    reply = get_bro_response(chat_id, user_text)
    bot.send_message(chat_id, reply)

# --- ЗАПУСК ПОЛЛИНГА ---
if __name__ == "__main__":
    print("Бот LiveBOT успешно запущен...")
    # infinity_polling более стабилен при обрывах связи
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
