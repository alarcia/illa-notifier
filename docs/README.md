# Illa Notifier Technical Documentation

**Illa Notifier** is an automated cinema monitoring and multi-channel notification engine built for *Cinemes Illa Carlemany* (Andorra). It continuously monitors the cinema's scheduled billboard, detects newly added movies or newly added screening formats (such as original-language VOSE sessions), and broadcasts alerts across a public Telegram channel, personalized direct messages, and batched email digests.

This documentation provides an in-depth, explanatory breakdown of how the application is designed, how its components interact, the technical decisions behind its implementation, and the operational characteristics to consider.

---

## 📚 Documentation Index

### 🏛️ Architecture & System Design
- [System Overview & Architecture](architecture/system-overview.md): C4 Context and Container views, component interactions, and external boundaries.
- [Codebase Structure & Component Responsibilities](architecture/codebase-structure.md): File-by-file organization, layout rules, and architectural boundaries ("where everything goes").
- [Concurrency & Process Model](architecture/concurrency-model.md): Detailed explanation of the dual-runtime single-process architecture (sync scraper loop + async Telegram bot thread) and signal handling constraints.
- [Data Ingestion & Notification Pipeline](architecture/data-pipeline.md): How the scraper extracts embedded Vue SSR attributes, reconciles state against SQLite, and dispatches multi-channel alerts.
- [Persistence & Schema Design](architecture/persistence-and-schema.md): Database architecture, entity relationships, WAL mode mechanics, self-contained migrations, and composite key idempotency.

### 📋 Architectural Decision Records (ADRs)
The [Decisions Log](decisions/README.md) details the architectural rationale, evaluated alternatives, and trade-offs for core design choices:
- [ADR 0001: Single-Process Multi-Threading vs Microservices](decisions/0001-single-process-multithreading.md)
- [ADR 0002: SQLite in WAL Mode for Edge Deployment](decisions/0002-sqlite-wal-for-edge-persistence.md)
- [ADR 0003: Extracting Vue SSR Attributes vs Headless Browser Automation](decisions/0003-scraping-vue-hydration-json.md)
- [ADR 0004: Multi-Channel Idempotency via Composite Unique Keys](decisions/0004-composite-deduplication-keys.md)
- [ADR 0005: Batched Email Digest via Resend API](decisions/0005-batched-email-resend.md)

### ⚠️ Operational Realities & Considerations
- [Operational Considerations, Caveats & Scaling](operational-considerations.md): Things to keep in mind regarding SQLite single-writer concurrency, Telegram API rate limits, edge deployment on Raspberry Pi, failure modes, and scaling limits.

---

## 🧭 High-Level Architecture Snapshot

```
                            [cinemesilla.com]
                                    │
                         (Raw HTML with Vue SSR)
                                    ▼
                         ┌─────────────────────┐
                         │    CinemaScraper    │
                         └──────────┬──────────┘
                                    │ BillboardData
                                    ▼
                         ┌─────────────────────┐
                         │  CatalogSyncService │
                         └─────┬─────────┬─────┘
                               │         │
                   Read/Update │         │ Dispatches
                               ▼         ▼
                      ┌───────────┐   ┌───────────────────────────┐
                      │ Database  │   │         Notifier          │
                      │ (SQLite)  │   └──┬─────────────┬─────────┬┘
                      └─────▲─────┘      │             │         │
                            │            ▼             ▼         ▼
                            │      [@cartelera_illa] [User DMs] [Resend Email]
               Reads/Writes │        (Broadcast)  (Filtered)   (Batched)
                 Sub Filters│
                      ┌─────┴─────┐
                      │    Bot    │
                      │ (asyncio) │
                      └───────────┘
```

The entire system runs within a single Docker container, maintaining a footprint of approximately 70 MB of RAM on a low-power edge host (Raspberry Pi).
