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

    def test_upsert_session_updates_movie_id_on_conflict(self) -> None:
        self.db.update_or_add_movie(13422, "LA BOLA NEGRA", "Drama", None)
        s1 = Session(
            id="40273", movie_id=13422, format_id=1, format_name="CASTELLÀ",
            room_id=4, room_name="Sala 04", showtime="2026-09-25 17:30",
            show_date="25/09/2026", show_time="17:30"
        )
        self.db.upsert_session(s1)
        self.assertEqual(self.db.get_movie_formats(13422), ["CASTELLÀ"])
        self.assertEqual(self.db.get_movie_formats(13423), [])

        # Re-upsert same session ID with new movie_id
        self.db.update_or_add_movie(13423, "LA BOLA NEGRA", "Drama", None)
        s2 = Session(
            id="40273", movie_id=13423, format_id=1, format_name="CASTELLÀ",
            room_id=4, room_name="Sala 04", showtime="2026-09-25 17:30",
            show_date="25/09/2026", show_time="17:30"
        )
        self.db.upsert_session(s2)
        self.assertEqual(self.db.get_movie_formats(13423), ["CASTELLÀ"])

    def test_movie_id_change_does_not_duplicate_alerts(self) -> None:
        from models import BillboardData

        # Pass 1: Movie arrives with ID 13422 and format CASTELLÀ
        m1 = ScrapedMovie(
            movie_id=13422, title="LA BOLA NEGRA", genre="Drama",
            cinema_id="10", cinema_name="Cinemes", poster_url=None,
            ticket_url="https://example.com/13422"
        )
        s1 = Session(
            id="40273", movie_id=13422, format_id=1, format_name="CASTELLÀ",
            room_id=4, room_name="Sala 04", showtime="2026-09-25 17:30",
            show_date="25/09/2026", show_time="17:30"
        )
        b1 = BillboardData(movies=[m1], sessions_by_movie={13422: [s1]})
        res1 = self.sync_service.sync(b1)
        self.assertEqual(res1.new_movies_count, 1)
        self.assertEqual(len(self.notifier.alerts_sent), 1)

        # Pass 2: Cinema changes ID to 13423, reuses session 40273
        self.notifier.alerts_sent.clear()
        m2 = ScrapedMovie(
            movie_id=13423, title="LA BOLA NEGRA", genre="Drama",
            cinema_id="10", cinema_name="Cinemes", poster_url=None,
            ticket_url="https://example.com/13423"
        )
        s2 = Session(
            id="40273", movie_id=13423, format_id=1, format_name="CASTELLÀ",
            room_id=4, room_name="Sala 04", showtime="2026-09-25 17:30",
            show_date="25/09/2026", show_time="17:30"
        )
        b2 = BillboardData(movies=[m2], sessions_by_movie={13423: [s2]})
        res2 = self.sync_service.sync(b2)
        self.assertEqual(res2.new_movies_count, 0)
        self.assertEqual(res2.new_formats_count, 0)
        self.assertEqual(len(self.notifier.alerts_sent), 0)

        # Pass 3: Next hour check
        res3 = self.sync_service.sync(b2)
        self.assertEqual(res3.new_movies_count, 0)
        self.assertEqual(res3.new_formats_count, 0)
        self.assertEqual(len(self.notifier.alerts_sent), 0)

        # Pass 4: Genuine new format arrives (VOSE)
        s3 = Session(
            id="40274", movie_id=13423, format_id=2, format_name="VOSE",
            room_id=4, room_name="Sala 04", showtime="2026-09-25 20:00",
            show_date="25/09/2026", show_time="20:00"
        )
        b3 = BillboardData(movies=[m2], sessions_by_movie={13423: [s2, s3]})
        res4 = self.sync_service.sync(b3)
        self.assertEqual(res4.new_movies_count, 0)
        self.assertEqual(res4.new_formats_count, 1)
        self.assertEqual(len(self.notifier.alerts_sent), 1)

    def test_subscriber_not_spammed_when_movie_id_changes(self) -> None:
        from models import BillboardData, TelegramUser

        # Register user and subscribe to CASTELLÀ
        user = TelegramUser(telegram_id=12345, first_name="Test", username="testuser")
        self.db.upsert_user(user)
        self.db.set_all_filters(12345, "format_type", ["CASTELLÀ"])

        m1 = ScrapedMovie(
            movie_id=13422, title="LA BOLA NEGRA", genre="Drama",
            cinema_id="10", cinema_name="Cinemes", poster_url=None,
            ticket_url="https://example.com/13422"
        )
        s1 = Session(
            id="40273", movie_id=13422, format_id=1, format_name="CASTELLÀ",
            room_id=4, room_name="Sala 04", showtime="2026-09-25 17:30",
            show_date="25/09/2026", show_time="17:30"
        )
        b1 = BillboardData(movies=[m1], sessions_by_movie={13422: [s1]})
        res1 = self.sync_service.sync(b1)
        self.assertEqual(res1.dms_sent, 1)

        # Cinema reassigns ID to 13423
        self.notifier.dms_sent.clear()
        m2 = ScrapedMovie(
            movie_id=13423, title="LA BOLA NEGRA", genre="Drama",
            cinema_id="10", cinema_name="Cinemes", poster_url=None,
            ticket_url="https://example.com/13423"
        )
        s2 = Session(
            id="40273", movie_id=13423, format_id=1, format_name="CASTELLÀ",
            room_id=4, room_name="Sala 04", showtime="2026-09-25 17:30",
            show_date="25/09/2026", show_time="17:30"
        )
        b2 = BillboardData(movies=[m2], sessions_by_movie={13423: [s2]})
        res2 = self.sync_service.sync(b2)
        self.assertEqual(res2.dms_sent, 0)
        self.assertEqual(len(self.notifier.dms_sent), 0)


if __name__ == "__main__":
    unittest.main()
