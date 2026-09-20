# Concurrency & Process Model

This document explains the runtime concurrency architecture of **Illa Notifier**, covering how the synchronous scraping loop and the asynchronous Telegram bot coexist within a single OS process without deadlock, signal conflicts, or race conditions.

---

## 1. Process Topology

Rather than distributing workloads across multiple Docker containers or introducing external process managers (such as Celery, Redis, or Supervisord), the application executes inside a **single containerized Python process**:

```
[OS Process: python src/main.py]
│
├── [Main Thread (Synchronous)]
│   └── main()
│       └── while True:
│           ├── run_cycle(scraper, sync_service)
│           └── time.sleep(3600)
│
└── [Worker Thread (Asynchronous, daemon=True)]
    └── run_bot()
        └── asyncio Event Loop
            └── Application (python-telegram-bot)
                └── updater.start_polling(drop_pending_updates=True)
```

---

## 2. Overcoming Python Signal Constraints in Secondary Threads

### The Root Constraint
In standard `python-telegram-bot` applications, developers typically start the bot using:

```python
application.run_polling()
```

Under the hood, `run_polling()` invokes `asyncio.get_event_loop().add_signal_handler()` to register OS signal handlers (`SIGINT`, `SIGTERM`) for graceful teardown. In Python, however, **signal handlers can only be attached to the main interpreter thread**. Calling `run_polling()` inside a secondary thread immediately crashes the process with:

```text
ValueError: signal only works in main thread of the main interpreter
```

### The Architectural Solution
To run the bot in a background thread while the main thread manages the hourly scraping schedule, `src/bot.py` bypasses `run_polling()` and controls the underlying asynchronous primitives directly:

```python
async def _run_bot_async(app: Application) -> None:
    async with app:
        # Start polling directly without registering OS signal handlers
        await app.updater.start_polling(drop_pending_updates=True)
        await app.start()
        logger.info("Bot ready and polling for updates")
        
        # Keep the event loop alive indefinitely until process shutdown
        await asyncio.Event().wait()

def run_bot() -> None:
    config = BotConfig.from_env()
    app = build_application(config)
    asyncio.run(_run_bot_async(app))
```

### Critical Mechanisms:
1. **`drop_pending_updates=True`**: When the container restarts or redeploys after downtime, any queued interactions sent while the bot was offline are purged, preventing flood loops or outdated callback processing.
2. **`asyncio.Event().wait()`**: Yields execution within the event loop without consuming CPU cycles, keeping the bot responsive to incoming updates.
3. **`daemon=True` Lifecycle**: Because `bot_thread` is marked as a daemon thread, when Docker terminates the container (`SIGTERM` received by the main thread), the Python runtime exits immediately without the worker thread blocking process termination.

---

## 3. Database Concurrency Across Threads

Both the main thread (during the hourly scrape) and the bot thread (whenever users interact with `/start`, `/alerts`, or `/email`) access the same SQLite database file (`notifier.db`).

SQLite is inherently thread-safe, but naive connection sharing across threads can produce runtime errors (`sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`) or lock contention failures (`sqlite3.OperationalError: database is locked`).

Illa Notifier implements three structural protections in `src/database.py`:

### 1. Connection-Per-Operation Pattern
Connections are strictly transient. Rather than maintaining a global connection object, each database method opens, uses, and closes its own connection via a context manager:

```python
def _get_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path, timeout=10.0)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

Because connections are isolated per function call, threads never share internal SQLite state structures.

### 2. WAL (Write-Ahead Logging) Mode
During initial startup (`_init_db`), WAL mode is permanently enabled:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

In standard rollback journal mode, writing locks the entire database, blocking all readers. In **WAL mode**:
- **Readers do not block writers**.
- **Writers do not block readers**.
A user actively configuring their alert preferences inside Telegram will never be stalled because the hourly scraper is currently reading the movie catalog.

### 3. Busy Timeout (Lock Queueing)
While WAL mode allows concurrent readers alongside a writer, SQLite permits **only one writer at any single instant**.

If a user saves their email at the exact millisecond the scraper commits newly discovered showtimes, lock contention occurs. `PRAGMA busy_timeout = 5000` instructs SQLite to sleep and retry for up to 5,000 milliseconds instead of immediately raising a lock error.

---

## 4. Resilience to Network Hiccups

The Telegram long-polling connection between the Raspberry Pi host and `api.telegram.org` is vulnerable to transient home internet disruptions.

Normally, connection drops trigger lengthy tracebacks from `httpx` or `telegram.ext.Updater`. A custom logging filter (`TelegramNetworkErrorFilter` in `src/main.py`) suppresses noise by intercepting `NetworkError` and `ConnectError` exceptions and re-emitting them as clean single-line `WARNING` logs.
