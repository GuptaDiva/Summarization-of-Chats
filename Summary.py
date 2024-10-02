import json
import sqlite3
from telegram import Update, Message
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext
from dateutil import parser as date_parser
import os
from groq import Groq

# Replace 'YOUR_TOKEN' with your bot's API token
TOKEN = os.environ.get("TG_BOT_TOKEN")

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect( 'chat_history.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            text TEXT,
            date TEXT,
            user TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Function to store incoming messages in the database
def store_message(message: Message):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (text, date, user) VALUES (?, ?, ?)
    ''', (message.text, message.date.isoformat(), message.from_user.username if message.from_user.username else message.from_user.full_name))
    conn.commit()
    conn.close()

# Function to extract chats within date range
def get_chats_in_date_range(start_date, end_date):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM messages WHERE date BETWEEN ? AND ?
    ''', (start_date.isoformat(), end_date.isoformat()))
    rows = cursor.fetchall()
    conn.close()
    
    # Convert rows to a list of dictionaries
    return [{'id': row[0], 'text': row[1], 'date': row[2], 'user': row[3]} for row in rows]

# /summarize command handler
def summarize_chats_groq(chats):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    # Convert the chat list to JSON
    documents = json.dumps(chats)

    # Send the chats to Groq API for summarization
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": f'Summarize the semantic meaning of these chats and give me the summary in a paragraph: {documents}',
            }
        ],
        model="llama3-8b-8192",
    )

    # Extract the summary from the response
    return chat_completion.choices[0].message.content

# /summarize command handler
async def summarize(update: Update, context: CallbackContext) -> None:
    try:
        if len(context.args) != 2:
            await update.message.reply_text('Please provide two dates in the format: /summarize <date1> <date2>')
            return

        # Parse the dates from the command arguments
        date1 = date_parser.parse(context.args[0]).astimezone()
        date2 = date_parser.parse(context.args[1]).astimezone()

        # Filter chats between the specified date range
        filtered_chats = get_chats_in_date_range(date1, date2)

        # If there are chats, send them for summarization
        if filtered_chats:
            summary = summarize_chats_groq(filtered_chats)
            await update.message.reply_text(f"Summary of chats between {date1} and {date2}:\n{summary}")
        else:
            await update.message.reply_text('No chats found in the specified date range.')

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# Message handler to capture all messages
async def handle_message(update: Update, context: CallbackContext) -> None:
    store_message(update.message)

# Initialize the bot and start polling for updates
if __name__ == '__main__':
    init_db()  # Initialize the database

    # Initialize the application
    application = ApplicationBuilder().token(TOKEN).build()

    # Register the /summarize command handler
    application.add_handler(CommandHandler('summarize', summarize))

    # Register the message handler to capture all messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start polling for updates
    application.run_polling()