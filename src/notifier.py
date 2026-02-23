import os
import json
from typing import Optional

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Notifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.token}/"

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
            print(f"Error sending Telegram notification: {e}")
            return False