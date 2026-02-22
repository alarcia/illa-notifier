# Illa Notifier

A lightweight notification system that monitors Illa Carlemany cinema releases to dispatch automated email and Telegram alerts.

## 📢 **Join the channel**
All alerts are automatically published to the Telegram channel: [@cartelera_illa](https://t.me/cartelera_illa)

> 🤖 **Bot in Development**: A customizable Telegram bot is currently under development to allow personalized movie alerts!

## 🎯 Purpose

This project automates the tracking of new movie releases at the local cinema. With the help of this tool, the user can independently verify the currently available movies and receive notifications as soon as new titles are added to the billboard.

## ⚙️ How It Works

1. **Automated Web Scraping:** Uses `BeautifulSoup` to fetch the latest movie catalog directly from the [Cinemes Illa Carlemany](https://cinemesilla.com/) website. It extracts key information such as the movie title, genre, format, and poster URL.
2. **State Management & Diffing:** Maintains a local SQLite database of currently active movies. Each time the script runs, it compares the scraped data against the database to detect **newly added** movies, while archiving those that are no longer showing.
3. **Notification Dispatch (WIP):** Formats the newly detected releases and prepares them to be sent out via Telegram and Email using configured environment variables.
4. **Containerized Execution:** The entire process is completely isolated within a Docker container, designed to be run periodically (e.g., via cron) without polluting the host environment's Python dependencies.

## 🛠️ Technology Stack

- **Language:** Python 3.12+
- **Scraping:** `requests`, `BeautifulSoup` (`beautifulsoup4`)
- **Database:** SQLite (built-in)
- **Deployment:** Docker

## 📂 Project Structure

- `src/main.py`: The entry point that orchestrates web scraping, data parsing, and database synchronisation.
- `src/database.py`: Encapsulates database operations, providing a clean interface for querying and updating movie states.
- `requirements.txt`: Lightweight list of external Python dependencies.
- `Dockerfile`: Instructions ensuring a lightweight, reproducible runtime environment.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
