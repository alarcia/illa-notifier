# ADR 0003: Extracting Vue SSR Attributes vs Headless Browser Automation

* **Status**: Accepted
* **Deciders**: Engineering Team
* **Date**: 2026-03

---

## Context and Problem Statement
The target cinema website (`cinemesilla.com`) is a modern single-page application built with Vue.js. To monitor movies and showtimes, we must extract titles, genres, formats (VOSE, Catalan, Spanish), rooms, and dates.

Often, scraping modern SPAs leads developers to install headless browsers (Chromium with Playwright, Selenium, or Puppeteer). We needed to evaluate whether headless automation was necessary.

## Decision Drivers
* Resource constraints: Running Chromium on a Raspberry Pi consumes 400MB-1GB of RAM and significant CPU.
* Fragility: CSS class names change frequently during frontend updates.
* Speed: HTTP GET takes < 1 second; headless rendering takes 5-15 seconds.

## Considered Options
1. **Direct Vue Hydration Parsing**: Fetch raw HTML via standard `requests` and extract the JSON embedded directly within `<cinemaindexpage>` Vue props (`:onlytitlesinfo`, `:fullsessionsinfo`, `:postersurl`).
2. **Headless Browser (Playwright / Puppeteer)**: Launch Chromium, navigate to the page, wait for JavaScript hydration, and query DOM elements.

## Decision Outcome
Chosen option: **Option 1 (Direct Vue Hydration Parsing via BeautifulSoup + json.loads)**.

### Technical Implementation
The cinema backend server-renders a Vue root tag containing JSON-serialized model state:
```html
<cinemaindexpage 
    :postersurl='"..."' 
    :onlytitlesinfo='[...]' 
    :fullsessionsinfo='[...]'>
</cinemaindexpage>
```
`CinemaScraper` finds this element with `BeautifulSoup`, unescapes HTML entities, and directly parses the raw JSON into domain dataclasses.

### Positive Consequences
* **Extreme Efficiency**: Scraping takes ~300ms of network time and negligible CPU.
* **Resilience to CSS Changes**: Redesigning styles or changing markup layout does not break scraping as long as the backend passes the same Vue props.
* **No Heavy Dependencies**: No browser binaries or complex C-library dependencies inside the Docker image.

### Negative Consequences / Trade-offs
* If the cinema migrates completely away from Vue to client-side API fetching without SSR props, the scraper will need to be refactored to query their internal API endpoints directly.
