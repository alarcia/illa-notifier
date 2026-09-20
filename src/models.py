from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TelegramUser:
    telegram_id: int
    first_name: str
    username: str | None


@dataclass(frozen=True)
class Session:
    id: str              # ID_Pase
    movie_id: int        # ID_Espectaculo
    format_id: int       # ID_Formato
    format_name: str     # NombreFormato (CASTELLÀ, VOSE, VO...)
    room_id: int | None  # ID_Sala
    room_name: str | None  # NombreSala
    showtime: str        # HoraReal (full datetime)
    show_date: str       # diacompleto (30/03/2026)
    show_time: str       # Hora (19:00)


@dataclass(frozen=True)
class ScrapedMovie:
    movie_id: int
    title: str
    genre: str
    cinema_id: str
    cinema_name: str
    poster_url: str | None
    ticket_url: str


@dataclass(frozen=True)
class BillboardData:
    movies: list[ScrapedMovie] = field(default_factory=list)
    sessions_by_movie: dict[int, list[Session]] = field(default_factory=dict)


@dataclass(frozen=True)
class SyncResult:
    new_movies_count: int = 0
    new_formats_count: int = 0
    dms_sent: int = 0
    emails_sent: int = 0
