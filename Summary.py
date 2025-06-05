import os
import json
import sqlite3
from datetime import datetime
from telegram import Update, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from dateutil import parser as date_parser
from groq import Groq
import re

# Replace 'YOUR_TOKEN' with your bot's API token
TOKEN = os.environ.get("TG_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TOKEN:
    raise ValueError("Telegram bot token (TG_BOT_TOKEN) is not set in environment variables.")
if not GROQ_API_KEY:
    raise ValueError("Groq API key (GROQ_API_KEY) is not set in environment variables.")

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('chat_history.db')
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

# Function to summarize chats using Groq API
def summarize_chats_groq(chats):
    client = Groq(api_key=GROQ_API_KEY)

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

# Function to analyze the semantics of the summary
def analyze_summary_semantics(summary):
    client = Groq(api_key=GROQ_API_KEY)

    # Analyze the semantics of the summary
    analysis = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": f'Perform a semantic analysis of the following summary. The semantic analysis should be composed of adjectives and not more than 3 to 4 words: {summary}',
            }
        ],
        model="llama3-8b-8192",
    )

    return analysis.choices[0].message.content

# Function to suggest suitable responses based on chats
def suggest_responses(chats):
    client = Groq(api_key=GROQ_API_KEY)

    # Convert the chat list to JSON
    documents = json.dumps(chats)

    # Generate suitable response suggestions
    suggestions = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": f'Based on the following chats, suggest suitable responses for continuing the conversation effectively. The suggested responses should be small and precise,not more than a sentence, only display the suggested reponses, no introductory line, only the suggested responses in separate lines without bullet points. Suggest 4 responses only, not more, nor less. The suggested reponses can be one worded as well and a sentence too.: {documents}',
            }
        ],
        model="llama3-8b-8192",
    )

    return suggestions.choices[0].message.content.split("\n")  # Return responses as a list



# Function to sanitize button text for Telegram's inline keyboard
def sanitize_button_text(text):
    # Remove newlines and limit button text to 64 characters (Telegram's restriction)
    sanitized = re.sub(r'\s+', ' ', text).strip()
    return sanitized[:64]  # Ensure it's not longer than 64 characters

# /summarize command handler with suggested responses as inline buttons
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

        if filtered_chats:
            # Generate summary, semantic analysis, and suggested responses
            summary = summarize_chats_groq(filtered_chats)
            semantic_analysis = analyze_summary_semantics(summary)
            suggested_responses = suggest_responses(filtered_chats)

            # Debug: Check the content of suggested_responses
            print(f"Suggested responses: {suggested_responses}")

            # Ensure the suggested responses are a list of valid strings
            if not isinstance(suggested_responses, list):
                suggested_responses = suggested_responses.splitlines()

            # Sanitize and create inline keyboard buttons
            keyboard = [
                [InlineKeyboardButton(sanitize_button_text(response), callback_data=sanitize_button_text(response))]
                for response in suggested_responses if response.strip()
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send summary and analysis as text
            await update.message.reply_text(
                f"Summary of chats between {date1} and {date2}:\n{summary}\n\n"
                f"Semantic Analysis:\n{semantic_analysis}"
            )

            # Send inline keyboard for suggested responses
            await update.message.reply_text(
                "Suggested Responses:",
                reply_markup=reply_markup,
    #             do_quote=update.message.build_reply_arguments(
    #     quote=update.message.text,
    #     target_chat_id=update.message.from_user.id
    # )
            )
        else:
            await update.message.reply_text('No chats found in the specified date range.')

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# Callback handler to handle button clicks
async def handle_response_button_click(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Acknowledge the button click

    # Send the clicked response back to the chat
    await query.message.reply_text(f"{query.data}")


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

    # Register the callback query handler for button clicks
    application.add_handler(CallbackQueryHandler(handle_response_button_click))

    # Start polling for updates
    application.run_polling()
