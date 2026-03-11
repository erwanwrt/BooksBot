import re
import asyncio
import logging
import httpx
from pathlib import Path
from urllib.parse import urlencode
from playwright.async_api import async_playwright, BrowserContext
from bs4 import BeautifulSoup
from config import ANNAS_ARCHIVE_URL, BASE_DIR

logger = logging.getLogger(__name__)

BROWSER_DATA_DIR = str(BASE_DIR / "browser_data")
POLL_INTERVAL = 3  # seconds between checks for download link
POLL_MAX_WAIT = 90  # max seconds to wait for countdown
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

LANGUAGE_MAP = {
    "fr": "fr",
    "en": "en",
    "es": "es",
    "de": "de",
    "it": "it",
}

# Regex to find a direct download URL in page text (external domain, ends with .epub)
_DOWNLOAD_URL_RE = re.compile(r'https?://(?!annas-archive)[^\s"<>]+\.epub[^\s"<>]*', re.IGNORECASE)


async def _fetch_page_headless(url: str, wait_selector: str | None = None) -> str:
    """Fetch a page using a headless browser (for search — no DDoS-Guard)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = await context.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            logger.info("Landed on: %s (status %s)", page.url, resp.status if resp else "?")
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    pass
            await page.wait_for_timeout(2000)
            return await page.content()
        finally:
            await browser.close()


async def _get_persistent_context(playwright) -> BrowserContext:
    """Get a persistent browser context (visible window, keeps DDoS-Guard cookies)."""
    return await playwright.chromium.launch_persistent_context(
        user_data_dir=BROWSER_DATA_DIR,
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
        accept_downloads=True,
        locale="en-US",
    )


def _extract_md5(href: str) -> str | None:
    match = re.search(r'/md5/([a-f0-9]{32})', href, re.IGNORECASE)
    return match.group(1).lower() if match else None


def _extract_info_from_link(item) -> dict:
    info: dict = {}

    for h3 in item.select("h3"):
        text = h3.get_text(strip=True)
        if text:
            info["title"] = text
            break

    if "title" not in info:
        for el in item.select("[class*='truncate']"):
            text = el.get_text(strip=True)
            if len(text) > 5:
                info["title"] = text
                break

    if "title" not in info:
        all_text = item.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in all_text.split("\n") if len(l.strip()) > 5]
        if lines:
            info["title"] = max(lines, key=len)

    author_icon = item.select_one("[class*='mdi--user-edit']")
    if author_icon:
        parent = author_icon.parent
        if parent:
            author = parent.get_text(strip=True)
            if author:
                info["author"] = author

    mono = item.select_one("[class*='font-mono']")
    if mono:
        fn = mono.get_text(strip=True)
        if fn:
            info["filename"] = fn

    full_text = item.get_text(" ", strip=True)
    size_match = re.search(r'(\d+[\.,]?\d*\s*[KMG]B)', full_text, re.IGNORECASE)
    if size_match:
        info["size"] = size_match.group(1)

    return info


async def search_books(query: str, language: str = "") -> list[dict]:
    """Search Anna's Archive for epub books. Returns up to 10 results."""
    params = {"q": query, "ext": "epub"}
    if language and language in LANGUAGE_MAP:
        params["lang"] = LANGUAGE_MAP[language]

    url = f"{ANNAS_ARCHIVE_URL}/search?{urlencode(params)}"

    try:
        html = await _fetch_page_headless(url, wait_selector=".js-aarecord-list-outer")
    except Exception as e:
        logger.error("Search request failed: %s", e)
        return []

    soup = BeautifulSoup(html, "html.parser")
    md5_map: dict[str, dict] = {}

    for item in soup.select(".js-aarecord-list-outer a[href^='/md5/']"):
        href = item.get("href", "")
        md5 = _extract_md5(href)
        if not md5:
            continue

        info = _extract_info_from_link(item)
        detail_url = f"{ANNAS_ARCHIVE_URL}{href}" if href.startswith("/") else href

        if md5 not in md5_map:
            md5_map[md5] = {"detail_url": detail_url}

        existing = md5_map[md5]
        for key in ("title", "author", "filename", "size"):
            if key not in existing and key in info:
                existing[key] = info[key]

    results = []
    for md5, data in md5_map.items():
        title = data.get("title", "")
        if not title:
            continue
        results.append({
            "title": title,
            "author": data.get("author", ""),
            "filename": data.get("filename", ""),
            "size": data.get("size", ""),
            "detail_url": data["detail_url"],
        })
        if len(results) >= 10:
            break

    logger.info("Found %d results for query '%s'", len(results), query)
    return results


async def download_book(detail_url: str, filepath: str) -> bool:
    """Resolve the mirror download link via browser, then download the file via httpx.

    Flow:
    1. Browser: detail page → slow_download → wait countdown → extract mirror URL
    2. httpx: download the epub from the external mirror (fast, no browser needed)

    Returns True if file was downloaded successfully.
    """
    # --- Phase 1: resolve mirror URL using browser (needed for DDoS-Guard) ---
    download_url = None
    try:
        async with async_playwright() as p:
            context = await _get_persistent_context(p)
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                # Step 1: detail page → find slow_download link
                await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                html = await page.content()

                soup = BeautifulSoup(html, "html.parser")
                slow_url = None
                for a_tag in soup.select("a[href*='/slow_download/']"):
                    href = a_tag.get("href", "")
                    slow_url = href if href.startswith("http") else f"{ANNAS_ARCHIVE_URL}{href}"
                    break

                if not slow_url:
                    logger.warning("No slow_download link found on detail page")
                    return False

                logger.info("Found slow_download URL: %s", slow_url)

                # Step 2: navigate to slow_download, wait for countdown to reveal mirror link
                await page.goto(slow_url, wait_until="domcontentloaded", timeout=30000)
                download_url = await _poll_for_download_link(page)

            finally:
                await context.close()

    except Exception as e:
        logger.error("Failed to resolve download URL: %s", e)
        return False

    if not download_url:
        logger.warning("Could not resolve download URL after waiting")
        return False

    logger.info("Resolved mirror URL: %s", download_url[:150])

    # --- Phase 2: download file from external mirror via httpx (fast) ---
    try:
        async with httpx.AsyncClient(
            headers=HTTP_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15, read=300, write=30, pool=15),
        ) as client:
            async with client.stream("GET", download_url) as resp:
                if resp.status_code != 200:
                    logger.error("Mirror download returned status %d", resp.status_code)
                    return False

                with open(filepath, "wb") as f:
                    async for chunk in resp.aiter_bytes(65536):
                        f.write(chunk)

        size = Path(filepath).stat().st_size
        if size < 1024:
            logger.error("Downloaded file too small (%d bytes)", size)
            Path(filepath).unlink()
            return False

        logger.info("Downloaded %s (%d bytes)", filepath, size)
        return True

    except Exception as e:
        logger.error("Mirror download failed: %s", e)
        if Path(filepath).exists():
            Path(filepath).unlink()
        return False


async def _poll_for_download_link(page, max_wait: int = POLL_MAX_WAIT) -> str | None:
    """Poll the slow_download page until the direct download link appears after countdown."""
    elapsed = 0

    while elapsed < max_wait:
        await page.wait_for_timeout(POLL_INTERVAL * 1000)
        elapsed += POLL_INTERVAL

        html = await page.content()

        # Method 1: find external mirror URL via regex in raw HTML
        match = _DOWNLOAD_URL_RE.search(html)
        if match:
            return match.group(0)

        # Method 2: find external <a href> pointing to a file mirror
        soup = BeautifulSoup(html, "html.parser")
        for a_tag in soup.select("a[href^='http']"):
            href = a_tag.get("href", "")
            if "annas-archive" in href:
                continue
            if ".epub" in href or "/d/" in href or "/dl/" in href or "get.php" in href:
                return href

        logger.debug("Waiting for download link... (%ds/%ds)", elapsed, max_wait)

    return None
