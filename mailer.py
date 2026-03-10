import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from config import KINDLE_EMAIL, SMTP_EMAIL, SMTP_PASSWORD

logger = logging.getLogger(__name__)


def _send_email(filepath: str, filename: str) -> bool:
    """Synchronous email sending via Gmail SMTP."""
    msg = MIMEMultipart()
    msg["From"] = SMTP_EMAIL
    msg["To"] = KINDLE_EMAIL
    msg["Subject"] = "convert"  # "convert" tells Kindle to convert if needed

    msg.attach(MIMEText("", "plain"))

    attachment = MIMEBase("application", "octet-stream")
    with open(filepath, "rb") as f:
        attachment.set_payload(f.read())
    encoders.encode_base64(attachment)

    safe_filename = Path(filepath).name if not filename else filename
    attachment.add_header("Content-Disposition", f"attachment; filename={safe_filename}")
    msg.attach(attachment)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)

    return True


async def send_to_kindle(filepath: str, filename: str) -> bool:
    """Send an epub file to Kindle via Gmail SMTP (async wrapper)."""
    try:
        await asyncio.to_thread(_send_email, filepath, filename)
        logger.info("Sent %s to Kindle (%s)", filename, KINDLE_EMAIL)
        return True
    except Exception as e:
        logger.error("Failed to send to Kindle: %s", e)
        return False
