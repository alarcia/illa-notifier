import logging
import os
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger("illa_notifier.database")


@dataclass(frozen=True)
class TelegramUser:
    telegram_id: int
    first_name: str
    username: str | None


@dataclass(frozen=True)
class Session:
    id: str              # ID_Pase
    movie_id: int        # ID_Espectaculo
    format_id: int       # ID_Formato
    format_name: str     # NombreFormato (CASTELLÀ, VOSE, VO...)
    room_id: int | None  # ID_Sala
    room_name: str | None  # NombreSala
    showtime: str        # HoraReal (full datetime)
    show_date: str       # diacompleto (30/03/2026)
    show_time: str       # Hora (19:00)


class Database:
    def __init__(self, db_path: str = os.environ.get("DB_PATH", "notifier.db")) -> None:
        self.db_path = db_path
        self._create_tables()
        self._run_migrations()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS movies (
                    id         INTEGER PRIMARY KEY,
                    title      TEXT    NOT NULL,
                    genre      TEXT,
                    poster_url TEXT,
                    is_active  INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id          TEXT    PRIMARY KEY,
                    movie_id    INTEGER NOT NULL REFERENCES movies(id),
                    format_id   INTEGER NOT NULL,
                    format_name TEXT    NOT NULL,
                    room_id     INTEGER,
                    room_name   TEXT,
                    showtime    TEXT    NOT NULL,
                    show_date   TEXT    NOT NULL,
                    show_time   TEXT    NOT NULL,
                    is_active   INTEGER DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_movie
                    ON sessions (movie_id);

                CREATE INDEX IF NOT EXISTS idx_sessions_movie_format
                    ON sessions (movie_id, format_name);

                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    first_name  TEXT    NOT NULL,
                    username    TEXT,
                    email       TEXT,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS subscription_filters (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL
                                REFERENCES users (telegram_id) ON DELETE CASCADE,
                    filter_type  TEXT NOT NULL,
                    filter_value TEXT NOT NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (telegram_id, filter_type, filter_value)
                );

                CREATE INDEX IF NOT EXISTS idx_sf_type_value
                    ON subscription_filters (filter_type, filter_value);

                CREATE TABLE IF NOT EXISTS notification_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL
                                REFERENCES users (telegram_id) ON DELETE CASCADE,
                    movie_id    INTEGER NOT NULL
                                REFERENCES movies (id) ON DELETE CASCADE,
                    sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (telegram_id, movie_id)
                );

                CREATE INDEX IF NOT EXISTS idx_nl_movie
                    ON notification_log (movie_id);
            """)

    def _run_migrations(self) -> None:
        """Run one-time schema migrations. Each migration checks before applying."""
        with self._get_connection() as conn:
            # Migration: drop 'format' column from movies (superseded by sessions table)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(movies)").fetchall()]
            if "format" in columns:
                conn.execute("ALTER TABLE movies DROP COLUMN format")
                logger.info("Migration: dropped 'format' column from movies table")

            # Migration: add email_notifications column to users
            user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
            if "email_notifications" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN email_notifications INTEGER DEFAULT 0")
                logger.info("Migration: added 'email_notifications' column to users table")

            # Migration: add channel column to notification_log
            nl_columns = [row[1] for row in conn.execute("PRAGMA table_info(notification_log)").fetchall()]
            if "channel" not in nl_columns:
                conn.executescript("""
                    ALTER TABLE notification_log RENAME TO notification_log_old;

                    CREATE TABLE notification_log (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER NOT NULL
                                    REFERENCES users (telegram_id) ON DELETE CASCADE,
                        movie_id    INTEGER NOT NULL
                                    REFERENCES movies (id) ON DELETE CASCADE,
                        channel     TEXT    NOT NULL DEFAULT 'telegram',
                        sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (telegram_id, movie_id, channel)
                    );

                    INSERT INTO notification_log (id, telegram_id, movie_id, channel, sent_at)
                    SELECT id, telegram_id, movie_id, 'telegram', sent_at
                    FROM notification_log_old;

                    DROP TABLE notification_log_old;

                    CREATE INDEX IF NOT EXISTS idx_nl_movie
                        ON notification_log (movie_id);
                """)
                logger.info("Migration: added 'channel' column to notification_log table")

    def reset_active_status(self) -> None:
        """Mark all movies and sessions as inactive before a fresh scrape."""
        with self._get_connection() as conn:
            conn.execute("UPDATE movies SET is_active = 0")
            conn.execute("UPDATE sessions SET is_active = 0")

    def is_new_movie(self, movie_id: int) -> bool:
        """Return True if the movie has never been seen before."""
        query = "SELECT 1 FROM movies WHERE id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (movie_id,))
            return cursor.fetchone() is None

    def update_or_add_movie(self, movie_id: int, title: str, genre: str, poster_url: str | None) -> None:
        """Adds or updates a movie (format is now derived from sessions)."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO movies (id, title, genre, poster_url, is_active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    is_active = 1,
                    poster_url = excluded.poster_url
            """, (movie_id, title, genre, poster_url))

    # ── Session methods ──────────────────────────────────────────────────

    def upsert_session(self, session: Session) -> None:
        """Insert or update a screening session."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO sessions (id, movie_id, format_id, format_name,
                                      room_id, room_name, showtime,
                                      show_date, show_time, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    is_active   = 1,
                    format_name = excluded.format_name,
                    room_name   = excluded.room_name,
                    showtime    = excluded.showtime,
                    show_date   = excluded.show_date,
                    show_time   = excluded.show_time
            """, (
                session.id, session.movie_id, session.format_id,
                session.format_name, session.room_id, session.room_name,
                session.showtime, session.show_date, session.show_time,
            ))

    def get_movie_formats(self, movie_id: int) -> list[str]:
        """Return the distinct format names for a movie from its active sessions."""
        with self._get_connection() as conn:
            # Use sessions regardless of their is_active flag so that we can
            # compare against the previously-known formats even after
            # `reset_active_status()` is called at the start of a scrape.
            rows = conn.execute(
                "SELECT DISTINCT format_name FROM sessions WHERE movie_id = ?",
                (movie_id,),
            ).fetchall()
            return [row[0] for row in rows]

    def get_movie_sessions(self, movie_id: int) -> list[Session]:
        """Return all active sessions for a movie (for future bot features)."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT id, movie_id, format_id, format_name,
                       room_id, room_name, showtime, show_date, show_time
                FROM sessions
                WHERE movie_id = ? AND is_active = 1
                ORDER BY showtime
            """, (movie_id,)).fetchall()
            return [
                Session(
                    id=row[0], movie_id=row[1], format_id=row[2],
                    format_name=row[3], room_id=row[4], room_name=row[5],
                    showtime=row[6], show_date=row[7], show_time=row[8],
                )
                for row in rows
            ]

    def delete_inactive_movies(self):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM movies WHERE is_active = 0")

    def upsert_user(self, user: TelegramUser) -> None:
        """Insert the user or update first_name/username on subsequent /start calls."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO users (telegram_id, first_name, username)
                VALUES (:telegram_id, :first_name, :username)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    username   = excluded.username,
                    updated_at = CURRENT_TIMESTAMP
            """, {
                "telegram_id": user.telegram_id,
                "first_name":  user.first_name,
                "username":    user.username,
            })

    def get_user_filters(self, telegram_id: int) -> set[tuple[str, str]]:
        """Return the active subscription filters for a user as a set of (filter_type, filter_value) tuples."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT filter_type, filter_value FROM subscription_filters WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchall()
            return {(row[0], row[1]) for row in rows}

    def toggle_filter(self, telegram_id: int, filter_type: str, filter_value: str) -> bool:
        """Toggle a subscription filter. Returns True if the filter is now active, False if removed."""
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM subscription_filters WHERE telegram_id = ? AND filter_type = ? AND filter_value = ?",
                (telegram_id, filter_type, filter_value),
            ).fetchone()

            if existing:
                conn.execute(
                    "DELETE FROM subscription_filters WHERE telegram_id = ? AND filter_type = ? AND filter_value = ?",
                    (telegram_id, filter_type, filter_value),
                )
                return False

            conn.execute(
                "INSERT INTO subscription_filters (telegram_id, filter_type, filter_value) VALUES (?, ?, ?)",
                (telegram_id, filter_type, filter_value),
            )
            return True

    def set_all_filters(self, telegram_id: int, filter_type: str, values: list[str]) -> None:
        """Activate all given filter values for a filter type (idempotent)."""
        with self._get_connection() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO subscription_filters (telegram_id, filter_type, filter_value) VALUES (?, ?, ?)",
                [(telegram_id, filter_type, v) for v in values],
            )

    def remove_all_filters(self, telegram_id: int, filter_type: str) -> None:
        """Remove all filter values for a given filter type."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM subscription_filters WHERE telegram_id = ? AND filter_type = ?",
                (telegram_id, filter_type),
            )

    def get_matching_subscribers(self, movie_id: int, formats: list[str], genre: str) -> list[int]:
        """Return telegram_ids of users whose filters match the given movie attributes.

        A user matches if they have at least one filter that matches either any of
        the movie's formats OR genre.  Users who have already been notified about
        this movie (present in notification_log) are excluded.
        """
        if not formats:
            return []

        placeholders = ", ".join("?" for _ in formats)
        params: list[str | int] = list(formats) + [genre, movie_id]

        with self._get_connection() as conn:
            # Only exclude users who have already been notified via Telegram
            # for this movie. Users who were emailed (or otherwise notified)
            # should still receive Telegram DMs if they match the new format.
            rows = conn.execute(f"""
                SELECT DISTINCT sf.telegram_id
                FROM subscription_filters sf
                WHERE (
                    (sf.filter_type = 'format_type' AND sf.filter_value IN ({placeholders}))
                    OR
                    (sf.filter_type = 'genre' AND sf.filter_value = ?)
                )
                AND sf.telegram_id NOT IN (
                    SELECT nl.telegram_id FROM notification_log nl WHERE nl.movie_id = ? AND nl.channel = 'telegram'
                )
            """, params).fetchall()
            return [row[0] for row in rows]

    def log_notification(self, telegram_id: int, movie_id: int) -> None:
        """Record that a Telegram DM notification was sent (idempotency guard)."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO notification_log (telegram_id, movie_id, channel) VALUES (?, ?, 'telegram')",
                (telegram_id, movie_id),
            )

    # ── Email-related methods ────────────────────────────────────────────

    def update_user_email(self, telegram_id: int, email: str, enabled: bool = True) -> None:
        """Save the user's email and set the email_notifications flag."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users
                SET email = ?, email_notifications = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
            """, (email, int(enabled), telegram_id))

    def get_user_email_status(self, telegram_id: int) -> tuple[str | None, bool]:
        """Return (email, email_notifications_enabled) for a user."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT email, email_notifications FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            if row is None:
                return None, False
            return row[0], bool(row[1])

    def disable_email_notifications(self, telegram_id: int) -> None:
        """Disable email notifications for a user (keeps the email address)."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET email_notifications = 0, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (telegram_id,),
            )

    def remove_user_email(self, telegram_id: int) -> None:
        """Remove email and disable email notifications."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET email = NULL, email_notifications = 0, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (telegram_id,),
            )

    def get_email_subscribers(self, movie_id: int, formats: list[str], genre: str) -> list[tuple[int, str]]:
        """Return (telegram_id, email) of users with email active, matching filters,
        and not yet notified by email for this movie."""
        if not formats:
            return []

        placeholders = ", ".join("?" for _ in formats)
        params: list[str | int] = list(formats) + [genre, movie_id]

        with self._get_connection() as conn:
            rows = conn.execute(f"""
                SELECT DISTINCT sf.telegram_id, u.email
                FROM subscription_filters sf
                JOIN users u ON u.telegram_id = sf.telegram_id
                WHERE u.email IS NOT NULL
                  AND u.email_notifications = 1
                  AND (
                      (sf.filter_type = 'format_type' AND sf.filter_value IN ({placeholders}))
                      OR
                      (sf.filter_type = 'genre' AND sf.filter_value = ?)
                  )
                  AND sf.telegram_id NOT IN (
                      SELECT nl.telegram_id FROM notification_log nl
                      WHERE nl.movie_id = ? AND nl.channel = 'email'
                  )
            """, params).fetchall()
            return [(row[0], row[1]) for row in rows]

    def log_email_notification(self, telegram_id: int, movie_id: int) -> None:
        """Record that an email notification was sent (idempotency guard)."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO notification_log (telegram_id, movie_id, channel) VALUES (?, ?, 'email')",
                (telegram_id, movie_id),
            )