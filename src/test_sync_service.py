from __future__ import annotations

import os
import unittest

from database import Database
from models import ScrapedMovie, Session
from scraper import CinemaScraper
from sync_service import CatalogSyncService


class DummyNotifier:
    def __init__(self) -> None:
        self.alerts_sent: list[str] = []
        self.dms_sent: list[tuple[int, str]] = []
        self.emails_sent: list[str] = []

    def send_movie_alert(self, title: str, genre: str, format_type: str, poster_url: str | None, ticket_url: str | None = None) -> bool:
        self.alerts_sent.append(title)
        return True

    def send_dm(self, telegram_id: int, title: str, genre: str, format_type: str, poster_url: str | None, ticket_url: str | None = None) -> bool:
        self.dms_sent.append((telegram_id, title))
        return True

    def send_email_notification(self, to_email: str, movies: list) -> bool:
        self.emails_sent.append(to_email)
        return True


class TestCatalogSyncService(unittest.TestCase):
    def setUp(self) -> None:
        self.test_db_path = "test_sync.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        self.db = Database(self.test_db_path)
        self.notifier = DummyNotifier()
        self.sync_service = CatalogSyncService(db=self.db, notifier=self.notifier)
        self.scraper = CinemaScraper()

    def tearDown(self) -> None:
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        for ext in ["-wal", "-shm"]:
            f = f"{self.test_db_path}{ext}"
            if os.path.exists(f):
                os.remove(f)

    def test_sync_first_time_and_idempotency(self) -> None:
        debug_html_path = os.path.join(os.path.dirname(__file__), "..", "debug.html")
        with open(debug_html_path, "r", encoding="utf-8") as f:
            billboard = self.scraper.parse_html(f.read())

        # First run: all movies should be detected as new
        first_result = self.sync_service.sync(billboard)
        self.assertEqual(first_result.new_movies_count, len(billboard.movies))
        self.assertEqual(len(self.notifier.alerts_sent), len(billboard.movies))

        # Second run with same billboard: 0 new movies, 0 new alerts
        self.notifier.alerts_sent.clear()
        second_result = self.sync_service.sync(billboard)
        self.assertEqual(second_result.new_movies_count, 0)
        self.assertEqual(second_result.new_formats_count, 0)
        self.assertEqual(len(self.notifier.alerts_sent), 0)


if __name__ == "__main__":
    unittest.main()
