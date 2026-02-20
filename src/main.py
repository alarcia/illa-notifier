import requests
from bs4 import BeautifulSoup
import json
import html
from database import Database

def main():
    db = Database()
    url = "https://cinemesilla.com/" 
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        vue_component = soup.find('cinemaindexpage')
        if not vue_component:
            return

        # Get base URL for posters and the movies JSON
        base_poster_url = json.loads(html.unescape(vue_component.get(':postersurl', '""')))
        movies_list = json.loads(html.unescape(vue_component.get(':onlytitlesinfo', '[]')))

        db.reset_active_status()
        new_movies = []

        for movie in movies_list:
            movie_id = movie.get('ID_Espectaculo')
            title = str(movie.get('Titulo', 'Unknown')).strip()
            genre = movie.get('NombreGenero', 'Unknown')
            format_type = movie.get('NombreFormato', 'Unknown')
            
            # Combine base URL + filename
            poster_filename = movie.get('Cartel', '')
            full_poster_url = f"{base_poster_url}{poster_filename}" if poster_filename else None

            if db.is_new_movie(movie_id):
                print(f"[*] NEW: {title}")
                new_movies.append({"title": title, "poster": full_poster_url})
            
            db.update_or_add_movie(movie_id, title, genre, format_type, full_poster_url)

        db.delete_inactive_movies()
        
        # This list 'new_movies' will be used in the next step for Telegram
        if new_movies:
            print(f"\nReady to notify {len(new_movies)} movies.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()