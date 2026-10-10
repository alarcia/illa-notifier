"""
Sends a single test Telegram notification with a hardcoded movie.
Run from the project root:
    python src/test_notification.py
"""
import sys

from dotenv import load_dotenv

sys.path.insert(0, "src")
from notifier import Notifier
from scraper import CinemaScraper


def main() -> None:
    load_dotenv()
    notifier = Notifier()

    print("Fetching billboard using CinemaScraper...")
    scraper = CinemaScraper()
    billboard = scraper.get_billboard()

    if billboard.movies:
        movie = billboard.movies[0]
        sessions = billboard.sessions_by_movie.get(movie.movie_id, [])
        format_type = ", ".join(sorted({s.format_name for s in sessions})) or "CASTELLÀ"
        title = movie.title
        genre = movie.genre
        full_poster_url = movie.poster_url
        ticket_url = movie.ticket_url
    else:
        print("No live movies fetched, using fallback test movie...")
        title = "ALWAYS LALISA"
        genre = "Concert"
        format_type = "VOSE"
        full_poster_url = "https://media-illa.totalsoft.es/posters/alwayslalisa.jpg"
        ticket_url = "https://cinemesilla.com/pelicula/always-lalisa"

    print(f"Title      : {title}")
    print(f"Genre      : {genre}")
    print(f"Format     : {format_type}")
    print(f"Poster URL : {full_poster_url}")
    print(f"Ticket URL : {ticket_url}")
    print("Sending test notification...")

    success = notifier.send_movie_alert(title, genre, format_type, full_poster_url, ticket_url)
    if success:
        print("✅ Notification sent successfully.")
    else:
        print("❌ Failed to send notification. Check your TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.")


if __name__ == "__main__":
    main()
