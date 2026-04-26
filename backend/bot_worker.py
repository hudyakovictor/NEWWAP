import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from core.diary import get_diary_entries

TELEGRAM_TOKEN = "8686482593:AAEeSFo-21w6jpCRs7zj3NZf2FnSsaV0ENw"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("DEEPUTIN Tracker подключен. Введите /diary для получения статуса расследования.")

async def send_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entries = get_diary_entries(limit=3)
    if not entries:
        await update.message.reply_text("Дневник пока пуст.")
        return
        
    response = "📕 **Последние записи расследования:**\n\n"
    for entry in entries:
        date_str = entry['timestamp'][:16].replace("T", " ")
        response += f"⏱ {date_str} | {entry['author']}\n{entry['content']}\n\n"
        
    await update.message.reply_text(response, parse_mode='Markdown')

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("diary", send_diary))
    
    print("Бот запущен...")
    app.run_polling()
