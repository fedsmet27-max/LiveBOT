
import os, requests, telebot, base64, json, gc, time, threading
import speech_recognition as sr
from pydub import AudioSegment
import cv2
from http.server import BaseHTTPRequestHandler, HTTPServer

# Токены
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
API_KEY = os.environ.get('OPENROUTER_API_KEY')
SYSTEM_PROMPT = "Ты — AI Bro, дерзкий, харизматичный ИИ-кореш. Общайся на равных, юзай молодёжный сленг и матюки. Говори кратко, ёмко. Обращайся к юзеру 'Федя' или 'брат', 'родной', склоняй как по кайфу."
DB_FILE = "chat_history.json"
LIMIT = 50

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# --- ВЕБ-СЕРВЕР ДЛЯ ОБМАНА RENDER ---
class WebhookServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("AI Bro в эфире, Render, не туши меня!".encode("utf-8"))
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), WebhookServer)
    print(f"Фейк-сервер запущен на порту {port}")
    server.serve_forever()

# --- БАЗА ДАННЫХ И ЛОГИКА ---
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
        return "Ты че молчишь, родной? Напиши че-нибудь!"
    if text_query and not b64_img:
        save_mem(chat_id, "user", text_query)
    
    from datetime import datetime
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
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30)
        res_json = res.json()
        
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

# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ ---
@bot.message_handler(commands=['start'])
def start_cmd(m):
    clear_mem(m.chat.id)
    bot.reply_to(m, "Здорово, Федя! Я ИИ Бро — твой кореш на связи. Че как сам, родной? Пиши, шли гс, кружки или фотки — всё разберем!")

@bot.message_handler(commands=['clear'])
def clear_cmd(m):
    clear_mem(m.chat.id)
    bot.reply_to(m, "Память чиста, родной! Начинаем заново.")

@bot.message_handler(content_types=['text'])
def handle_text(m):
    ans = ask_gemini(m.chat.id, m.text)
    bot.reply_to(m, ans)

@bot.message_handler(content_types=['voice'])
def handle_voice(m):
    bot.send_chat_action(m.chat.id, 'typing')
    text, _ = process_media(m.voice.file_id, m.chat.id)
    if text:
        ans = ask_gemini(m.chat.id, text)
        bot.reply_to(m, f"Ты сказал: \"{text}\"\n\n{ans}")
    else:
        bot.reply_to(m, "Родной, не разобрал твой базар. Повтори почетче.")

@bot.message_handler(content_types=['video_note'])
def handle_video_note(m):
    bot.send_chat_action(m.chat.id, 'typing')
    text, b64_img = process_media(m.video_note.file_id, m.chat.id, is_video=True)
    ans = ask_gemini(m.chat.id, text, b64_img)
    bot.reply_to(m, ans)

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    bot.send_chat_action(m.chat.id, 'typing')
    try:
        file_info = bot.get_file(m.photo[-1].file_id)
        img_data = bot.download_file(file_info.file_path)
        b64_img = base64.b64encode(img_data).decode('utf-8')
        ans = ask_gemini(m.chat.id, m.caption, b64_img)
        bot.reply_to(m, ans)
    except Exception as e:
        print(e)
        bot.reply_to(m, "Не смог открыть картинку, брат.")

# --- ЗАПУСК ВСЕЙ СИСТЕМЫ ---
def run_bot():
    print("Чистим вебхуки...")
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    
    print("Бот погнал в фоне!...")
    # non_stop=True поможет боту пережить конфликты и мягкий перезапуск Render
    bot.infinity_polling(
        timeout=20,
        long_polling_timeout=15,
        skip_pending=True,
        allowed_updates=[],

    )

if __name__ == "__main__":
    # 1. Запускаем бота в отдельном фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # 2. Запускаем сервер на главном потоке (он будет держать соединение с Render вечно)
    run_web_server()
