from __future__ import annotations

import html
import json
import logging
import re
import zlib
from datetime import datetime
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models import BillboardData, ScrapedMovie, Session

logger = logging.getLogger("illa_notifier.scraper")

DEFAULT_URL = "https://cinemesilla.com/"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

FORMAT_ID_MAP: dict[str, int] = {
    "CASTELLÀ": 1,
    "VOSE": 2,
    "VO": 3,
    "CATALÀ": 4,
}


def _clean_mojibake(text: str | None) -> str:
    """Fix double-encoded UTF-8 strings common in web CMS exports."""
    if not text:
        return ""
    if any(m in text for m in ("Ã", "Â")):
        try:
            return text.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return text


def _generate_movie_id(slug_or_title: str) -> int:
    """Generate a stable, positive 31-bit integer movie ID from slug or title."""
    return zlib.crc32(slug_or_title.strip().lower().encode("utf-8")) & 0x7FFFFFFF


def _parse_iso_datetime(iso_str: str) -> tuple[str, str]:
    """Parse ISO datetime string into (DD/MM/YYYY, HH:MM)."""
    if not iso_str:
        return "", ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")
    except Exception:
        return iso_str, ""


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

        # 1. Primary parser: Schema.org ItemList (Astro SSR new site)
        billboard = self._parse_json_ld(soup)
        if billboard.movies:
            return billboard

        # 2. Legacy fallback: <cinemaindexpage> Vue component (old site)
        legacy_billboard = self._parse_legacy(soup)
        if legacy_billboard.movies:
            return legacy_billboard

        logger.error("No billboard data found in HTML (neither Schema.org JSON-LD nor legacy Vue component)")
        return BillboardData()

    def _parse_json_ld(self, soup: BeautifulSoup) -> BillboardData:
        """Parse Schema.org ItemList JSON-LD and enrich with HTML session tags."""
        item_list: dict | None = None
        for s in soup.find_all("script", type="application/ld+json"):
            if not s.string:
                continue
            try:
                data = json.loads(s.string)
                if isinstance(data, dict) and data.get("@type") == "ItemList":
                    item_list = data
                    break
            except Exception:
                continue

        if not item_list or not item_list.get("itemListElement"):
            return BillboardData()

        # Extract session tags (language / room) from HTML cards
        session_tags: dict[str, str] = {}
        session_rooms: dict[str, str] = {}
        cartelera = soup.find("section", id="cartelera")
        if cartelera:
            for a in cartelera.find_all("a", href=re.compile(r"/sesion/")):
                href = str(a.get("href", ""))
                sid = href.split("/sesion/")[-1].strip("/")
                if not sid:
                    continue

                etiquetas = [_clean_mojibake(e.get_text(strip=True)) for e in a.find_all("span", class_="etiqueta")]
                lang_tag: str | None = None
                room_tag: str | None = None

                for et in etiquetas:
                    et_lower = et.lower()
                    if "sala" in et_lower:
                        room_tag = et
                    elif et_lower in ("original", "vo", "vose"):
                        lang_tag = "VOSE"
                    elif "cat" in et_lower:
                        lang_tag = "CATALÀ"
                    elif "cast" in et_lower or "esp" in et_lower:
                        lang_tag = "CASTELLÀ"

                session_tags[sid] = lang_tag or "CASTELLÀ"
                if room_tag:
                    session_rooms[sid] = room_tag

        movies: list[ScrapedMovie] = []
        sessions_by_movie: dict[int, list[Session]] = {}

        for li in item_list.get("itemListElement", []):
            m = li.get("item", {})
            title = _clean_mojibake(m.get("name", "Unknown").strip())
            url = m.get("url", "")
            slug = url.split("/pelicula/")[-1].strip("/") if "/pelicula/" in url else title.lower()
            movie_id = _generate_movie_id(slug)

            genres_raw = m.get("genre", [])
            if isinstance(genres_raw, list):
                genre = ", ".join([_clean_mojibake(g) for g in genres_raw])
            else:
                genre = _clean_mojibake(str(genres_raw or "Unknown"))

            poster_url = m.get("image")
            ticket_url = url or f"https://cinemesilla.com/pelicula/{slug}"

            movies.append(
                ScrapedMovie(
                    movie_id=movie_id,
                    title=title,
                    genre=genre,
                    cinema_id="illa",
                    cinema_name="Cinemes illa Carlemany",
                    poster_url=poster_url,
                    ticket_url=ticket_url,
                )
            )

            movie_sessions: list[Session] = []
            for raw_s in m.get("subjectOf", []):
                s_url = raw_s.get("url", "")
                sid = s_url.split("/sesion/")[-1].strip("/") if "/sesion/" in s_url else ""
                if not sid:
                    continue

                format_name = session_tags.get(sid)
                if not format_name:
                    in_lang = raw_s.get("inLanguage")
                    if in_lang == "ca":
                        format_name = "CATALÀ"
                    elif in_lang == "es":
                        format_name = "CASTELLÀ"
                    elif any(o in genre.lower() for o in ("òpera", "opera", "ballet", "concert")):
                        format_name = "VOSE"
                    else:
                        format_name = "CASTELLÀ"

                format_id = FORMAT_ID_MAP.get(format_name, 1)

                room_name = session_rooms.get(sid)
                room_id: int | None = None
                if room_name:
                    match = re.search(r"\d+", room_name)
                    if match:
                        room_id = int(match.group())

                start_date_str = raw_s.get("startDate", "")
                show_date, show_time = _parse_iso_datetime(start_date_str)

                movie_sessions.append(
                    Session(
                        id=sid,
                        movie_id=movie_id,
                        format_id=format_id,
                        format_name=format_name,
                        room_id=room_id,
                        room_name=room_name,
                        showtime=start_date_str,
                        show_date=show_date,
                        show_time=show_time,
                    )
                )

            sessions_by_movie[movie_id] = movie_sessions

        logger.info(
            "Parsed %d movies and %d total sessions from Schema.org JSON-LD",
            len(movies),
            sum(len(s) for s in sessions_by_movie.values()),
        )
        return BillboardData(movies=movies, sessions_by_movie=sessions_by_movie)

    def _parse_legacy(self, soup: BeautifulSoup) -> BillboardData:
        """Legacy parser for the old <cinemaindexpage> Vue component."""
        vue_component = soup.find("cinemaindexpage")
        if not vue_component:
            return BillboardData()

        base_poster_url = json.loads(html.unescape(vue_component.get(":postersurl", '""')))
        movies_list = json.loads(html.unescape(vue_component.get(":onlytitlesinfo", "[]")))
        sessions_list = json.loads(html.unescape(vue_component.get(":fullsessionsinfo", "[]")))

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
            "Parsed %d movies and %d total sessions from legacy Vue component",
            len(movies),
            sum(len(s) for s in sessions_by_movie.values()),
        )
        return BillboardData(movies=movies, sessions_by_movie=sessions_by_movie)

    def get_billboard(self) -> BillboardData:
        """Fetch and parse current billboard data."""
        html_text = self.fetch_html()
        return self.parse_html(html_text)
