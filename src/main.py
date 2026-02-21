import requests
from bs4 import BeautifulSoup
import json
import html
from database import Database
from notifier import Notifier

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
            
            poster_filename = movie.get('Cartel', '')
            full_poster_url = f"{base_poster_url}{poster_filename}" if poster_filename else None

            # Check if it's new BEFORE updating the DB
            if db.is_new_movie(movie_id):
                print(f"[*] NEW MOVIE DETECTED: {title}")
                # Send Telegram Notification
                notifier.send_movie_alert(title, genre, format_type, full_poster_url)
                new_movies_count += 1
            
            # Update or add to DB
            db.update_or_add_movie(movie_id, title, genre, format_type, full_poster_url)

        db.delete_inactive_movies()
        print(f"\nProcessing finished. {new_movies_count} notifications sent.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()