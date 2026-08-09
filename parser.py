import os
import json
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
AI_API_KEY = os.getenv("AI_API_KEY")

# Укажите юзернеймы каналов-источников для парсинга (без символа @)
CHANNELS = ["durov", "tginfo", "news"] 

STATE_FILE = "last_posts.json"

def process_with_ai(text):
    """Обработка текста поста через OpenRouter API."""
    if not AI_API_KEY:
        print("AI_API_KEY не задан, отправляем оригинальный текст.")
        return text

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = (
        "Ты — профессиональный редактор новостного Telegram-канала. "
        "Сделай краткую выжимку (рерайт) следующего поста на русском языке. "
        "Сохрани только ключевой смысл, сделай текст емким и структурированным, добавь 1-2 уместных эмодзи. "
        "Не добавляй вводных слов вроде 'Вот выжимка:' или 'Рерайт:'."
    )

    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=25)
        response.raise_for_status()
        data = response.json()
        ai_text = data["choices"][0]["message"]["content"].strip()
        return ai_text
    except Exception as e:
        print(f"Ошибка при запросе к ИИ: {e}. Отправляем оригинал.")
        return text

def load_last_posts():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_last_posts(data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_telegram_message(text):
    if not BOT_TOKEN or not TARGET_CHAT_ID:
        print("Ошибка: BOT_TOKEN или TARGET_CHAT_ID не заданы!")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TARGET_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def parse_channel(channel_name, last_id):
    url = f"https://t.me/s/{channel_name}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Не удалось открыть страницу {channel_name}: HTTP {response.status_code}")
            return last_id
        
        soup = BeautifulSoup(response.text, "html.parser")
        messages = soup.find_all("div", class_="tgme_widget_message")
        
        if not messages:
            return last_id

        if last_id == 0:
            last_msg_data = messages[-1].get("data-post")
            if last_msg_data and "/" in last_msg_data:
                init_id = int(last_msg_data.split("/")[1])
                print(f"Первичная инициализация {channel_name}. Запомнили пост #{init_id}")
                return init_id

        new_last_id = last_id
        
        for msg in messages:
            post_data = msg.get("data-post")
            if not post_data or "/" not in post_data:
                continue
            
            post_id = int(post_data.split("/")[1])
            if post_id <= last_id:
                continue
            
            text_div = msg.find("div", class_="tgme_widget_message_text")
            if not text_div:
                continue
            
            raw_text = text_div.get_text(separator="\n", strip=True)
            
            print(f"Обработка нового поста #{post_id} из @{channel_name} через ИИ...")
            ai_processed_text = process_with_ai(raw_text)
            
            caption = f"<b>Пост из @{channel_name}:</b>\n\n{ai_processed_text}"
            send_telegram_message(caption)
            
            if post_id > new_last_id:
                new_last_id = post_id
                
        return new_last_id

    except Exception as e:
        print(f"Ошибка парсинга {channel_name}: {e}")
        return last_id

def main():
    last_posts = load_last_posts()
    
    for channel in CHANNELS:
        print(f"Проверка канала: @{channel}")
        current_last_id = last_posts.get(channel, 0)
        new_last_id = parse_channel(channel, current_last_id)
        last_posts[channel] = new_last_id
        
    save_last_posts(last_posts)

if __name__ == "__main__":
    main()
