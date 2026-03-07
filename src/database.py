import os
import sqlite3
from dataclasses import dataclass

@dataclass(frozen=True)
class TelegramUser:
    telegram_id: int
    first_name: str
    username: str | None


class Database:
    def __init__(self, db_path: str = os.environ.get("DB_PATH", "notifier.db")) -> None:
        self.db_path = db_path
        self._create_tables()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS movies (
                    id         INTEGER PRIMARY KEY,
                    title      TEXT    NOT NULL,
                    genre      TEXT,
                    format     TEXT,
                    poster_url TEXT,
                    is_active  INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

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

    def reset_active_status(self):
        with self._get_connection() as conn:
            conn.execute("UPDATE movies SET is_active = 0")

    def is_new_movie(self, movie_id):
        query = "SELECT 1 FROM movies WHERE id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (movie_id,))
            return cursor.fetchone() is None

    def update_or_add_movie(self, movie_id, title, genre, format, poster_url):
        """Adds or updates a movie including its poster URL."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO movies (id, title, genre, format, poster_url, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET 
                    is_active = 1,
                    poster_url = excluded.poster_url
            """, (movie_id, title, genre, format, poster_url))

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

    def get_matching_subscribers(self, movie_id: int, format_type: str, genre: str) -> list[int]:
        """Return telegram_ids of users whose filters match the given movie attributes.

        A user matches if they have at least one filter that matches either the
        movie's format_type OR genre.  Users who have already been notified about
        this movie (present in notification_log) are excluded.
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT DISTINCT sf.telegram_id
                FROM subscription_filters sf
                WHERE (
                    (sf.filter_type = 'format_type' AND sf.filter_value = ?)
                    OR
                    (sf.filter_type = 'genre' AND sf.filter_value = ?)
                )
                AND sf.telegram_id NOT IN (
                    SELECT nl.telegram_id FROM notification_log nl WHERE nl.movie_id = ?
                )
            """, (format_type, genre, movie_id)).fetchall()
            return [row[0] for row in rows]

    def log_notification(self, telegram_id: int, movie_id: int) -> None:
        """Record that a personal notification was sent (idempotency guard)."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO notification_log (telegram_id, movie_id) VALUES (?, ?)",
                (telegram_id, movie_id),
            )