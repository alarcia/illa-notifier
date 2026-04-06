# Illa Notifier

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

Scrapes the [Cinemes Illa Carlemany](https://cinemesilla.com/) website every hour, spots new movies, and sends Telegram alerts. There's a public channel for everything and a bot for people who only care about specific genres or languages.

## 📢 The channel

[@cartelera_illa](https://t.me/cartelera_illa) — every new movie shows up here automatically. Poster, title, genre, available languages, and a link to buy tickets. Notifications are in English.

## 🤖 The bot

[@illa_notifier_bot](https://t.me/illa_notifier_bot) — the channel is noisy if you don't care about half the movies. The bot lets you pick what you actually want to hear about:

- 💬 **Language** — VOSE, Castellà, Català
- 🎭 **Genre** — Thriller, Comedia, Drama, Terror, Animació, Aventura

Set your filters, and you'll get a DM only when something matches. No filters, no messages.

> The bot currently speaks Spanish. English and Catalan localization is planned.

### Commands

| Command | What it does |
|---------|-------------|
| `/start` | Registers you and shows a welcome message with a quick link to set up alerts |
| `/alerts` | Opens a keyboard with toggle buttons for each language and genre |

The keyboard has header buttons (Language / Genre) that select or deselect an entire category at once. Each individual filter shows a ✅ when active.

## ⚙️ How it works

The scraper fetches the full movie catalog and session data from cinemesilla.com using `BeautifulSoup`. It parses a Vue component that holds all the movie and showtime info as JSON attributes — titles, genres, posters, formats, rooms, times.

On each run it compares what it found against a SQLite database. New movie? Alert goes to the channel. Then it checks which bot users have filters matching that movie's genre or language and sends them a DM. A notification log prevents duplicate messages.

The bot and the scraper run in the same process — the bot listens for commands in a background thread while the scraper loops every hour. The whole thing runs in a Docker container.

## 🛠️ Tech

- **Python 3.12** with `beautifulsoup4` + `requests` for scraping
- **python-telegram-bot** for the bot and notifications
- **SQLite** for state (movies, sessions, users, filters, notification log)
- **Docker** for deployment

## 📂 Project structure

```
src/
├── main.py          # Entry point — scraping loop + bot thread
├── bot.py           # /start, /alerts, inline keyboard callbacks
├── notifier.py      # Sends alerts to the channel and DMs to subscribers
├── database.py      # All SQLite operations
└── test_notification.py
```

## ⚠️ Known limitations

- Genre and language options are hardcoded. If the cinema adds a new format or genre category, the bot keyboard won't show it until the code is updated.
- The scraper runs hourly. A movie could be up on the website for up to an hour before the alert goes out.
- Only tested on macOS and Linux (Docker). No Windows testing.

## 📝 License

MIT — see [LICENSE](LICENSE).
