import sqlite3

class Database:
    def __init__(self, db_path="movies.db"):
        self.db_path = db_path
        self._create_tables()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        with self._get_connection() as conn:
            # Added poster_url column
            conn.execute("""
                CREATE TABLE IF NOT EXISTS movies (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    genre TEXT,
                    format TEXT,
                    poster_url TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
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