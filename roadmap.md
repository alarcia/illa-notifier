# Project Roadmap

This document outlines the planned improvements and upcoming features for the **illa-notifier** bot.

## Core Bot Improvements

### 🌐 Multi-language Support
- **Additional Languages**: Implementation of **English (en)** and **Catalan (ca)** alongside the current language.
- **User Configuration**: A new command will allow users to toggle their preferred language for bot interactions.
- **Improved UX**: Localization of all system messages and notifications.

## Monitoring & Maintenance

### 🕵️‍♂️ Genre & Format Detection System
- **Advanced Tracking**: Implement a system to detect new genres or formats that are currently untracked in the main database.
- **Storage**: A dedicated database table will store these new detections for developer review.
- **Developer Alerts**:
    - Automated email notifications sent to the administrator for each new detection.
    - Each alert will include the full state of the detection table for quick auditing.
- **Manual Management**: Records will be kept until manually deleted by the developer after confirming they have been processed or added to the main tracking logic.
