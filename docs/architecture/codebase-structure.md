# Codebase Structure & Component Boundaries

This document describes the organization of the repository, the technical boundaries between modules, and the design rules determining where specific concerns reside ("where everything goes").

---

## 1. Directory Tree Overview

```
illa-notifier/
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions deployment pipeline (self-hosted runner)
├── docs/                       # Technical architecture & operational documentation
│   ├── architecture/           # Deep-dives into subsystems, concurrency, pipeline, schema
│   ├── decisions/              # Architectural Decision Records (ADRs)
│   ├── operational-considerations.md # Gotchas, limits, and runtime realities
│   └── README.md               # Documentation hub and architecture map
├── src/                        # Application source code
│   ├── __init__.py
│   ├── bot.py                  # Inbound user interaction: Telegram bot commands & callbacks
│   ├── database.py             # Data access layer: SQLite client, schema & migrations
│   ├── main.py                 # Application entry point: thread initialization & scraping loop
│   ├── models.py               # Domain entities: immutable dataclasses
│   ├── notifier.py             # Outbound communication: Telegram API & Resend email client
│   ├── scraper.py              # Ingestion: HTTP client & Vue SSR JSON parser
│   ├── sync_service.py         # Domain orchestration: reconciliation & notification triggers
│   ├── test_notification.py    # Manual verification script for Telegram alerts
│   ├── test_scraper.py         # Unit tests for HTML/JSON extraction against debug fixture
│   └── test_sync_service.py    # Unit tests for catalog state reconciliation & idempotency
├── Dockerfile                  # Container definition (Python 3.12-slim)
├── docker-compose.yml          # Container orchestration, volume mapping & log rotation
├── debug.html                  # Live HTML fixture of cinemesilla.com used by tests
├── debug-new.html              # Incremental HTML fixture for testing change detection
├── requirements.txt            # Python dependencies
└── roadmap.md                  # High-level feature roadmap
```

---

## 2. Module Responsibilities & Architectural Boundaries

A critical aspect of maintaining this system is preserving the clean separation of concerns between its layers:

### `src/models.py` (Domain Layer)
- **What belongs here**: Pure data structures representing the problem domain (`ScrapedMovie`, `Session`, `BillboardData`, `TelegramUser`, `SyncResult`).
- **Design rules**: All classes use `@dataclass(frozen=True)`. They must be strictly immutable and free of side effects, database calls, or network calls.

### `src/scraper.py` (Ingestion Layer)
- **What belongs here**: Network fetching from `cinemesilla.com`, parsing `<cinemaindexpage>` Vue component attributes, deserializing JSON data, and building clean `BillboardData` models.
- **Design rules**:
  - The parser (`parse_html`) is a pure function: given an HTML string, it produces `BillboardData`. It has no knowledge of SQLite or Telegram.
  - The fetcher (`fetch_html`) encapsulates HTTP headers and exponential retry adapters (`HTTPAdapter`).
  - The scraper never decides whether a movie is "new" or sends alerts.

### `src/database.py` (Persistence Layer)
- **What belongs here**: Direct SQLite operations, table definitions, index creation, programmatic migrations (`_run_migrations`), and parameterized SQL queries.
- **Design rules**:
  - Encapsulates all SQL logic. No SQL statements should ever appear in `sync_service.py` or `bot.py`.
  - Every method creates and closes its own connection (`with self._get_connection() as conn:`). Connections are never stored as instance state across threads.
  - Enforces `PRAGMA busy_timeout = 5000` and `foreign_keys = ON`.

### `src/sync_service.py` (Application / Domain Logic Layer)
- **What belongs here**: Orchestrating the reconciliation between the freshly scraped `BillboardData` and the database state.
- **Design rules**:
  - Coordinates `Database` and `Notifier`.
  - Decides when a movie is brand new vs when an existing movie has gained new language/screening formats.
  - Filters subscribers against preferences and triggers alerts.
  - Gathers newly detected movies into an in-memory batch for single-digest email generation.

### `src/notifier.py` (Outbound Communication Gateway)
- **What belongs here**: Delivering messages to external APIs (Telegram Bot API and Resend Email API).
- **Design rules**:
  - Implements formatting: Markdown captions for Telegram, responsive dark-mode HTML cards for email.
  - Implements network fault tolerance (retries and logging).
  - Tolerates missing optional credentials: if `RESEND_API_KEY` is not set, email notifications are skipped cleanly without crashing.

### `src/bot.py` (Inbound Presentation Layer)
- **What belongs here**: User-facing Telegram bot handlers (`/start`, `/alerts`, `/email`), conversation states, and inline keyboard UI rendering.
- **Design rules**:
  - Handles the asynchronous event loop of `python-telegram-bot`.
  - Interacts exclusively with `Database` to persist user profiles and preference filters.
  - Does not participate in the scraping loop or notification dispatch.

### `src/main.py` (Composition Root & Runtime Entry Point)
- **What belongs here**: Instantiating singleton dependencies (`Database`, `Notifier`, `CinemaScraper`, `CatalogSyncService`), spawning the background bot daemon thread, and executing the hourly scraping `while True` loop.
- **Design rules**:
  - Configures global logging and exception filtering (`TelegramNetworkErrorFilter`).
  - Contains no business logic.
