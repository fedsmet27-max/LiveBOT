import os, requests, telebot, base64, json, gc, time
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
import speech_recognition as sr
from pydub import AudioSegment
import cv2

class SimpleHTTPServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"AI Bro is alive!")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

Thread(target=lambda: HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), SimpleHTTPServer).serve_forever(), daemon=True).start()

BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
API_KEY = os.environ.get('OPENROUTER_API_KEY')
SYSTEM_PROMPT = "Ты — AI Bro, дерзкий, харизматичный ИИ-кореш. Общайся на равных, юзай молодёжный сленг и матюки. Говори кратко, ёмко."
DB_FILE = "chat_history.json"
LIMIT = 50

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def load_mem():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_mem(chat_id, role, content):
    data = load_mem(); cid = str(chat_id)
    if cid not in data: data[cid] = []
    data[cid].append({"role": role, "content": content})
    data[cid] = data[cid][-LIMIT:]
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e: print(f"Ошибка памяти: {e}")

def get_mem(chat_id):
    return load_mem().get(str(chat_id), [])[-LIMIT:]

def clear_mem(chat_id):
    data = load_mem()
    if str(chat_id) in data:
        del data[str(chat_id)]
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f)
        except: pass

def process_media(file_id, chat_id, is_video=False):
    ogg_path, wav_path, img_path = f"t_{chat_id}.ogg", f"t_{chat_id}.wav", f"t_{chat_id}.jpg"
    text, b64_img = "", None
    try:
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(ogg_path, 'wb') as f: f.write(downloaded_file)
        
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
    except Exception as e: print(f"Медиа ошибка: {e}")
    finally:
        for p in [ogg_path, wav_path, img_path]:
            if os.path.exists(p): os.remove(p)
        gc.collect()
    return text, b64_img

def ask_gemini(chat_id, text_query, b64_img=None):
    if not text_query and not b64_img:
        return "Ты че молчишь, бро? Напиши че-нибудь!"
    if text_query and not b64_img:
        save_mem(chat_id, "user", text_query)
    
    history = get_mem(chat_id)
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    if b64_img:
        user_content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}]
        if text_query:
            user_content.append({"type": "text", "text": f"Бро прислал кружок и сказал: \"{text_query}\". Ответь ему."})
        else:
            user_content.append({"type": "text", "text": "Че на кадре из кружка, бро?"})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_content}]
    else:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    data = {"model": "google/gemini-2.5-flash", "messages": messages, "max_tokens": 1000}
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=40).json()
        if 'choices' in res:
            reply = res['choices'][0]['message']['content']
            if not b64_img: save_mem(chat_id, "assistant", reply)
            return reply
        return "Бро, у меня на сервере косяк, проверь баланс OpenRouter!"
    except Exception as e:
        print(f"Ошибка ИИ: {e}"); return "Бля, бро, че-то мозги набекрень съехали..."

@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "Здорово, бро! Я твой ИИ-кореш. Я вижу кружки, фотки, слышу ГС и всё помню! Очистить память: /clear.")

@bot.message_handler(commands=['clear'])
def clear(m):
    clear_mem(m.chat.id)
    bot.reply_to(m, "Всё забыл, голова пустая, бро! 😉")

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.strip() == "": return
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, ask_gemini(m.chat.id, m.text))

@bot.message_handler(content_types=['voice', 'video_note'])
def handle_audio(m):
    bot.send_chat_action(m.chat.id, 'typing')
    is_video = m.content_type == 'video_note'
    file_id = m.video_note.file_id if is_video else m.voice.file_id
    
    bot.reply_to(m, "Зазырим кружок... 👀" if is_video else "Слушаю тебя, бро... 🎧")
    text, b64_img = process_media(file_id, m.chat.id, is_video)
    
    if is_video:
        info = f"Ты сказал: \"{text}\"\n\nАнализирую кружок..." if text and text.strip() else "Ты записал кружок молча.\n\nАнализирую..."
        bot.reply_to(m, info)
        bot.reply_to(m, ask_gemini(m.chat.id, text, b64_img))
    else:
        if not text or not text.strip():
            bot.reply_to(m, "Бля, не разобрал ни слова в ГС. Попробуй сказать чётче.")
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
        bot.reply_to(m, ask_gemini(m.chat.id, m.caption if m.caption else "", b64_img))
    except: bot.reply_to(m, "Не смог открыть картинку, бро.")
        

    except Exception as e: print(f"Ошибка вебхука: {e}")
    print("Бот погнал!...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)if __name__ == "__main__":
    print("Сносим все старые коннекты в Телеге...")
    try:
        # Удаляем вебхук принудительно
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e: 
        print(f"Ошибка сброса вебхука: {e}")
    if __name__ == "__main__":
       bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)

    print("Супер-Бот погнал!...")
    # Тут добавлен allowed_updates=[] — он заставляет Телеграм сбросить ВСЕ старые запросы обновлений
    bot.infinity_polling(
        timeout=20, 
        long_polling_timeout=15, 
        skip_pending=True, 
        allowed_updates=[]
    )

