import logging
from functools import wraps
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import TELEGRAM_USER_ID, TELEGRAM_FILE_LIMIT, DOWNLOADS_DIR
from anna_archive import search_books, download_book
from downloader import cleanup_file, get_file_size
from mailer import send_to_kindle

logger = logging.getLogger(__name__)

# Conversation states
CHOOSE_LANG, CHOOSE_BOOK, CHOOSE_DELIVERY = range(3)

LANGUAGES = [
    ("FR", "fr"), ("EN", "en"), ("ES", "es"),
    ("DE", "de"), ("IT", "it"), ("Any", ""),
]


def authorized(func):
    """Decorator to restrict access to the authorized user."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else 0
        if user_id != TELEGRAM_USER_ID:
            logger.warning("Unauthorized access attempt by user %d", user_id)
            if update.message:
                await update.message.reply_text("⛔ Accès non autorisé.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Accès non autorisé.", show_alert=True)
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    return wrapper


@authorized
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📚 *BooksBot*\n\n"
        "Envoyez-moi un titre de livre ou utilisez /search <titre>.\n"
        "Utilisez /cancel pour annuler.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


@authorized
async def search_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text messages or /search command as search queries."""
    if update.message.text.startswith("/search"):
        query = update.message.text.replace("/search", "", 1).strip()
    else:
        query = update.message.text.strip()

    if not query:
        await update.message.reply_text("Veuillez fournir un titre à rechercher.")
        return ConversationHandler.END

    context.user_data["query"] = query

    # Show language selection
    keyboard = []
    row = []
    for label, code in LANGUAGES:
        row.append(InlineKeyboardButton(label, callback_data=f"lang_{code}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await update.message.reply_text(
        f"🔍 Recherche : *{query}*\n\nChoisissez la langue :",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return CHOOSE_LANG


@authorized
async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection and perform search."""
    query_cb = update.callback_query
    await query_cb.answer()

    language = query_cb.data.replace("lang_", "")
    search_query = context.user_data.get("query", "")

    await query_cb.edit_message_text(f"🔎 Recherche en cours pour *{search_query}*...", parse_mode="Markdown")

    results = await search_books(search_query, language)

    if not results:
        await query_cb.edit_message_text("❌ Aucun résultat trouvé.")
        return ConversationHandler.END

    context.user_data["results"] = results

    # Build results keyboard
    keyboard = []
    text_lines = ["📚 *Résultats :*\n"]
    for i, book in enumerate(results):
        title = book["title"][:60]
        extra = book.get("author") or book.get("filename") or book.get("size") or ""
        extra = extra[:40]
        text_lines.append(f"`{i + 1}.` {title}")
        if extra:
            text_lines.append(f"   _{extra}_")
        keyboard.append([InlineKeyboardButton(f"{i + 1}. {title[:40]}", callback_data=f"book_{i}")])

    await query_cb.edit_message_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return CHOOSE_BOOK


@authorized
async def choose_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle book selection and show delivery options."""
    query_cb = update.callback_query
    await query_cb.answer()

    idx = int(query_cb.data.replace("book_", ""))
    results = context.user_data.get("results", [])

    if idx < 0 or idx >= len(results):
        await query_cb.edit_message_text("❌ Sélection invalide.")
        return ConversationHandler.END

    context.user_data["selected_book"] = results[idx]

    book = results[idx]
    keyboard = [
        [InlineKeyboardButton("📱 Telegram", callback_data="deliver_telegram")],
        [InlineKeyboardButton("📖 Kindle", callback_data="deliver_kindle")],
        [InlineKeyboardButton("📱+📖 Les deux", callback_data="deliver_both")],
    ]

    await query_cb.edit_message_text(
        f"📖 *{book['title'][:80]}*\n\nComment souhaitez-vous recevoir le livre ?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return CHOOSE_DELIVERY


@authorized
async def choose_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle delivery choice: download and deliver the book."""
    query_cb = update.callback_query
    await query_cb.answer()

    method = query_cb.data.replace("deliver_", "")
    book = context.user_data.get("selected_book")

    if not book:
        await query_cb.edit_message_text("❌ Erreur : aucun livre sélectionné.")
        return ConversationHandler.END

    await query_cb.edit_message_text("⏳ Téléchargement en cours...\n⏱ Compteur en cours (jusqu'à 60s), veuillez patienter.")

    # Download the book (resolve URL + download in one browser session)
    filename = f"{book['title'][:80]}.epub"
    safe_name = "".join(c for c in filename if c.isalnum() or c in " ._-").strip()
    if not safe_name.endswith(".epub"):
        safe_name += ".epub"
    filepath = str(DOWNLOADS_DIR / safe_name)

    success = await download_book(book["detail_url"], filepath)
    if not success:
        await query_cb.edit_message_text("❌ Échec du téléchargement.")
        return ConversationHandler.END

    file_size = get_file_size(filepath)
    send_telegram = method in ("telegram", "both")
    send_kindle = method in ("kindle", "both")
    status_parts = []

    try:
        # Step 3a: Send via Telegram
        if send_telegram:
            if file_size > TELEGRAM_FILE_LIMIT:
                status_parts.append(f"⚠️ Fichier trop volumineux pour Telegram ({file_size // (1024*1024)} MB > 50 MB)")
            else:
                await query_cb.edit_message_text("📤 Envoi sur Telegram...")
                with open(filepath, "rb") as f:
                    await query_cb.get_bot().send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        filename=filename,
                        caption=f"📖 {book['title'][:100]}",
                    )
                status_parts.append("✅ Envoyé sur Telegram")

        # Step 3b: Send to Kindle
        if send_kindle:
            await query_cb.edit_message_text("📧 Envoi vers Kindle...")
            success = await send_to_kindle(filepath, filename)
            if success:
                status_parts.append("✅ Envoyé sur Kindle")
            else:
                status_parts.append("❌ Échec de l'envoi Kindle")

    finally:
        cleanup_file(filepath)

    result_text = f"📖 *{book['title'][:80]}*\n\n" + "\n".join(status_parts)
    await query_cb.edit_message_text(result_text, parse_mode="Markdown")
    return ConversationHandler.END


@authorized
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    context.user_data.clear()
    await update.message.reply_text("🚫 Recherche annulée.")
    return ConversationHandler.END


def get_handlers() -> list:
    """Return the list of handlers to register."""
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("search", search_entry),
            MessageHandler(filters.TEXT & ~filters.COMMAND, search_entry),
        ],
        states={
            CHOOSE_LANG: [CallbackQueryHandler(choose_language, pattern=r"^lang_")],
            CHOOSE_BOOK: [CallbackQueryHandler(choose_book, pattern=r"^book_\d+$")],
            CHOOSE_DELIVERY: [CallbackQueryHandler(choose_delivery, pattern=r"^deliver_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    return [
        CommandHandler("start", start),
        conv_handler,
    ]
