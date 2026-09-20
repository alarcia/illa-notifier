from __future__ import annotations

import logging
import threading
import time

from bot import run_bot
from database import Database
from notifier import Notifier
from scraper import CinemaScraper
from sync_service import CatalogSyncService

CHECK_INTERVAL_SECONDS = 3600


class TelegramNetworkErrorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "telegram.ext.Updater" and record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            if exc_type and ("NetworkError" in exc_type.__name__ or "ConnectError" in exc_type.__name__):
                record.exc_info = None
                record.msg = f"Network issue while polling: {exc_value}"
                record.args = ()
                record.levelname = "WARNING"
                record.levelno = logging.WARNING
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").addFilter(TelegramNetworkErrorFilter())
logger = logging.getLogger("illa_notifier.main")


def run_cycle(scraper: CinemaScraper, sync_service: CatalogSyncService) -> None:
    """Execute a single scraping, sync, and notification pass."""
    try:
        billboard = scraper.get_billboard()
        if not billboard.movies:
            logger.warning("No movies found in billboard data.")
            return

        sync_service.sync(billboard)
    except Exception as e:
        logger.exception("An error occurred during sync cycle: %s", e)


def main() -> None:
    logger.info("Initializing illa-notifier services...")
    db = Database()
    notifier = Notifier()
    scraper = CinemaScraper()
    sync_service = CatalogSyncService(db=db, notifier=notifier)

    # Start the Telegram bot listener in a background daemon thread
    bot_thread = threading.Thread(target=run_bot, name="telegram-bot", daemon=True)
    bot_thread.start()
    logger.info("Background telegram bot thread started.")

    while True:
        run_cycle(scraper, sync_service)
        logger.info("Waiting %d seconds for next check...", CHECK_INTERVAL_SECONDS)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()