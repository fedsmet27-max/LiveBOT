import os, requests, telebot, base64, json, gc
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
import speech_recognition as sr
from pydub import AudioSegment

# --- МИКРО-СЕРВЕР ---
class SimpleHTTPServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"AI Bro is fully armed with memory!")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

Thread(target=lambda: HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), SimpleHTTPServer).serve_forever(), daemon=True).start()

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
API_KEY = os.environ.get('OPENROUTER_API_KEY')
SYSTEM_PROMPT = "Ты — AI Bro, дерзкий, харизматичный, преданный ИИ-кореш. Общайся на равных, юзай молодёжный сленг и матюки. Говори кратко, ёмко."
DB_FILE = "chat_history.json"
LIMIT = 50 # Храним последние 50 сообщений, чтоб контекст не разрывало

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# --- БЕСКОНЕЧНАЯ ЛОКАЛЬНАЯ ПАМЯТЬ ---
def load_mem():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_mem(chat_id, role, content):
    data = load_mem()
    cid = str(chat_id)
    if cid not in data: data[cid] = []
    data[cid].append({"role": role, "content": content})
    data[cid] = data[cid][-LIMIT:] # Обрезаем по лимиту
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e: print(f"Ошибка записи памяти: {e}")

def get_mem(chat_id):
    mem = load_mem()
    return mem.get(str(chat_id), [])[-LIMIT:]

def clear_mem(chat_id):
    data = load_mem()
    if str(chat_id) in data:
        del data[str(chat_id)]
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f)
        except: pass

# --- РАБОТА С ГС И КРУЖКАМИ ---
def transcribe_audio(file_id, chat_id, is_video=False):
    ogg_path = f"temp_{chat_id}.ogg"
    wav_path = f"temp_{chat_id}.wav"
    try:
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(ogg_path, 'wb') as new_file: new_file.write(downloaded_file)
        
        audio = AudioSegment.from_file(ogg_path, format="mp4" if is_video else "ogg")
        audio.export(wav_path, format="wav")
        
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            text = r.recognize_google(r.record(source), language="ru-RU")
        return text
    except Exception as e:
        print(f"Ошибка аудио: {e}"); return ""
    finally:
        for p in [ogg_path, wav_path]:
            if os.path.exists(p): os.remove(p)
        gc.collect()

# --- ЗАПРОС К OPENROUTER (С УЧЕТОМ ПАМЯТИ) ---
def ask_gemini(chat_id, text_query, b64_img=None):
    if text_query and not b64_img:
        save_mem(chat_id, "user", text_query)
    
    history = get_mem(chat_id)
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    # Формируем текущее сообщение (с картинкой или без)
    if b64_img:
        user_content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}]
        if text_query: user_content.append({"type": "text", "text": text_query})
        # Картинки в историю чата не пишем (они слишкомжирные для JSON), отправляем разово
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_content}]
    else:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    data = {"model": "google/gemini-2.5-flash", "messages": messages}
    
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=40).json()
        if 'choices' in res:
            reply = res['choices'][0]['message']['content']
            if not b64_img: # Историю переписки без картинок пишем в память
                save_mem(chat_id, "assistant", reply)
            return reply
        print(f"Ошибка OpenRouter: {res}"); return "Бро, какая-то лажа с ключами или балансом на OpenRouter..."
    except Exception as e:
        print(f"Ошибка ИИ: {e}"); return "Бля, бро, че-то у меня мозги набекрень съехали..."

# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "Здорово, бро! Я твой ИИ-кореш с бесконечной памятью. Воспринимаю текст, ГС, кружки и фотки. Чтобы стереть мне память, пиши /clear. Жги!")

@bot.message_handler(commands=['clear'])
def clear(m):
    clear_mem(m.chat.id)
    bot.reply_to(m, "Базару нет, бро! Всё забыл, голова пустая. Напомни, как меня зовут? 😉")

@bot.message_handler(content_types=['text'])
def handle_text(m):
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, ask_gemini(m.chat.id, m.text))

@bot.message_handler(content_types=['voice', 'video_note'])
def handle_audio(m):
    bot.send_chat_action(m.chat.id, 'typing')
    is_video = m.content_type == 'video_note'
    file_id = m.video_note.file_id if is_video else m.voice.file_id
    
    bot.reply_to(m, "Слушаю тебя, бро... 🎧")
    text = transcribe_audio(file_id, m.chat.id, is_video)
    
    if not text:
        bot.reply_to(m, "Бля, не разобрал ни слова. Попробуй сказать четче.")
        return
        
    bot.reply_to(m, f"Ты сказал: \"{text}\"\n\nДумаю...")
    bot.reply_to(m, ask_gemini(m.chat.id, text))

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, "Опа, зазырим че там... 👀")
    try:
        file_info = bot.get_file(m.photo[-1].file_id)
        img_data = bot.download_file(file_info.file_path)
        b64_img = base64.b64encode(img_data).decode('utf-8')
        caption = m.caption if m.caption else ""
        bot.reply_to(m, ask_gemini(m.chat.id, caption, b64_img))
    except Exception as e:
        print(f"Ошибка фото: {e}")
        bot.reply_to(m, "Не смог открыть картинку, бро. Че-то пошло не так.")
if __name__ == "__main__":
    print("Выметаем старых зомби из Телеги...")
    try:
        # Принудительно удаляем вебхук и чистим зависшие апдейты
        bot.remove_webhook()
        # Даем Телеге 2 секунды раздуплиться
        time.sleep(2) 
    except Exception as e:
        print(f"Не удалось сбросить вебхук: {e}")

    print("Супер-Бот успешно запущен на чистом соединении!...")
    # Запускаем поллинг, заставляя Телегу забыть про старые запросы (skip_pending=True)
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)

  
