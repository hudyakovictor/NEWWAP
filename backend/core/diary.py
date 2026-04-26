import json
import os
from datetime import datetime

DIARY_FILE = os.path.join("storage", "diary_db.json")

def add_diary_entry(author: str, content: str):
    os.makedirs(os.path.dirname(DIARY_FILE), exist_ok=True)
    entries = get_diary_entries()
    
    new_entry = {
        "timestamp": datetime.now().isoformat(),
        "author": author,
        "content": content
    }
    entries.append(new_entry)
    
    with open(DIARY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return new_entry

def get_diary_entries(limit: int = 10):
    if not os.path.exists(DIARY_FILE):
        return []
    with open(DIARY_FILE, "r", encoding="utf-8") as f:
        try:
            entries = json.load(f)
            return entries[-limit:] # Возвращаем последние N записей
        except json.JSONDecodeError:
            return []
