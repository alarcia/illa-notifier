import html
import json
import logging
import threading
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from bot import run_bot
from database import Database, Session
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("illa_notifier.main")

def main():
    db = Database()
    notifier = Notifier()
    url = "https://cinemesilla.com/" 
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    logger.info("Connecting to: %s", url)
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        vue_component = soup.find('cinemaindexpage')
        if not vue_component:
            logger.error("Component <cinemaindexpage> not found")
            return

        # Get base URL for posters, movies list, and full sessions
        base_poster_url = json.loads(html.unescape(vue_component.get(':postersurl', '""')))
        movies_list = json.loads(html.unescape(vue_component.get(':onlytitlesinfo', '[]')))
        sessions_list = json.loads(html.unescape(vue_component.get(':fullsessionsinfo', '[]')))

        # Build a dict of sessions grouped by movie_id for quick lookup
        sessions_by_movie: dict[int, list[dict]] = {}
        for raw_session in sessions_list:
            mid = raw_session.get('ID_Espectaculo')
            if mid is not None:
                sessions_by_movie.setdefault(mid, []).append(raw_session)

        db.reset_active_status()
        new_movies_count = 0

        for movie in movies_list:
            movie_id = movie.get('ID_Espectaculo')
            title = str(movie.get('Titulo', 'Unknown')).strip()
            genre = movie.get('NombreGenero', 'Unknown')
            cinema_id = movie.get('ID_Centro', '')
            cinema_name = movie.get('CinemaName', '')

            poster_filename = movie.get('Cartel', '')
            full_poster_url = f"{base_poster_url}{poster_filename}" if poster_filename else None

            # Build ticket purchase URL
            ticket_url = (
                f"https://cinemesilla.com/FilmTheaterPage"
                f"/{movie_id}"
                f"/{quote(title)}"
                f"/{cinema_id}"
                f"/{quote(cinema_name)}"
            )

            # Collect unique formats from sessions for this movie
            movie_sessions = sessions_by_movie.get(movie_id, [])
            formats = sorted({s.get('NombreFormato', 'Unknown') for s in movie_sessions}) or [movie.get('NombreFormato', 'Unknown')]
            format_display = ", ".join(formats)

            # Check if it's new BEFORE updating the DB
            if db.is_new_movie(movie_id):
                logger.info("NEW MOVIE DETECTED: %s (%s)", title, format_display)
                # Send global notification to the channel
                notifier.send_movie_alert(title, genre, format_display, full_poster_url, ticket_url)
                new_movies_count += 1

                # Send personal DMs to matching subscribers
                subscribers = db.get_matching_subscribers(movie_id, formats, genre)
                for tg_id in subscribers:
                    success = notifier.send_dm(tg_id, title, genre, format_display, full_poster_url, ticket_url)
                    if success:
                        db.log_notification(tg_id, movie_id)
                        logger.info("DM sent to subscriber %s", tg_id)
                    else:
                        logger.warning("DM failed for subscriber %s", tg_id)

                # Send email notifications to matching email subscribers
                email_subscribers = db.get_email_subscribers(movie_id, formats, genre)
                for tg_id, email_addr in email_subscribers:
                    success = notifier.send_email_notification(
                        email_addr, title, genre, format_display, full_poster_url, ticket_url,
                    )
                    if success:
                        db.log_email_notification(tg_id, movie_id)
                        logger.info("Email sent to %s (user %s)", email_addr, tg_id)
                    else:
                        logger.warning("Email failed for %s (user %s)", email_addr, tg_id)
            
            # Update or add movie to DB (without format — derived from sessions)
            db.update_or_add_movie(movie_id, title, genre, full_poster_url)

            # Upsert all sessions for this movie
            for raw_session in movie_sessions:
                session = Session(
                    id=str(raw_session.get('ID_Pase', '')),
                    movie_id=movie_id,
                    format_id=int(raw_session.get('ID_Formato', 0)),
                    format_name=raw_session.get('NombreFormato', 'Unknown'),
                    room_id=int(raw_session['ID_Sala']) if raw_session.get('ID_Sala') else None,
                    room_name=raw_session.get('NombreSala'),
                    showtime=raw_session.get('HoraReal', ''),
                    show_date=raw_session.get('diacompleto', ''),
                    show_time=raw_session.get('Hora', ''),
                )
                db.upsert_session(session)

        logger.info("Processing finished. %d channel notifications sent.", new_movies_count)

    except Exception as e:
        logger.exception("An error occurred: %s", e)

if __name__ == "__main__":
    # Start the bot listener (handles /start and future commands) in a
    # background daemon thread so it doesn't block the scraping loop.
    bot_thread = threading.Thread(target=run_bot, name="telegram-bot", daemon=True)
    bot_thread.start()

    while True:
        try:
            main()
        except Exception as e:
            logger.exception("Critical error in loop: %s", e)

        # 3600 seconds = 1 hour
        logger.info("Waiting 1 hour for the next check...")
        time.sleep(3600)