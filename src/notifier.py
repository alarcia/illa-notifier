import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests
import resend
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


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

    def send_movie_alert(
        self,
        title: str,
        genre: str,
        format_type: str,
        poster_url: Optional[str],
        ticket_url: Optional[str] = None,
    ) -> bool:
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
        
        # If we have a poster URL, we send a photo. Otherwise, just text.
        if poster_url:
            endpoint = f"{self.api_url}sendPhoto"
            payload = {
                "chat_id": self.chat_id,
                "photo": poster_url,
                "caption": caption,
                "parse_mode": "Markdown",
            }
        else:
            endpoint = f"{self.api_url}sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": caption,
                "parse_mode": "Markdown",
            }

        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            response = requests.post(endpoint, data=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            self._logger.error("Error sending Telegram notification: %s", e)
            return False

    def send_dm(
        self,
        telegram_id: int,
        title: str,
        genre: str,
        format_type: str,
        poster_url: Optional[str],
        ticket_url: Optional[str] = None,
    ) -> bool:
        """Send a personal movie alert to a specific user via DM."""
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

        if poster_url:
            endpoint = f"{self.api_url}sendPhoto"
            payload: dict = {
                "chat_id": telegram_id,
                "photo": poster_url,
                "caption": caption,
                "parse_mode": "Markdown",
            }
        else:
            endpoint = f"{self.api_url}sendMessage"
            payload = {
                "chat_id": telegram_id,
                "text": caption,
                "parse_mode": "Markdown",
            }

        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            response = requests.post(endpoint, data=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            self._logger.error("Error sending DM to %s: %s", telegram_id, e)
            return False

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