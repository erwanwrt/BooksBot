import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_IDS = {
    int(uid.strip())
    for uid in os.getenv("TELEGRAM_USER_ID", "0").split(",")
    if uid.strip().isdigit()
}
KINDLE_EMAIL = os.getenv("KINDLE_EMAIL", "")
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ANNAS_ARCHIVE_URL = os.getenv("ANNAS_ARCHIVE_URL", "https://annas-archive.org")

BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024  # 50 MB
