import html
import json
import logging
import threading
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from bot import run_bot
from database import Database
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

def main():
    db = Database()
    notifier = Notifier()
    url = "https://cinemesilla.com/" 
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    print(f"Connecting to: {url}...")
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        vue_component = soup.find('cinemaindexpage')
        if not vue_component:
            print("Error: Component <cinemaindexpage> not found.")
            return

        # Get base URL for posters and the movies JSON
        base_poster_url = json.loads(html.unescape(vue_component.get(':postersurl', '""')))
        movies_list = json.loads(html.unescape(vue_component.get(':onlytitlesinfo', '[]')))

        db.reset_active_status()
        new_movies_count = 0

        for movie in movies_list:
            movie_id = movie.get('ID_Espectaculo')
            title = str(movie.get('Titulo', 'Unknown')).strip()
            genre = movie.get('NombreGenero', 'Unknown')
            format_type = movie.get('NombreFormato', 'Unknown')
            cinema_id = movie.get('ID_Centro', '')
            cinema_name = movie.get('CinemaName', '')

            poster_filename = movie.get('Cartel', '')
            full_poster_url = f"{base_poster_url}{poster_filename}" if poster_filename else None

            # Build ticket purchase URL
            # Pattern: /FilmTheaterPage/{id}/{title_encoded}/{cinema_id}/{cinema_name_encoded}
            ticket_url = (
                f"https://cinemesilla.com/FilmTheaterPage"
                f"/{movie_id}"
                f"/{quote(title)}"
                f"/{cinema_id}"
                f"/{quote(cinema_name)}"
            )

            # Check if it's new BEFORE updating the DB
            if db.is_new_movie(movie_id):
                print(f"[*] NEW MOVIE DETECTED: {title}")
                # Send Telegram Notification
                notifier.send_movie_alert(title, genre, format_type, full_poster_url, ticket_url)
                new_movies_count += 1
            
            # Update or add to DB
            db.update_or_add_movie(movie_id, title, genre, format_type, full_poster_url)

        print(f"\nProcessing finished. {new_movies_count} notifications sent.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Start the bot listener (handles /start and future commands) in a
    # background daemon thread so it doesn't block the scraping loop.
    bot_thread = threading.Thread(target=run_bot, name="telegram-bot", daemon=True)
    bot_thread.start()

    while True:
        try:
            main()
        except Exception as e:
            print(f"Critical error in loop: {e}")

        # 3600 seconds = 1 hour
        print("Waiting 1 hour for the next check...")
        time.sleep(3600)