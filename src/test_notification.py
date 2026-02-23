"""
Sends a single test Telegram notification with a hardcoded movie.
Run from the project root:
    python src/test_notification.py
"""
import html
import json
import sys
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.path.insert(0, "src")
from notifier import Notifier


# ---------------------------------------------------------------------------
# Hardcoded movie data — GREENLAND 2 (ID 13030, real data from the website)
# ---------------------------------------------------------------------------
MOVIE = {
    "ID_Espectaculo": 13030,
    "Titulo": "GREENLAND 2",
    "NombreGenero": "Thriller",
    "NombreFormato": "CASTELLÀ",
    "Cartel": "greenland2.jpg",
    "ID_Centro": 10,
    "CinemaName": "Cinemes illa Carlemany",
}

BASE_URL = "https://cinemesilla.com/"


def fetch_poster_base_url() -> str:
    """Fetches the poster base URL from the live website, same as main.py."""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    response = requests.get(BASE_URL, headers=headers, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    vue_component = soup.find("cinemaindexpage")
    if not vue_component:
        raise RuntimeError("Could not find <cinemaindexpage> component — website structure may have changed.")
    return json.loads(html.unescape(vue_component.get(":postersurl", '""')))


def main() -> None:
    load_dotenv()
    notifier = Notifier()

    print("Fetching poster base URL from website...")
    base_poster_url = fetch_poster_base_url()
    print(f"Poster base URL: {base_poster_url}")

    title = MOVIE["Titulo"]
    genre = MOVIE["NombreGenero"]
    format_type = MOVIE["NombreFormato"]
    movie_id = MOVIE["ID_Espectaculo"]
    cinema_id = MOVIE["ID_Centro"]
    cinema_name = MOVIE["CinemaName"]
    poster_filename = MOVIE["Cartel"]

    full_poster_url = f"{base_poster_url}{poster_filename}" if poster_filename else None
    ticket_url = (
        f"https://cinemesilla.com/FilmTheaterPage"
        f"/{movie_id}"
        f"/{quote(title)}"
        f"/{cinema_id}"
        f"/{quote(cinema_name)}"
    )

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
