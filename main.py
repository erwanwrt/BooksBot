import logging
from telegram.ext import Application
from config import TELEGRAM_BOT_TOKEN
from bot import get_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Check your .env file.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    for handler in get_handlers():
        application.add_handler(handler)

    logger.info("BooksBot started. Polling...")
    application.run_polling()


if __name__ == "__main__":
    main()
