import time
import requests
import os
import json
from datetime import datetime

TOKEN = "8686482593:AAEeSFo-21w6jpCRs7zj3NZf2FnSsaV0ENw"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
DIARY_FILE = "/Users/victorkhudyakov/dutin/newapp/storage/diary_db.json"

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 100, "offset": offset}
    try:
        resp = requests.get(url, params=params)
        return resp.json()
    except Exception as e:
        print("Error getting updates:", e)
        return None

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def send_document(chat_id, filepath):
    url = f"{BASE_URL}/sendDocument"
    with open(filepath, "rb") as f:
        requests.post(url, data={"chat_id": chat_id}, files={"document": f})

def format_diary_md():
    if not os.path.exists(DIARY_FILE):
        return "Дневник пока пуст."
    
    with open(DIARY_FILE, "r", encoding="utf-8") as f:
        try:
            entries = json.load(f)
        except json.JSONDecodeError:
            return "Ошибка чтения дневника."
            
    lines = ["# Дневник Расследования DEEPUTIN\n"]
    for entry in entries:
        dt = datetime.fromisoformat(entry.get("timestamp", "")).strftime("%Y-%m-%d %H:%M")
        author = entry.get("author", "Unknown")
        content = entry.get("content", "")
        lines.append(f"**[{dt}] {author}:**\n{content}\n")
        
    md_path = "/Users/victorkhudyakov/dutin/newapp/storage/diary_export.md"
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path

def main():
    print("Bot started...")
    offset = None
    while True:
        updates = get_updates(offset)
        if updates and updates.get("ok"):
            for item in updates.get("result", []):
                offset = item["update_id"] + 1
                msg = item.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                
                if text == "/start":
                    send_message(chat_id, "Привет! Я бот-ассистент расследования DEEPUTIN. Напиши /diary чтобы получить актуальный дневник.")
                elif text == "/diary":
                    send_message(chat_id, "Собираю актуальный дневник...")
                    md_path = format_diary_md()
                    if md_path.endswith(".md"):
                        send_document(chat_id, md_path)
                    else:
                        send_message(chat_id, md_path)
        time.sleep(1)

if __name__ == "__main__":
    main()
