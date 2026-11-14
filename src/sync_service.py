from __future__ import annotations

import logging

from database import Database
from models import BillboardData, SyncResult
from notifier import MovieData, NotificationError, Notifier

logger = logging.getLogger("illa_notifier.sync")

# Wait before each retry after a failed Telegram attempt. Exhausted -> status 'failed'.
RETRY_DELAYS_SECONDS = [60, 5 * 60, 30 * 60, 24 * 3600]


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
        emails_sent = 0
        new_movies_for_email: list[tuple[MovieData, list[str]]] = []

        for movie in billboard.movies:
            movie_id = movie.movie_id
            title = movie.title
            genre = movie.genre

            movie_sessions = billboard.sessions_by_movie.get(movie_id, [])
            formats = sorted({s.format_name for s in movie_sessions}) or ["Unknown"]

            is_new = self.db.is_new_movie(movie_id, title)
            existing_formats = self.db.get_movie_formats(movie_id, title) if not is_new else []

            # Ensure movie record exists before logging notifications (FK constraint)
            self.db.update_or_add_movie(movie_id, title, genre, movie.poster_url)

            if is_new:
                alert_formats = [f for f in formats if not self.db.has_channel_alert(title, f)]
                alert_type = "new_movie"
                if alert_formats:
                    alert_formats = formats  # announce the movie with all its formats
                    logger.info("NEW MOVIE DETECTED: %s (%s)", title, ", ".join(formats))
                    new_movies_count += 1
            else:
                unseen_formats = sorted(set(formats) - set(existing_formats))
                alert_formats = [f for f in unseen_formats if not self.db.has_channel_alert(title, f)]
                alert_type = "new_format"
                if alert_formats:
                    logger.info("NEW FORMAT(S) FOR EXISTING MOVIE: %s (%s)", title, ", ".join(alert_formats))
                    new_formats_count += 1

            if alert_formats:
                format_display = ", ".join(alert_formats)
                common = (movie_id, title, genre, format_display, movie.poster_url, movie.ticket_url)
                # channel_alerts = "already queued" dedupe guard; delivery state lives in telegram_outbox
                self.db.enqueue_telegram("channel", self.notifier.chat_id, *common)
                for fmt in alert_formats:
                    self.db.log_channel_alert(movie_id, title, fmt, alert_type)
                for tg_id in self.db.get_matching_subscribers(movie_id, alert_formats, genre, title):
                    self.db.enqueue_telegram("dm", tg_id, *common)

                movie_data = MovieData(
                    movie_id=movie_id,
                    title=title,
                    genre=genre,
                    format_type=format_display,
                    poster_url=self.notifier.resolve_poster(movie.poster_url),
                    ticket_url=movie.ticket_url,
                )
                new_movies_for_email.append((movie_data, alert_formats))

            for session in movie_sessions:
                self.db.upsert_session(session)

        dms_sent = self.process_outbox()

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

    def process_outbox(self) -> int:
        """Attempt every due Telegram delivery. Returns the number of DMs delivered."""
        dms_sent = 0
        for row in self.db.get_due_outbox():
            attempt = row["attempts"] + 1
            # Placeholder poster only after a first failure (poster may be a transient CDN error)
            args = (row["title"], row["genre"], row["format_display"], row["poster_url"], row["ticket_url"])
            try:
                if row["kind"] == "channel":
                    self.notifier.send_movie_alert(*args, allow_placeholder=attempt > 1)
                else:
                    self.notifier.send_dm(int(row["chat_id"]), *args, allow_placeholder=attempt > 1)
            except NotificationError as e:
                delay = RETRY_DELAYS_SECONDS[attempt - 1] if attempt <= len(RETRY_DELAYS_SECONDS) else None
                self.db.mark_outbox_failed_attempt(row["id"], str(e), delay)
                if delay is None:
                    logger.error("Telegram %s for %s to %s FAILED permanently after %d attempts: %s",
                                 row["kind"], row["title"], row["chat_id"], attempt, e)
                else:
                    logger.warning("Telegram %s for %s to %s failed (attempt %d), retrying in %ds: %s",
                                   row["kind"], row["title"], row["chat_id"], attempt, delay, e)
                continue

            self.db.mark_outbox_sent(row["id"])
            if row["kind"] == "dm":
                self.db.log_notification(int(row["chat_id"]), row["movie_id"])
                dms_sent += 1
            logger.info("Telegram %s sent for %s (%s) to %s", row["kind"], row["title"], row["format_display"], row["chat_id"])
        return dms_sent

    def log_undelivered(self) -> None:
        """Loudly report alerts whose retries are exhausted (called every scan cycle)."""
        for row in self.db.get_failed_outbox():
            logger.error(
                "⚠️ UNDELIVERED Telegram %s: %s (%s) to %s — %d attempts since %s, last error: %s",
                row["kind"], row["title"], row["format_display"], row["chat_id"],
                row["attempts"], row["created_at"], row["last_error"],
            )
