from __future__ import annotations

import html
import json
import logging
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models import BillboardData, ScrapedMovie, Session

logger = logging.getLogger("illa_notifier.scraper")

DEFAULT_URL = "https://cinemesilla.com/"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class CinemaScraper:
    """Client for fetching and parsing billboard data from Cinemes Illa Carlemany."""

    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = 20,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def fetch_html(self, url: str | None = None) -> str:
        """Fetch raw HTML from the target URL."""
        target_url = url or self.base_url
        logger.info("Fetching billboard HTML from: %s", target_url)
        response = self.session.get(target_url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def parse_html(self, html_text: str) -> BillboardData:
        """Pure parser: extract structured movie and session data from page HTML."""
        soup = BeautifulSoup(html_text, "html.parser")
        vue_component = soup.find("cinemaindexpage")

        if not vue_component:
            logger.error("Component <cinemaindexpage> not found in HTML")
            return BillboardData()

        base_poster_url = json.loads(html.unescape(vue_component.get(":postersurl", '""')))
        movies_list = json.loads(html.unescape(vue_component.get(":onlytitlesinfo", "[]")))
        sessions_list = json.loads(html.unescape(vue_component.get(":fullsessionsinfo", "[]")))

        # Group sessions by movie ID
        sessions_by_movie: dict[int, list[Session]] = {}
        for raw in sessions_list:
            mid = raw.get("ID_Espectaculo")
            if mid is None:
                continue
            session = Session(
                id=str(raw.get("ID_Pase", "")),
                movie_id=mid,
                format_id=int(raw.get("ID_Formato", 0)),
                format_name=raw.get("NombreFormato", "Unknown"),
                room_id=int(raw["ID_Sala"]) if raw.get("ID_Sala") else None,
                room_name=raw.get("NombreSala"),
                showtime=raw.get("HoraReal", ""),
                show_date=raw.get("diacompleto", ""),
                show_time=raw.get("Hora", ""),
            )
            sessions_by_movie.setdefault(mid, []).append(session)

        # Parse movies
        movies: list[ScrapedMovie] = []
        for raw in movies_list:
            movie_id = raw.get("ID_Espectaculo")
            if movie_id is None:
                continue

            title = str(raw.get("Titulo", "Unknown")).strip()
            genre = raw.get("NombreGenero", "Unknown")
            cinema_id = str(raw.get("ID_Centro", ""))
            cinema_name = raw.get("CinemaName", "")

            poster_filename = raw.get("Cartel", "")
            full_poster_url = f"{base_poster_url}{poster_filename}" if poster_filename else None

            ticket_url = (
                f"https://cinemesilla.com/FilmTheaterPage"
                f"/{movie_id}"
                f"/{quote(title)}"
                f"/{cinema_id}"
                f"/{quote(cinema_name)}"
            )

            movies.append(
                ScrapedMovie(
                    movie_id=movie_id,
                    title=title,
                    genre=genre,
                    cinema_id=cinema_id,
                    cinema_name=cinema_name,
                    poster_url=full_poster_url,
                    ticket_url=ticket_url,
                )
            )

        logger.info(
            "Parsed %d movies and %d total sessions from HTML",
            len(movies),
            sum(len(s) for s in sessions_by_movie.values()),
        )
        return BillboardData(movies=movies, sessions_by_movie=sessions_by_movie)

    def get_billboard(self) -> BillboardData:
        """Fetch and parse current billboard data."""
        html_text = self.fetch_html()
        return self.parse_html(html_text)
