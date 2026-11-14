from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
import resend
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

PLACEHOLDER_POSTER = Path(__file__).resolve().parent.parent / "assets" / "placeholder_poster.jpg"
POSTER_HOSTS = ("cdn.totalsoft.es", "media-illa.totalsoft.es")


class NotificationError(Exception):
    """A Telegram send failed; message is safe to log (no token)."""


@dataclass(frozen=True)
class MovieData:
    """Data needed to render a movie in an email notification."""
    movie_id: int
    title: str
    genre: str
    format_type: str
    poster_url: str | None
    ticket_url: str | None


class Notifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.token}/"
        self._logger = logging.getLogger("illa_notifier.notifier")

        # Resend email config
        self._resend_api_key = os.getenv("RESEND_API_KEY", "")
        self._email_from = os.getenv("EMAIL_FROM", "")
        if self._resend_api_key:
            resend.api_key = self._resend_api_key
        else:
            self._logger.warning("RESEND_API_KEY not set — email notifications disabled")

    def resolve_poster(self, poster_url: Optional[str]) -> Optional[str]:
        """Return a poster URL that actually serves an image, or None.

        The site serves posters from two mirrored hosts and swaps between them
        client-side (img onerror -> data-poster-fallback), so try both.
        """
        if not poster_url:
            return None
        candidates = [poster_url]
        for a, b in (POSTER_HOSTS, POSTER_HOSTS[::-1]):
            if f"//{a}/" in poster_url:
                candidates.append(poster_url.replace(f"//{a}/", f"//{b}/", 1))
        for url in candidates:
            try:
                r = requests.head(url, timeout=10, allow_redirects=True)
                if r.ok and r.headers.get("content-type", "").startswith("image/"):
                    if url != poster_url:
                        # Evidence for a possible CDN migration (cdn.totalsoft.es vs media-illa)
                        self._logger.info("Poster served from alternate host: %s (original 404: %s)", url, poster_url)
                    return url
            except requests.RequestException:
                pass
        self._logger.warning("Poster unavailable on all hosts: %s", poster_url)
        return None

    def _post(self, method: str, data: dict, files: Optional[dict] = None) -> None:
        try:
            response = requests.post(f"{self.api_url}{method}", data=data, files=files, timeout=30)
        except requests.RequestException as e:
            # str(e) contains the request URL, which embeds the bot token — never log it
            raise NotificationError(f"{method}: {type(e).__name__}") from None
        if not response.ok:
            raise NotificationError(f"{method}: {response.status_code} {response.text[:300]}")

    def _send(self, chat_id, caption: str, poster_url: Optional[str], reply_markup: Optional[dict], allow_placeholder: bool) -> None:
        """Send a photo alert. Raises NotificationError on failure.

        Uses the real poster when reachable. The placeholder is used when the movie has no
        poster, or when allow_placeholder is set (i.e. a previous attempt already failed).
        """
        base: dict = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
        if reply_markup:
            base["reply_markup"] = json.dumps(reply_markup)

        photo_url = self.resolve_poster(poster_url)
        if photo_url:
            try:
                return self._post("sendPhoto", {**base, "photo": photo_url})
            except NotificationError as e:
                if not allow_placeholder:
                    raise
                self._logger.warning("Real poster rejected for %s, using placeholder: %s", chat_id, e)
        elif poster_url and not allow_placeholder:
            raise NotificationError(f"poster unavailable: {poster_url}")

        with open(PLACEHOLDER_POSTER, "rb") as f:
            self._post("sendPhoto", base, files={"photo": f})

    def send_movie_alert(
        self,
        title: str,
        genre: str,
        format_type: str,
        poster_url: Optional[str],
        ticket_url: Optional[str] = None,
        allow_placeholder: bool = False,
    ) -> None:
        caption = (
            f"🎬 *NEW MOVIE DETECTED*\n\n"
            f"🍿 *Title:* {title}\n"
            f"🎭 *Genre:* {genre}\n"
            f"💬 *Language:* {format_type}\n"
        )

        reply_markup: Optional[dict] = None
        if ticket_url:
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🎟️ Get tickets", "url": ticket_url}]
                ]
            }
        
        self._send(self.chat_id, caption, poster_url, reply_markup, allow_placeholder)

    def send_dm(
        self,
        telegram_id: int,
        title: str,
        genre: str,
        format_type: str,
        poster_url: Optional[str],
        ticket_url: Optional[str] = None,
        allow_placeholder: bool = False,
    ) -> None:
        """Send a personal movie alert to a specific user via DM. Raises NotificationError."""
        caption = (
            f"🔔 *Nueva película que encaja con tus alertas*\n\n"
            f"🍿 *Título:* {title}\n"
            f"🎭 *Género:* {genre}\n"
            f"💬 *Idioma:* {format_type}\n"
        )

        reply_markup: Optional[dict] = None
        if ticket_url:
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🎟️ Comprar entradas", "url": ticket_url}]
                ]
            }

        self._send(telegram_id, caption, poster_url, reply_markup, allow_placeholder)

    # ── Email ────────────────────────────────────────────────────────────

    @staticmethod
    def _render_movie_card(movie: MovieData) -> str:
        """Render a single movie as an HTML card for the email body."""
        poster = (
            f'<img src="{movie.poster_url}" alt="{movie.title}" '
            f'style="max-width:280px;border-radius:10px;margin-bottom:12px;" /><br>'
            if movie.poster_url else ""
        )
        ticket = (
            f'<a href="{movie.ticket_url}" style="display:inline-block;padding:10px 20px;'
            f'background-color:#e50914;color:#ffffff;text-decoration:none;'
            f'border-radius:8px;font-weight:bold;font-size:14px;">'
            f'🎟️ Comprar entradas</a>'
            if movie.ticket_url else ""
        )
        return f"""\
<div style="background:#16213e;border-radius:12px;padding:16px;margin-bottom:16px;">
  {poster}
  <table style="width:100%;border-collapse:collapse;margin-bottom:10px;">
    <tr>
      <td style="padding:4px 0;color:#999;width:90px;">🍿 Título</td>
      <td style="padding:4px 0;font-weight:bold;">{movie.title}</td>
    </tr>
    <tr>
      <td style="padding:4px 0;color:#999;">🎭 Género</td>
      <td style="padding:4px 0;">{movie.genre}</td>
    </tr>
    <tr>
      <td style="padding:4px 0;color:#999;">💬 Idioma</td>
      <td style="padding:4px 0;">{movie.format_type}</td>
    </tr>
  </table>
  {ticket}
</div>"""

    def send_email_notification(self, to_email: str, movies: list[MovieData]) -> bool:
        """Send a single email with one or more movie alerts.

        Returns True if the email was sent successfully.
        """
        if not self._resend_api_key or not self._email_from:
            self._logger.warning("Email not configured — skipping email to %s", to_email)
            return False

        if not movies:
            return False

        # Subject adapts to single vs multiple movies
        if len(movies) == 1:
            subject = f"🎬 Nueva película: {movies[0].title}"
        else:
            subject = f"🎬 {len(movies)} nuevas películas en cartelera"

        cards_html = "\n".join(self._render_movie_card(m) for m in movies)

        heading = (
            "🎬 Nueva película en cartelera"
            if len(movies) == 1
            else f"🎬 {len(movies)} nuevas películas en cartelera"
        )

        html_body = f"""\
<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:480px;margin:0 auto;
            background:#1a1a2e;color:#eaeaea;padding:24px;border-radius:16px;">
  <h2 style="color:#e50914;margin-top:0;">{heading}</h2>
  {cards_html}
  <hr style="border:none;border-top:1px solid #333;margin:24px 0 12px;" />
  <p style="font-size:12px;color:#666;">
    Cinemes Illa Carlemany · Notificación automática<br>
    Puedes desactivar los emails desde el bot de Telegram.
  </p>
</div>"""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resend.Emails.send({
                    "from": self._email_from,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body,
                })
                titles = ", ".join(m.title for m in movies)
                self._logger.info("Email sent to %s with %d movies: %s", to_email, len(movies), titles)
                return True
            except Exception as e:
                is_last = attempt == max_retries - 1
                if is_last:
                    self._logger.error("Email to %s failed after %d attempts: %s", to_email, max_retries, e)
                    return False
                delay = min(1.0 * (2 ** attempt), 8.0)
                self._logger.warning("Email to %s failed (attempt %d/%d), retrying in %.0fs: %s",
                                     to_email, attempt + 1, max_retries, delay, e)
                time.sleep(delay)

        return False