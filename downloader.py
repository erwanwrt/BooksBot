import asyncio
import logging
import httpx
from pathlib import Path
from config import DOWNLOADS_DIR

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


async def download_epub(url: str, filename: str) -> str | None:
    """Download an epub file via HTTP streaming. Returns the filepath or None."""
    safe_name = "".join(c for c in filename if c.isalnum() or c in " ._-").strip()
    if not safe_name.endswith(".epub"):
        safe_name += ".epub"
    filepath = DOWNLOADS_DIR / safe_name

    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=300, follow_redirects=True
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    logger.error("Download returned status %d for %s", resp.status_code, url)
                    return None

                with open(filepath, "wb") as f:
                    async for chunk in resp.aiter_bytes(65536):
                        f.write(chunk)

        size = filepath.stat().st_size
        if size < 1024:
            logger.error("Downloaded file too small (%d bytes), likely not a valid epub", size)
            filepath.unlink()
            return None

        logger.info("Downloaded %s (%d bytes)", filepath, size)
        return str(filepath)

    except Exception as e:
        logger.error("Download failed: %s", e)
        if filepath.exists():
            filepath.unlink()
        return None


def cleanup_file(filepath: str) -> None:
    """Delete a file after delivery."""
    try:
        path = Path(filepath)
        if path.exists():
            path.unlink()
            logger.info("Cleaned up %s", filepath)
    except Exception as e:
        logger.error("Cleanup failed for %s: %s", filepath, e)


def get_file_size(filepath: str) -> int:
    """Return file size in bytes."""
    return Path(filepath).stat().st_size
