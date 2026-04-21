# Illa Notifier

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![Resend](https://img.shields.io/badge/Resend-Email-000000?logo=resend&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

Scrapes the [Cinemes Illa Carlemany](https://cinemesilla.com/) website every hour, spots new movies, and sends alerts via Telegram and email. There's a public channel for everything, a bot for people who only care about specific genres or languages, and optional email notifications.

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
| `/start` | Registers you and shows a welcome message with quick links to set up alerts and email |
| `/alerts` | Opens a keyboard with toggle buttons for each language and genre |
| `/email` | Configure email notifications — add, change, disable, or remove your email |
| `*` | Any unrecognized message or command automatically shows an error and the main menu |

The alerts keyboard has header buttons (Language / Genre) that select or deselect an entire category at once. Each individual filter shows a ✅ when active.

## 📧 Email alerts

Don't want to check Telegram? The bot can also send you movie alerts by email. Use `/email` or tap the 📧 button after `/start` to set it up.

- Emails are sent via [Resend](https://resend.com/) from `cine@mail.alarcia.dev`
- When multiple new movies are detected in the same scraping cycle, they're **batched into a single email** — no inbox spam
- The email includes posters, genres, languages, and direct ticket links
- You can disable or remove your email anytime from the bot without losing your Telegram alerts

## ⚙️ How it works

The scraper fetches the full movie catalog and session data from cinemesilla.com using `BeautifulSoup`. It parses a Vue component that holds all the movie and showtime info as JSON attributes — titles, genres, posters, formats, rooms, times.

On each run it compares what it found against a SQLite database. New movie? Alert goes to the channel. Then it checks which bot users have filters matching that movie's genre or language and sends them a DM. After the full scan, all new movies are grouped by email subscriber and sent as a single batched email via Resend. A notification log (with channel tracking) prevents duplicate messages across both Telegram and email.

The bot and the scraper run in the same process — the bot listens for commands in a background thread while the scraper loops every hour. The whole thing runs in a Docker container.

## 🛠️ Tech

- **Python 3.12** with `beautifulsoup4` + `requests` for scraping
- **python-telegram-bot** for the bot and Telegram notifications
- **Resend** for transactional email notifications
- **SQLite** for state (movies, sessions, users, filters, notification log)
- **Docker** for deployment

## 📂 Project structure

```
src/
├── main.py          # Entry point — scraping loop + bot thread
├── bot.py           # /start, /alerts, /email, inline keyboard callbacks
├── notifier.py      # Sends alerts via Telegram (channel + DMs) and email (Resend)
├── database.py      # All SQLite operations
└── test_notification.py
```

## ⚠️ Known limitations

- Genre and language options are hardcoded. If the cinema adds a new format or genre category, the bot keyboard won't show it until the code is updated.
- The scraper runs hourly. A movie could be up on the website for up to an hour before the alert goes out.
- Only tested on macOS and Linux (Docker). No Windows testing.

## 📝 License

MIT — see [LICENSE](LICENSE).
