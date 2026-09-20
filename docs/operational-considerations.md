# Operational Considerations, Caveats & Scaling

This document covers the operational realities, runtime gotchas, edge cases, failure modes, and architectural boundaries to keep in mind when understanding, maintaining, or evolving **Illa Notifier**.

---

## 1. Critical Runtime Caveats ("Things to Consider")

### 1. SQLite Single-Writer Lock Contention
* **The Reality**: Although WAL mode allows simultaneous readers and writers, SQLite strictly enforces **a single active writer at any instant**.
* **The Risk**: If the hourly scraper is committing a large batch of movie sessions while multiple users are concurrently interacting with the bot (toggling filters or configuring email), write locks will collide.
* **How It Is Handled**: Every connection is initialized with `PRAGMA busy_timeout = 5000`. Instead of failing immediately with `OperationalError: database is locked`, SQLite sleeps and retries for up to 5 seconds.
* **Boundary**: If database write volume grows to where transactions take multiple seconds, write contention will become an issue, indicating the need to migrate to a client-server DBMS like PostgreSQL.

### 2. Telegram Bot API Rate Limits
* **Global Rate Limit**: The Telegram Bot API limits broadcasts to **30 messages per second** across all chats.
* **Per-Chat Rate Limit**: A bot cannot send more than **1 message per second** to a specific individual chat.
* **Current Delivery Model**: `sync_service.py` sends DMs sequentially in a synchronous loop. For small subscriber bases (< 500 users), this takes seconds and stays safely within rate limits.
* **Boundary**: If the subscriber base reaches thousands, sequential sending would stall the main loop for minutes, and sending too rapidly in parallel without a rate limiter would trigger HTTP 429 (`Too Many Requests`). Scaling beyond this threshold requires an asynchronous token-bucket queue (e.g., `aiolimiter`).

### 3. Telegram Polling in Secondary Threads
* **The Constraint**: Signal handlers (`SIGINT`, `SIGTERM`) in Python can only be registered on the main interpreter thread. Calling `Application.run_polling()` inside a worker thread crashes the application.
* **How It Is Handled**: `bot.py` starts polling using `await app.updater.start_polling()` directly and blocks with `await asyncio.Event().wait()`.
* **Important Implication**: Because the bot runs in a `daemon=True` thread, process shutdown is triggered by the main thread. If `main.py` crashes or exits, the bot thread is abruptly terminated.

### 4. Database File Backups with WAL Files
* **The Gotcha**: In WAL mode, SQLite writes new transactions to `notifier.db-wal` rather than immediately merging them into `notifier.db`.
* **The Risk**: Copying only `notifier.db` while the application is running will create a corrupted or incomplete backup.
* **Proper Backup Technique**:
  - Use SQLite's online vacuum command: `sqlite3 notifier.db "VACUUM INTO 'backup.db'"`
  - Or ensure the Docker volume mounts the entire directory (`/app/data`) so that `notifier.db`, `notifier.db-wal`, and `notifier.db-shm` are preserved together.

### 5. Website Structure Dependency
* **The Vulnerability**: Scraping relies on the cinema website rendering the `<cinemaindexpage>` Vue SSR component with `:onlytitlesinfo` and `:fullsessionsinfo` attributes.
* **Failure Mode**: If the cinema redesigns their frontend to load showtimes client-side via asynchronous `fetch()` after hydration, or modifies the Vue component name, `scraper.py` will not find the component and will log:
  ```text
  ERROR: Component <cinemaindexpage> not found in HTML
  ```
  The pipeline gracefully returns an empty `BillboardData()` without corrupting existing database records.

---

## 2. Deployment Architecture (Raspberry Pi Edge Host)

The production environment is hosted on a self-hosted Raspberry Pi connected via GitHub Actions:

```
[GitHub Repository]
       │
  (git push main)
       ▼
[GitHub Actions Workflow: deploy.yml]
       │
  (Runs on self-hosted runner on Raspberry Pi)
       ▼
[Raspberry Pi Host]
  ├── .env file created from secrets
  ├── Host directory: /app/data (mounted for SQLite persistence)
  └── docker compose up -d --build
```

### Key Environment Configuration
* **Timezone Mapping**: Mounted `/etc/localtime:ro` and `TZ: Europe/Madrid` in `docker-compose.yml` ensures that date comparisons and hourly schedules match local cinema time (Andorra / Central European Time).
* **Disk Wear Protection**:
  - `PRAGMA synchronous = NORMAL` prevents excessive `fsync` calls on SD/Flash storage.
  - Docker logging is strictly capped (`json-file` with `max-size: 10m` and `max-file: 3`) to prevent disk exhaustion.
* **Fault Recovery**: `restart: unless-stopped` ensures the container automatically recovers from Raspberry Pi reboots or unexpected power interruptions.

---

## 3. Scalability & System Evolution Path

The system is deliberately engineered to be simple, self-contained, and cheap to run. Here is how its capacity scales across growth milestones:

| Stage | User Base | Architectural Characteristic | Bottlenecks / Adjustments |
|---|---|---|---|
| **Current** | 1 – 500 subscribers | Single container, SQLite WAL, synchronous scraper loop, daemon bot thread. | Memory ~70 MB. Zero operational maintenance. Perfect fit. |
| **Intermediate** | 500 – 5,000 subscribers | Same container, SQLite WAL. | Sequential DM delivery becomes slow. Need to introduce an async rate limiter (`aiolimiter` capping outbound Telegram calls to 25 msgs/sec). |
| **High Scale** | > 5,000 subscribers | Split into two services: Scheduled Scraper Job + Webhook-based Telegram Bot. | SQLite write lock contention becomes a hazard. Migrate database to managed PostgreSQL; introduce Redis + Celery/ARQ task queues for notification fan-out. |
