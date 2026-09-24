from __future__ import annotations

import logging

from database import Database
from models import BillboardData, SyncResult
from notifier import MovieData, Notifier

logger = logging.getLogger("illa_notifier.sync")


class CatalogSyncService:
    """Synchronizes scraped billboard data with the database and dispatches notifications."""

    def __init__(self, db: Database, notifier: Notifier) -> None:
        self.db = db
        self.notifier = notifier

    def sync(self, billboard: BillboardData) -> SyncResult:
        """Run the full synchronization pipeline: detection, alerts, and persistence."""
        self.db.reset_active_status()

        new_movies_count = 0
        new_formats_count = 0
        dms_sent = 0
        emails_sent = 0
        new_movies_for_email: list[tuple[MovieData, list[str]]] = []

        for movie in billboard.movies:
            movie_id = movie.movie_id
            title = movie.title
            genre = movie.genre
            full_poster_url = movie.poster_url
            ticket_url = movie.ticket_url

            movie_sessions = billboard.sessions_by_movie.get(movie_id, [])
            formats = sorted({s.format_name for s in movie_sessions}) or ["Unknown"]
            format_display = ", ".join(formats)

            is_new = self.db.is_new_movie(movie_id, title)
            existing_formats = self.db.get_movie_formats(movie_id, title) if not is_new else []

            # Ensure movie record exists before logging notifications (FK constraint)
            self.db.update_or_add_movie(movie_id, title, genre, full_poster_url)

            if is_new:
                # Guard against channel duplicates
                unalerted_formats = [f for f in formats if not self.db.has_channel_alert(title, f)]
                if unalerted_formats or not formats:
                    logger.info("NEW MOVIE DETECTED: %s (%s)", title, format_display)
                    self.notifier.send_movie_alert(title, genre, format_display, full_poster_url, ticket_url)
                    for fmt in formats:
                        self.db.log_channel_alert(movie_id, title, fmt, "new_movie")
                    new_movies_count += 1

                    subscribers = self.db.get_matching_subscribers(movie_id, formats, genre, title)
                    for tg_id in subscribers:
                        if self.notifier.send_dm(tg_id, title, genre, format_display, full_poster_url, ticket_url):
                            self.db.log_notification(tg_id, movie_id)
                            dms_sent += 1
                            logger.info("DM sent to subscriber %s for new movie %s", tg_id, title)
                        else:
                            logger.warning("DM failed for subscriber %s for movie %s", tg_id, title)

                    movie_data = MovieData(
                        movie_id=movie_id,
                        title=title,
                        genre=genre,
                        format_type=format_display,
                        poster_url=full_poster_url,
                        ticket_url=ticket_url,
                    )
                    new_movies_for_email.append((movie_data, formats))
            else:
                unseen_formats = sorted(set(formats) - set(existing_formats))
                new_formats = [f for f in unseen_formats if not self.db.has_channel_alert(title, f)]
                if new_formats:
                    new_format_display = ", ".join(new_formats)
                    logger.info("NEW FORMAT(S) FOR EXISTING MOVIE: %s (%s)", title, new_format_display)
                    self.notifier.send_movie_alert(title, genre, new_format_display, full_poster_url, ticket_url)
                    for fmt in new_formats:
                        self.db.log_channel_alert(movie_id, title, fmt, "new_format")
                    new_formats_count += 1

                    subscribers = self.db.get_matching_subscribers(movie_id, new_formats, genre, title)
                    for tg_id in subscribers:
                        if self.notifier.send_dm(tg_id, title, genre, new_format_display, full_poster_url, ticket_url):
                            self.db.log_notification(tg_id, movie_id)
                            dms_sent += 1
                            logger.info("DM sent to subscriber %s for new format %s", tg_id, new_format_display)
                        else:
                            logger.warning("DM failed for subscriber %s for new format %s", tg_id, new_format_display)

                    movie_data = MovieData(
                        movie_id=movie_id,
                        title=title,
                        genre=genre,
                        format_type=new_format_display,
                        poster_url=full_poster_url,
                        ticket_url=ticket_url,
                    )
                    new_movies_for_email.append((movie_data, new_formats))

            for session in movie_sessions:
                self.db.upsert_session(session)

        # ── Batched email notifications ──────────────────────────────
        if new_movies_for_email:
            subscriber_movies: dict[tuple[int, str], list[MovieData]] = {}
            for movie_data, formats in new_movies_for_email:
                email_subs = self.db.get_email_subscribers(movie_data.movie_id, formats, movie_data.genre, movie_data.title)
                for tg_id, email_addr in email_subs:
                    subscriber_movies.setdefault((tg_id, email_addr), []).append(movie_data)

            for (tg_id, email_addr), movies_for_sub in subscriber_movies.items():
                if self.notifier.send_email_notification(email_addr, movies_for_sub):
                    for m in movies_for_sub:
                        self.db.log_email_notification(tg_id, m.movie_id)
                    emails_sent += 1
                    logger.info("Batched email (%d movies) sent to %s (user %s)", len(movies_for_sub), email_addr, tg_id)
                else:
                    logger.warning("Batched email failed for %s (user %s)", email_addr, tg_id)

        result = SyncResult(
            new_movies_count=new_movies_count,
            new_formats_count=new_formats_count,
            dms_sent=dms_sent,
            emails_sent=emails_sent,
        )
        logger.info(
            "Sync completed: %d new movies, %d new formats, %d DMs, %d emails sent.",
            result.new_movies_count,
            result.new_formats_count,
            result.dms_sent,
            result.emails_sent,
        )
        return result
