# SERP Scraper REST API — Server Integration Guide

> **Version:** 1.0.0  
> **Base URL:** `http://<server-host>:8000`  
> **Protocol:** REST over HTTP/HTTPS  
> **Data Format:** JSON (request body and response body)  
> **Interactive Docs:** `http://<server-host>:8000/docs` (Swagger UI) · `http://<server-host>:8000/redoc` (ReDoc)

---

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Server Information](#server-information)
3. [Authentication](#authentication)
4. [API Endpoints](#api-endpoints)
   - [Health Check](#1-health-check-get-health)
   - [Search](#2-web-search-post-apiv1search)
   - [Fetch URL](#3-fetch-url-content-post-apiv1fetch)
   - [Google News](#4-google-news-post-apiv1news)
   - [Google Scholar](#5-google-scholar-post-apiv1scholar)
5. [Response Format](#response-format)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)
8. [Server Configuration Reference](#server-configuration-reference)
9. [Integration Examples](#integration-examples)
10. [Troubleshooting / FAQ](#troubleshooting--faq)

---

## Quick Reference

| Endpoint | Method | Auth Required | Rate Limit (default) | Description |
|----------|--------|:---:|:---:|---|
| `/health` | `GET` | No | — | Server health check |
| `/api/v1/search` | `POST` | ✅ Yes | 30 req/min | Web search (Google / Bing) |
| `/api/v1/fetch` | `POST` | ✅ Yes | 60 req/min | Fetch URL → Markdown |
| `/api/v1/news` | `POST` | ✅ Yes | 30 req/min | Google News RSS |
| `/api/v1/scholar` | `POST` | ✅ Yes | 30 req/min | Google Scholar papers |

**Common headers for all authenticated endpoints:**

```
Content-Type: application/json
X-API-Key: <your_api_key>
```

---

## Server Information

### What This Server Does

This server wraps a SERP (Search Engine Results Page) scraping engine behind a REST API. It supports multiple search engines, browser-based and HTTP-based fetching, news aggregation, and academic paper search — all with rate-limiting, authentication, and structured logging.

### Technology Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI (Python) |
| Server | Uvicorn |
| Validation | Pydantic v2 |
| Auth | API keys (bcrypt hashed) |
| Browser Engine | Camoufox (Firefox/Gecko) |
| HTTP Client | httpx |
| Rate Limiting | Sliding window (in-memory) |

### Base URL Construction

```
http://<server-ip>:<port>
```

- **Default port:** `8000`
- The server configures `host` and `port` via environment variables (see [Server Configuration Reference](#server-configuration-reference)).

### Interactive API Documentation

Once the server is running, open these URLs in a browser:

- **Swagger UI:** `http://<server-host>:8000/docs` — interactive test console
- **ReDoc:** `http://<server-host>:8000/redoc` — clean reference view

---

## Authentication

### How It Works

1. The server stores **bcrypt-hashed** API keys (never plaintext).
2. Every request to a protected endpoint must include the `X-API-Key` header with your **plaintext** API key.
3. The server hashes the provided key and compares it against stored hashes using a constant-time algorithm.
4. If no key matches, the server returns `401 Unauthorized`.

### Request Header

```http
X-API-Key: abc123def456...
```

### Getting an API Key

The server administrator generates keys using the built-in CLI tool:

```bash
python -m api.cli.keys generate
```

This produces:
- A **plain API key** (shown only once — store it securely)
- A **hashed key** (for the server's `.env` configuration)

**You, as the client developer, only need the plain API key.** Pass it to the server administrator to generate one for you.

### Authentication Flow Diagram

```
Client                              Server
  │                                    │
  │  POST /api/v1/search               │
  │  X-API-Key: abc123...              │
  │ ──────────────────────────────►    │
  │                                    │  bcrypt hash(abc123...) → compare
  │                                    │  against stored hashed keys
  │                                    │
  │  ┌─── Match? ──── 200 OK          │
  │  │                                │
  │  └─── No match ── 401 Unauthorized│
  │                                    │
```

### Security Notes

- **Never send your hashed key** — the server needs the **plain** key to verify it.
- If you lose your plain key, the server admin must generate a new one (old keys can be deactivated).
- Multiple API keys can be active simultaneously (comma-separated in configuration).
- Unauthenticated access (`/health` only) can be disabled server-wide.

---

## API Endpoints

---

### 1. Health Check: `GET /health`

Checks whether the server is running and responsive.

**Authentication:** ❌ Not required

**Request:**

```bash
curl http://<server-host>:8000/health
```

**Response:**

```json
{
  "success": true,
  "data": {
    "status": "healthy"
  },
  "error": null,
  "meta": {
    "request_id": "health",
    "timestamp": "2026-06-24T12:00:00.000Z",
    "rate_limit_remaining": null,
    "rate_limit_reset": null
  }
}
```

**HTTP Status Codes:**
- `200` — Server is healthy

---

### 2. Web Search: `POST /api/v1/search`

Performs a web search on Google or Bing and returns organic results with rank, title, URL, and description.

**Authentication:** ✅ Required (`X-API-Key` header)  
**Rate Limit:** 30 requests/minute (configurable)

#### Request Body

```json
{
  "query": "python programming",
  "page": 1,
  "source": "google",
  "method": "browser"
}
```

| Field | Type | Required | Default | Constraints | Description |
|-------|------|:--------:|:-------:|-------------|-------------|
| `query` | string | ✅ | — | 1–500 chars | The search query |
| `page` | integer | ❌ | `1` | 1–100 | Page number (1-based) |
| `source` | string | ❌ | `null` | `"google"`, `"bing"`, or `null` | Search engine to use. `null` = auto-detect (Google first, Bing fallback) |
| `method` | string | ❌ | `null` | `"browser"`, `"http"`, or `null` | Scraping method. `"browser"` = Camoufox (stealth, slower), `"http"` = direct HTTP (faster, may be blocked). `null` = browser first, HTTP fallback |

#### Success Response (200)

```json
{
  "success": true,
  "data": [
    {
      "rank": 1,
      "title": "Python Programming Language",
      "url": "https://www.python.org/",
      "description": "The official home of the Python programming language...",
      "source": "google"
    },
    {
      "rank": 2,
      "title": "Python Tutorial - W3Schools",
      "url": "https://www.w3schools.com/python/",
      "description": "Python is a widely used programming language...",
      "source": "google"
    }
  ],
  "error": null,
  "meta": {
    "request_id": "a1b2c3d4",
    "timestamp": "2026-06-24T12:00:00.000Z",
    "rate_limit_remaining": 28,
    "rate_limit_reset": 45
  }
}
```

#### Response Data Fields (each result)

| Field | Type | Description |
|-------|------|-------------|
| `rank` | integer | Result position (1-based) |
| `title` | string | Page title |
| `url` | string | Result URL |
| `description` | string | Page snippet / meta description |
| `source` | string | Engine that returned the result (`"google"` or `"bing"`) |

#### Search Method Details

| Method | Engine | Typical Latency | Reliability |
|--------|--------|:---------------:|:-----------:|
| `"browser"` | Camoufox (Firefox) | 5–15s | ✅ High — stealth automation, handles JS-heavy pages |
| `"http"` | httpx | 1–3s | ⚠️ Moderate — faster but more likely to be blocked |
| `null` | Auto | Varies | ✅ Best of both — tries browser first, falls back to HTTP |

#### cURL Example

```bash
curl -X POST http://<server-host>:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_plain_api_key" \
  -d '{"query": "python programming", "page": 1, "source": "google"}'
```

#### Python Example (httpx)

```python
import httpx

response = httpx.post(
    "http://<server-host>:8000/api/v1/search",
    headers={"X-API-Key": "your_plain_api_key"},
    json={"query": "python programming", "page": 1},
)
data = response.json()
print(data["data"])  # list of search results
```

---

### 3. Fetch URL Content: `POST /api/v1/fetch`

Fetches a URL and converts the page content to Markdown text. Suitable for extracting readable content from web pages.

**Authentication:** ✅ Required (`X-API-Key` header)  
**Rate Limit:** 60 requests/minute (configurable)

#### Request Body

```json
{
  "url": "https://example.com",
  "prefer_browser": false,
  "compress": false
}
```

| Field | Type | Required | Default | Description |
|-------|------|:--------:|:-------:|-------------|
| `url` | string (URL) | ✅ | — | The URL to fetch (must be a valid HTTP/HTTPS URL) |
| `prefer_browser` | boolean | ❌ | `true` | **Deprecated.** When `true`: browser first, BS4 fallback. When `false` (recommended): BS4 first with **automatic JavaScript detection** — if JS is detected in the HTML, it automatically falls back to browser |
| `compress` | boolean | ❌ | `false` | When `true`, truncates long content (>10K chars) to head (35%), middle (15%), tail (50%) and marks truncated sections |

**Recommended setting:** `prefer_browser: false` — the automatic JS detection gives the best balance of speed and reliability.

#### Success Response (200) — Normal

```json
{
  "success": true,
  "data": {
    "url": "https://example.com",
    "content": "# Example Domain\n\nThis domain is for use in...",
    "char_count": 1250,
    "was_truncated": false,
    "original_length": null
  },
  "error": null,
  "meta": {
    "request_id": "e5f6g7h8",
    "timestamp": "2026-06-24T12:00:00.000Z",
    "rate_limit_remaining": 58,
    "rate_limit_reset": 30
  }
}
```

#### Success Response (200) — Compressed

When `compress: true` and content exceeds ~10,000 characters:

```json
{
  "success": true,
  "data": {
    "url": "https://example.com/long-page",
    "content": "[First 1,575 chars]...\n\n-- 10,500 chars truncated --\n\n[Last 2,250 chars]",
    "char_count": 4532,
    "was_truncated": true,
    "original_length": 15000
  },
  "error": null,
  "meta": { "...": "..." }
}
```

#### Response Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | The fetched URL (same as request) |
| `content` | string | Page content converted to Markdown |
| `char_count` | integer | Character count of returned content |
| `was_truncated` | boolean | `true` if content was truncated due to compression |
| `original_length` | integer | Original character count before truncation, or `null` if not truncated |

#### Fetch Logic — How the Server Resolves Content

```
Request received
       │
       ▼
  prefer_browser=false? (recommended)
       │
       ├── YES ──► HTTP fetch (httpx + BeautifulSoup)
       │                │
       │                ├── JS detected in HTML? ──► Browser (Camoufox)
       │                │
       │                ├── Content < 100 chars?  ──► Browser (Camoufox)
       │                │
       │                └── OK ──► Return Markdown
       │
       └── NO  ──► Browser (Camoufox) first
                      │
                      ├── OK ──► Return Markdown
                      │
                      └── Fail ──► HTTP fetch fallback
```

#### cURL Example

```bash
curl -X POST http://<server-host>:8000/api/v1/fetch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_plain_api_key" \
  -d '{"url": "https://en.wikipedia.org/wiki/Python_(programming_language)", "compress": true}'
```

---

### 4. Google News: `POST /api/v1/news`

Fetches news articles from Google News RSS feeds for a given query. Returns article title, URL, description, publication date, and source.

**Authentication:** ✅ Required (`X-API-Key` header)  
**Rate Limit:** 30 requests/minute (configurable, shared with `/scholar`)

#### Request Body

```json
{
  "query": "Tesla",
  "max_results": 50,
  "language": "tr",
  "country": "TR"
}
```

| Field | Type | Required | Default | Constraints | Description |
|-------|------|:--------:|:-------:|-------------|-------------|
| `query` | string | ✅ | — | 1–500 chars | News search topic |
| `max_results` | integer | ❌ | `50` | 1–100 | Maximum number of news articles |
| `language` | string | ❌ | `"tr"` | ISO language code | Language for results (`"tr"`, `"en"`, etc.) |
| `country` | string | ❌ | `null` | ISO country code | Country for geo-specific results. If not set, auto-derived from language (e.g., `"tr"` → `"TR"`, `"en"` → `"US"`) |

#### Success Response (200)

```json
{
  "success": true,
  "data": [
    {
      "title": "Tesla announces new model",
      "url": "https://news.google.com/rss/articles/...",
      "description": "Tesla unveiled their latest electric vehicle...",
      "published": "2026-06-23T08:00:00Z",
      "source": "BBC"
    },
    {
      "title": "Tesla stock rises on earnings",
      "url": "https://news.google.com/rss/articles/...",
      "description": "Shares of Tesla climbed 5% after...",
      "published": "2026-06-22T14:30:00Z",
      "source": "Financial Times"
    }
  ],
  "error": null,
  "meta": {
    "request_id": "i9j0k1l2",
    "timestamp": "2026-06-24T12:00:00.000Z",
    "rate_limit_remaining": 28,
    "rate_limit_reset": 50
  }
}
```

#### Response Data Fields (each article)

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Article headline |
| `url` | string | Google News RSS article URL (redirects to publisher) |
| `description` | string | Article excerpt / summary |
| `published` | string (ISO 8601) | Publication date and time |
| `source` | string | Publishing source name (e.g., "BBC", "Reuters") |

#### cURL Example

```bash
curl -X POST http://<server-host>:8000/api/v1/news \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_plain_api_key" \
  -d '{"query": "artificial intelligence", "max_results": 10, "language": "en"}'
```

---

### 5. Google Scholar: `POST /api/v1/scholar`

Searches Google Scholar for academic papers and returns rich metadata including authors, citation count, publication venue, year, and PDF links where available.

**Authentication:** ✅ Required (`X-API-Key` header)  
**Rate Limit:** 30 requests/minute (shared with `/news`, configurable via `API_RATE_LIMIT_NEWS`)

#### Request Body

```json
{
  "query": "machine learning",
  "max_results": 50,
  "language": "en",
  "year_from": 2020,
  "year_to": 2024,
  "sort_by": "relevance",
  "author": "Hinton",
  "exact_phrase": "neural networks"
}
```

| Field | Type | Required | Default | Constraints | Description |
|-------|------|:--------:|:-------:|-------------|-------------|
| `query` | string | ✅ | — | 1–500 chars | Search query |
| `max_results` | integer | ❌ | `50` | 1–100 | Max results to return |
| `language` | string | ❌ | `"en"` | Language code | Interface language |
| `year_from` | integer | ❌ | `null` | 1900–2030 | Filter: start publication year |
| `year_to` | integer | ❌ | `null` | 1900–2030 | Filter: end publication year |
| `sort_by` | string | ❌ | `"relevance"` | `"relevance"` or `"date"` | Sort order |
| `exact_phrase` | string | ❌ | `null` | — | Require exact phrase (Google Scholar `as_epq`) |
| `some_words` | string | ❌ | `null` | — | Require at least one of these words (`as_oq`) |
| `without_words` | string | ❌ | `null` | — | Exclude these words (`as_eq`) |
| `author` | string | ❌ | `null` | — | Search by author name (`as_sauthors`) |
| `publication` | string | ❌ | `null` | — | Search within a specific publication (`as_publication`) |

#### Success Response (200)

```json
{
  "success": true,
  "data": [
    {
      "title": "Learning representations by back-propagating errors",
      "url": "https://www.nature.com/articles/323533664",
      "scholar_url": "https://scholar.google.com/scholar?q=info:abc123:scholar.google.com/&output=cite",
      "snippet": "We describe a new learning procedure...",
      "authors": ["D E Rumelhart", "G E Hinton", "R J Williams"],
      "publication_year": 1986,
      "venue": "Nature",
      "citation_count": 51234,
      "pdf_url": "https://www.nature.com/articles/323533664.pdf",
      "cluster_id": "abc123"
    }
  ],
  "error": null,
  "meta": {
    "request_id": "s1t2u3v4",
    "timestamp": "2026-06-24T12:00:00.000Z",
    "rate_limit_remaining": 28,
    "rate_limit_reset": 45
  }
}
```

#### Response Data Fields (each paper)

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Full paper title |
| `url` | string | Direct link to the paper/article |
| `scholar_url` | string | Google Scholar citation/info page URL |
| `snippet` | string | Abstract or excerpt from the paper |
| `authors` | array of string | List of author names |
| `publication_year` | integer | Year of publication (`null` if not available) |
| `venue` | string | Journal, conference, or publication venue name |
| `citation_count` | integer | Number of citations on Google Scholar |
| `pdf_url` | string | Direct PDF download link if available (`null` otherwise) |
| `cluster_id` | string | Google Scholar cluster ID (for grouping related articles) |

#### cURL Example

```bash
curl -X POST http://<server-host>:8000/api/v1/scholar \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_plain_api_key" \
  -d '{
    "query": "transformer attention",
    "max_results": 20,
    "year_from": 2020,
    "year_to": 2024,
    "sort_by": "relevance"
  }'
```

---

## Response Format

Every endpoint returns a uniform JSON envelope.

### Success Response

```json
{
  "success": true,
  "data": { ... },           // Response payload (varies per endpoint)
  "error": null,
  "meta": {
    "request_id": "a1b2c3d4",
    "timestamp": "2026-06-24T12:00:00.000Z",
    "rate_limit_remaining": 28,
    "rate_limit_reset": 45
  }
}
```

### Error Response

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded for /search. Try again in 30 seconds.",
    "details": {
      "limit": 30,
      "window": "1 minute"
    }
  },
  "meta": {
    "request_id": "m3n4o5p6",
    "timestamp": "2026-06-24T12:00:00.000Z",
    "rate_limit_remaining": 0,
    "rate_limit_reset": 30
  }
}
```

### Meta Fields (present in all responses)

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | Unique 8-character request identifier |
| `timestamp` | string (ISO 8601) | Response timestamp in UTC |
| `rate_limit_remaining` | integer or `null` | Requests remaining in current rate limit window |
| `rate_limit_reset` | integer or `null` | Seconds until the rate limit window resets |

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | When |
|:----:|---------|------|
| `200` | Success | Request completed successfully |
| `400` | Bad Request | Invalid parameters, missing required fields, or validation errors |
| `401` | Unauthorized | Missing or invalid `X-API-Key` header |
| `429` | Too Many Requests | Rate limit exceeded for the endpoint. Check `Retry-After` header |
| `500` | Internal Error | Server-side error (scraper failure, proxy error, etc.) |

### Error Codes

| Code | Description | Typical Cause |
|------|-------------|---------------|
| `PROXY_ERROR` | All proxies failed | Proxy server unreachable or exhausted |
| `CAPTCHA_ERROR` | CAPTCHA detected | Search engine challenged the request |
| `TIMEOUT_ERROR` | Page load timeout | Target page too slow or unreachable |
| `PARSE_ERROR` | Failed to parse results | Unexpected HTML structure from search engine |
| `VALIDATION_ERROR` | Request validation failed | Invalid field values in request body |
| `RATE_LIMIT_EXCEEDED` | Rate limit exceeded | Too many requests in the current window |
| `UNKNOWN_ERROR` | Unexpected error | Unforeseen server-side failure |

### Handling Rate Limits (429)

1. Check the `Retry-After` HTTP response header (value is in seconds).
2. Inspect `meta.rate_limit_remaining` and `meta.rate_limit_reset` in every response to pace your requests.
3. Wait the specified time before retrying.

```python
# Python: handle rate limiting
import httpx
import time

response = httpx.post("http://<server-host>:8000/api/v1/search", ...)
if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 30))
    print(f"Rate limited. Waiting {retry_after}s...")
    time.sleep(retry_after)
    # retry the request
```

---

## Rate Limiting

### How It Works

- **Algorithm:** Sliding window (1-minute window, rolling)
- **Scope:** Global per endpoint (all API keys combined share the limit)
- **Granularity:** Each endpoint has its own counter (`/search`, `/fetch`, `/news` + `/scholar`)

### Default Limits

| Endpoint | Default Limit | Config Variable |
|----------|:-------------:|:---------------:|
| `/api/v1/search` | 30 req/min | `API_RATE_LIMIT_SEARCH` |
| `/api/v1/fetch` | 60 req/min | `API_RATE_LIMIT_FETCH` |
| `/api/v1/news` | 30 req/min | `API_RATE_LIMIT_NEWS` |
| `/api/v1/scholar` | 30 req/min | `API_RATE_LIMIT_NEWS` (shared) |
| Other | 100 req/min | `API_RATE_LIMIT_DEFAULT` |

### Reading Rate Limit From Responses

Every response includes rate limit information in `meta`:

```json
"meta": {
  "rate_limit_remaining": 28,
  "rate_limit_reset": 45
}
```

- **`rate_limit_remaining`**: How many more requests you can make in the current window.
- **`rate_limit_reset`**: Seconds until the window advances (oldest timestamp drops out).

### When Rate Limited

The server responds with:
- **HTTP 429** status
- **`Retry-After`** header (seconds)
- Standard error body with code `RATE_LIMIT_EXCEEDED`

---

## Server Configuration Reference

> The following environment variables control the server. Share this section with the server administrator if you need specific limits or settings.

### Server Host & Port

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `"0.0.0.0"` | Bind address (`0.0.0.0` = all interfaces) |
| `API_PORT` | `8000` | Listen port (1–65535) |
| `API_DEBUG` | `false` | Enable debug mode (auto-reload on code changes) |

### Request Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `API_MAX_CONCURRENT_REQUESTS` | `15` | Max concurrent requests handled at once (1–100) |
| `API_REQUEST_TIMEOUT` | `60` | Per-request timeout in seconds (5–300) |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `API_RATE_LIMIT_SEARCH` | `30` | Requests/minute for `/search` |
| `API_RATE_LIMIT_FETCH` | `60` | Requests/minute for `/fetch` |
| `API_RATE_LIMIT_NEWS` | `30` | Requests/minute for `/news` and `/scholar` |
| `API_RATE_LIMIT_DEFAULT` | `100` | Default for unknown endpoints |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEYS_HASHED` | `""` | Comma-separated bcrypt-hashed API keys |
| `API_ALLOW_NO_AUTH` | `false` | Allow unauthenticated access (never enable in production) |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `API_LOG_LEVEL` | `"INFO"` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `API_LOG_DIR` | `"logs"` | Directory for log files |
| `API_LOG_RETENTION_DAYS` | `7` | Days to retain rotated log files |

### CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `API_CORS_ORIGINS` | `""` | Comma-separated allowed origins (e.g., `https://myapp.com,https://admin.myapp.com`). Empty = no CORS headers |

### Complete `.env` Template for Server Admin

```bash
# ===========================================
# SERVER CONFIGURATION
# ===========================================
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false

# ===========================================
# REQUEST PROCESSING
# ===========================================
API_MAX_CONCURRENT_REQUESTS=15
API_REQUEST_TIMEOUT=60

# ===========================================
# RATE LIMITING
# ===========================================
API_RATE_LIMIT_SEARCH=30
API_RATE_LIMIT_FETCH=60
API_RATE_LIMIT_NEWS=30
API_RATE_LIMIT_DEFAULT=100

# ===========================================
# AUTHENTICATION
# ===========================================
API_KEYS_HASHED="$2b$12$hashed_key_here"
API_ALLOW_NO_AUTH=false

# ===========================================
# LOGGING
# ===========================================
API_LOG_LEVEL=INFO
API_LOG_DIR=logs
API_LOG_RETENTION_DAYS=7

# ===========================================
# CORS
# ===========================================
API_CORS_ORIGINS=https://myapp.com,https://admin.myapp.com
```

---

## Integration Examples

### Python (using `httpx`)

```python
import httpx

BASE_URL = "http://<server-host>:8000"
API_KEY = "your_plain_api_key"

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
}

client = httpx.Client(base_url=BASE_URL, headers=headers, timeout=120)

# --- Health Check ---
resp = client.get("/health")
print(resp.json())

# --- Search ---
resp = client.post(
    "/api/v1/search",
    json={"query": "latest AI research", "page": 1},
)
data = resp.json()
if data["success"]:
    for result in data["data"]:
        print(f"#{result['rank']}: {result['title']} — {result['url']}")

# --- Fetch URL ---
resp = client.post(
    "/api/v1/fetch",
    json={"url": "https://example.com", "compress": True},
)
data = resp.json()
if data["success"]:
    print(data["data"]["content"][:500])

# --- News ---
resp = client.post(
    "/api/v1/news",
    json={"query": "technology", "max_results": 5, "language": "en"},
)
data = resp.json()
if data["success"]:
    for article in data["data"]:
        print(f"[{article['source']}] {article['title']}")

# --- Scholar ---
resp = client.post(
    "/api/v1/scholar",
    json={
        "query": "deep learning",
        "max_results": 5,
        "sort_by": "relevance",
    },
)
data = resp.json()
if data["success"]:
    for paper in data["data"]:
        print(f"{paper['title']} ({paper['publication_year']}) — {paper['citation_count']} citations")
```

### JavaScript / TypeScript (using `fetch`)

```javascript
const BASE_URL = "http://<server-host>:8000";
const API_KEY = "your_plain_api_key";

const headers = {
  "Content-Type": "application/json",
  "X-API-Key": API_KEY,
};

async function searchWeb(query, page = 1) {
  const response = await fetch(`${BASE_URL}/api/v1/search`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, page }),
  });
  return response.json();
}

async function fetchUrl(url, compress = false) {
  const response = await fetch(`${BASE_URL}/api/v1/fetch`, {
    method: "POST",
    headers,
    body: JSON.stringify({ url, compress }),
  });
  return response.json();
}

async function getNews(query, maxResults = 10) {
  const response = await fetch(`${BASE_URL}/api/v1/news`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, max_results: maxResults, language: "en" }),
  });
  return response.json();
}

async function searchScholar(query, opts = {}) {
  const response = await fetch(`${BASE_URL}/api/v1/scholar`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, ...opts }),
  });
  return response.json();
}

// Usage:
// const results = await searchWeb("quantum computing");
// console.log(results.data);
```

### cURL Cheat Sheet

```bash
# Health check
curl http://<server-host>:8000/health

# Search
curl -X POST http://<server-host>:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{"query": "your search term"}'

# Fetch URL
curl -X POST http://<server-host>:8000/api/v1/fetch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{"url": "https://example.com/page"}'

# News
curl -X POST http://<server-host>:8000/api/v1/news \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{"query": "artificial intelligence", "max_results": 10, "language": "en"}'

# Scholar
curl -X POST http://<server-host>:8000/api/v1/scholar \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{"query": "machine learning", "year_from": 2020, "year_to": 2024}'
```

---

## Troubleshooting / FAQ

### Q: I get `401 Unauthorized`

**Causes & fixes:**

| Cause | Solution |
|-------|----------|
| Missing `X-API-Key` header | Add the header to your request |
| Wrong API key | Verify the plain key with the server admin |
| Server has no keys configured | Contact admin to set `API_KEYS_HASHED` |
| Wrong format | The header value must be the **plain** key, not the hashed version |

### Q: I get `429 Too Many Requests`

The rate limit for the endpoint has been reached.

- Wait the number of seconds specified in the `Retry-After` response header.
- Check `meta.rate_limit_remaining` before each request to pace yourself.
- Request higher rate limits from the server administrator.

### Q: I get `500 Internal Server Error`

The server encountered an error while processing the request. Check the `error.code` field:

- `PROXY_ERROR` — Proxy servers are unreachable. The server admin should verify proxy configuration.
- `CAPTCHA_ERROR` — The search engine is blocking the request. The server admin may need to rotate proxies or wait.
- `TIMEOUT_ERROR` — The target page is too slow. Try a different source or increase `API_REQUEST_TIMEOUT`.
- `PARSE_ERROR` — The search engine returned an unexpected format. May be temporary.

### Q: Search returns fewer results than expected

- The `source` may have limited results for your query. Try switching from `"google"` to `"bing"` (or vice versa) by changing the `source` parameter.
- If using a specific page number, the search engine may not have that many pages for the query.
- The page may contain duplicate or suppressed results.

### Q: Fetch returns empty or very short content

- The page may rely heavily on JavaScript. Set `prefer_browser` to `true` explicitly to force browser rendering.
- The URL may be behind a login wall or paywall — the scraper cannot bypass authentication.
- The page may block automated requests entirely.

### Q: How do I get the server's base URL?

Your server administrator will provide you with the server's IP address or hostname and the port. The base URL is:

```
http://<ip-or-hostname>:<port>
```

If the server is behind a reverse proxy (e.g., Nginx) with SSL, the URL would be:

```
https://<domain>
```

### Q: Can I use multiple API keys?

Yes. The server supports multiple hashed keys (comma-separated in `API_KEYS_HASHED`). Each client gets their own key, but rate limits are **global** per endpoint — all keys share the same pool.

### Q: Is there a way to test endpoints interactively?

Yes — open the server's interactive API documentation in a browser:

- **Swagger UI:** `http://<server-host>:8000/docs`
- **ReDoc:** `http://<server-host>:8000/redoc`

You can execute requests directly from the Swagger UI by entering your API key in the "Authorize" button.

---

> **Need help?** Contact the server administrator with your `request_id` from any failed response — it helps locate the request in the server's logs.
