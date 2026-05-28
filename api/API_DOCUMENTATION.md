# SERP Scraper REST API Documentation

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Configuration](#configuration)
5. [Authentication](#authentication)
6. [Endpoints](#endpoints)
   - [Health Check](#health-check)
   - [Search](#search)
   - [Fetch](#fetch)
   - [News](#news)
   - [Scholar](#scholar)
7. [Request/Response Models](#requestresponse-models)
8. [Error Handling](#error-handling)
9. [Rate Limiting](#rate-limiting)
10. [Logging](#logging)
11. [CLI Tools](#cli-tools)
12. [Architecture](#architecture)
13. [Project Structure](#project-structure)

---

## Overview

The SERP Scraper REST API is a FastAPI-based HTTP interface that provides programmatic access to search engine scraping functionality. It wraps the `serp` library with a layer of HTTP authentication, rate limiting, and centralized logging.

### Key Features

- **Multiple Search Methods**: Browser-based (nodriver) and HTTP-based (httpx) scraping
- **Google News RSS**: Scrape news articles via Google News RSS feeds
- **Google Scholar**: Scrape academic papers with rich metadata (authors, citations, year, venue, PDF links)
- **URL Fetching**: Retrieve page content as Markdown
- **Rate Limiting**: Per-endpoint sliding window rate limiting
- **API Key Authentication**: Secure access with hashed API keys
- **Centralized Logging**: Daily-rotated log files with structured formatting
- **CORS Support**: Configurable cross-origin resource sharing
- **Concurrent Request Pooling**: Configurable maximum concurrent requests

### Technology Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI 0.100+ |
| Server | Uvicorn |
| Validation | Pydantic v2 |
| Password Hashing | passlib + bcrypt |
| Async | asyncio |

---

## Installation

### Prerequisites

- Python 3.10 or higher
- Google Chrome browser (for browser-based scraping)

### Install with API Support

```bash
pip install serp-scraper[api]
```

### From Source

```bash
git clone https://github.com/neuronaline/serp-scraper.git
cd serp-scraper
pip install -e ".[api]"
```

---

## Quick Start

### 1. Generate an API Key

```bash
python -m api.cli.keys generate
```

This outputs:
- A **plain API key** (shown only once - save it securely)
- A **hashed key** (add to your `.env` file)

### 2. Configure Environment

Create a `.env` file in your project root:

```bash
# Server settings
API_HOST=0.0.0.0
API_PORT=8000

# API Key (from step 1)
API_KEYS_HASHED="your_hashed_key_here"

# Rate limiting (requests per minute)
API_RATE_LIMIT_SEARCH=30
API_RATE_LIMIT_FETCH=60
API_RATE_LIMIT_NEWS=30
```

### 3. Run the Server

```bash
python -m api.main
# Or with uvicorn directly:
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Test the API

```bash
# Health check
curl http://localhost:8000/health

# Search request
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_plain_api_key" \
  -d '{"query": "python programming"}'
```

---

## Configuration

All API configuration is done via environment variables with the `API_` prefix. The application uses Pydantic Settings for validation.

### Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `API_HOST` | str | `0.0.0.0` | Server host |
| `API_PORT` | int | `8000` | Server port (1-65535) |
| `API_DEBUG` | bool | `false` | Enable debug mode (auto-reload) |
| `API_MAX_CONCURRENT_REQUESTS` | int | `15` | Max concurrent requests (1-100) |
| `API_REQUEST_TIMEOUT` | int | `60` | Request timeout in seconds (5-300) |
| `API_RATE_LIMIT_SEARCH` | int | `30` | Rate limit for /search (requests/min) |
| `API_RATE_LIMIT_FETCH` | int | `60` | Rate limit for /fetch (requests/min) |
| `API_RATE_LIMIT_NEWS` | int | `30` | Rate limit for /news and /scholar (requests/min) |
| `API_RATE_LIMIT_DEFAULT` | int | `100` | Default rate limit (requests/min) |
| `API_KEYS_HASHED` | str | `""` | Comma-separated hashed API keys |
| `API_ALLOW_NO_AUTH` | bool | `false` | Allow unauthenticated access (not recommended) |
| `API_LOG_LEVEL` | str | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `API_LOG_DIR` | str | `logs` | Log file directory |
| `API_LOG_RETENTION_DAYS` | int | `7` | Days to retain log files |
| `API_CORS_ORIGINS` | str | `""` | Comma-separated allowed origins |

### Configuration Precedence

1. Environment variables (highest priority)
2. `.env` file
3. Default values (lowest priority)

---

## Authentication

### API Key Header

All endpoints (except `/health`) require the `X-API-Key` header:

```http
X-API-Key: your_api_key_here
```

### Key Generation

Use the built-in CLI tool to generate API keys:

```bash
python -m api.cli.keys generate
```

Output:
```
============================================================
NEW API KEY GENERATED
============================================================

PLAIN KEY (save this, it will not be shown again):
  abc123def456...

HASHED KEY (add this to your .env file):
  $2b$12$...

============================================================
Add to .env:
  API_KEYS_HASHED="$2b$12$..."
============================================================
```

### Key Storage

- **Plain key**: Shown only once during generation. User must store it securely.
- **Hashed key**: Stored in `API_KEYS_HASHED` environment variable. Never decrypted.

### Authentication Flow

1. Client sends request with `X-API-Key` header
2. Server looks up `API_KEYS_HASHED` environment variable
3. Server hashes the provided key with bcrypt
4. Server compares hashed keys using constant-time comparison
5. Request proceeds if any key matches

### Security Notes

- API keys are hashed using bcrypt (salted automatically)
- Comparison uses constant-time algorithm to prevent timing attacks
- Failed authentication returns `401 Unauthorized`
- When `API_KEYS_HASHED` is empty and `API_ALLOW_NO_AUTH=false`, all requests are rejected

---

## Endpoints

### Base URL

```
http://localhost:8000
```

### Health Check

#### `GET /health`

Returns the health status of the API.

**Authentication**: Not required

**Response**:
```json
{
  "success": true,
  "data": {
    "status": "healthy"
  },
  "error": null,
  "meta": {
    "request_id": "health",
    "timestamp": "2026-05-12T07:30:00.000Z",
    "rate_limit_remaining": null,
    "rate_limit_reset": null
  }
}
```

---

### Search

#### `POST /api/v1/search`

Perform a SERP search using Google or Bing.

**Authentication**: Required (`X-API-Key` header)

**Rate Limit**: 30 requests/minute (configurable)

**Request Body**:
```json
{
  "query": "python programming",
  "page": 1,
  "source": "google",
  "method": "browser"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | - | Search query (1-500 chars) |
| `page` | integer | No | `1` | Page number (1-100) |
| `source` | string | No | `null` | Search source: `"google"`, `"bing"`, or `null` (auto) |
| `method` | string | No | `null` | Search method: `"browser"`, `"http"`, or `null` (auto) |

**Response (Success)**:
```json
{
  "success": true,
  "data": [
    {
      "rank": 1,
      "title": "Python Programming Language",
      "url": "https://www.python.org/",
      "description": "The official home of the Python...",
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
    "timestamp": "2026-05-12T07:30:00.000Z",
    "rate_limit_remaining": 28,
    "rate_limit_reset": 45
  }
}
```

**Search Methods**:
- `browser`: Uses `nodriver` for stealth Chrome automation (more reliable, slower)
- `http`: Uses `httpx` for direct HTTP requests (faster, may be blocked)
- `null/auto`: Tries browser first, falls back to HTTP

**Search Sources**:
- `google`: Google search engine
- `bing`: Bing search engine
- `null/auto`: Google first, Bing fallback

---

### Fetch

#### `POST /api/v1/fetch`

Fetch URL content and return as Markdown.

**Authentication**: Required (`X-API-Key` header)

**Rate Limit**: 60 requests/minute (configurable)

**Request Body**:
```json
{
  "url": "https://example.com",
  "prefer_browser": true,
  "compress": false
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string (URL) | Yes | - | URL to fetch |
| `prefer_browser` | boolean | No | `true` | **Deprecated.** When `true`, uses browser first with BS4 fallback. When `false` (default), uses BS4 first with automatic JavaScript detection and browser fallback for JS-heavy pages. |
| `compress` | boolean | No | `false` | Compress long content (>10K chars). When enabled, takes head (35%), middle (15%), and tail (50%) portions, marking truncated sections. |

**Note:** The `prefer_browser` parameter controls fetch order but is supplemented by automatic JavaScript detection. When `prefer_browser=false` (the default and recommended setting), the system:
1. Attempts BS4 (HTTP + BeautifulSoup) first
2. **If JavaScript is detected in the HTML**, immediately falls back to browser
3. If BS4 fetch fails for any reason, falls back to browser

**Response (Success)**:
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
    "timestamp": "2026-05-12T07:30:00.000Z",
    "rate_limit_remaining": 58,
    "rate_limit_reset": 30
  }
}
```

**Compressed Response Example** (when `compress: true` and content > 10K chars):
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
  "meta": {
    "request_id": "e5f6g7h8",
    "timestamp": "2026-05-12T07:30:00.000Z",
    "rate_limit_remaining": 58,
    "rate_limit_reset": 30
  }
}
```

**JavaScript Detection & Browser Execution**:

The fetch endpoint automatically detects whether a page contains JavaScript and handles it accordingly:

1. **Lightweight HTTP Fetch (BS4)**: For static HTML pages without JavaScript, uses fast HTTP requests + BeautifulSoup4 parsing. This is the primary method for pages that don't require JavaScript execution.

2. **Browser-Based Fetch (nodriver)**: Automatically invoked when:
   - The page contains `<script>` tags with JavaScript code or external JS files
   - The BS4 fetch fails or returns minimal content (<100 characters)
   - Any retryable error occurs (timeout, proxy, CAPTCHA, etc.)

3. **Page Load Guarantee**: Whether using HTTP or browser fetch:
   - HTTP fetch: Waits for complete HTTP response with all redirect handling
   - Browser fetch: Waits for the `load` event plus additional time (1s) for JavaScript execution and dynamic content rendering

**Response Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `url` | string | The fetched URL |
| `content` | string | Page content as Markdown |
| `char_count` | integer | Character count of content (compressed if applicable) |
| `was_truncated` | boolean | Whether content was truncated due to compression |
| `original_length` | integer | Original character count if truncated, `null` otherwise |

---

### News

#### `POST /api/v1/news`

Fetch Google News articles for a query via RSS feeds.

**Authentication**: Required (`X-API-Key` header)

**Rate Limit**: 30 requests/minute (configurable)

**Request Body**:
```json
{
  "query": "Tesla",
  "max_results": 50,
  "language": "tr",
  "country": "TR"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | - | News search query (1-500 chars) |
| `max_results` | integer | No | `50` | Maximum results (1-100) |
| `language` | string | No | `tr` | Language code (`tr`, `en`, etc.) |
| `country` | string | No | `null` | Country code (`TR`, `US`). Auto-derived from language if not specified. |

**Response (Success)**:
```json
{
  "success": true,
  "data": [
    {
      "title": "Tesla announces new model",
      "url": "https://news.google.com/rss/articles/...",
      "description": "Tesla unveiled their latest electric vehicle...",
      "published": "2026-05-11T08:00:00Z",
      "source": "BBC"
    },
    {
      "title": "Tesla stock rises on earnings",
      "url": "https://news.google.com/rss/articles/...",
      "description": "Shares of Tesla climbed 5% after...",
      "published": "2026-05-10T14:30:00Z",
      "source": "NTV"
    }
  ],
  "error": null,
  "meta": {
    "request_id": "i9j0k1l2",
    "timestamp": "2026-05-12T07:30:00.000Z",
    "rate_limit_remaining": 28,
    "rate_limit_reset": 50
  }
}
```

---

### Scholar

#### `POST /api/v1/scholar`

Search Google Scholar for academic papers with rich metadata.

**Authentication**: Required (`X-API-Key` header)

**Rate Limit**: 30 requests/minute (shared with /news, configurable via `API_RATE_LIMIT_NEWS`)

**Request Body**:
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

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | - | Scholar search query (1-500 chars) |
| `max_results` | integer | No | `50` | Maximum results (1-100) |
| `language` | string | No | `en` | Language code (`en`, `tr`, etc.) |
| `year_from` | integer | No | `null` | Start year for publication range (1900-2030) |
| `year_to` | integer | No | `null` | End year for publication range (1900-2030) |
| `sort_by` | string | No | `relevance` | Sort order: `"relevance"` or `"date"` |
| `exact_phrase` | string | No | `null` | Exact phrase search (as_epq) |
| `some_words` | string | No | `null` | At least one of the words (as_oq) |
| `without_words` | string | No | `null` | Without these words (as_eq) |
| `author` | string | No | `null` | Search by author name (as_sauthors) |
| `publication` | string | No | `null` | Publication name (as_publication) |

**Response (Success)**:
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
    "timestamp": "2026-05-12T07:30:00.000Z",
    "rate_limit_remaining": 28,
    "rate_limit_reset": 45
  }
}
```

**ScholarResult Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Paper title |
| `url` | string | Direct link to the paper/article |
| `scholar_url` | string | Google Scholar page URL |
| `snippet` | string | Abstract/excerpt from the paper |
| `authors` | array | List of author names |
| `publication_year` | integer | Year of publication (null if not available) |
| `venue` | string | Journal, conference, or publication venue |
| `citation_count` | integer | Number of citations |
| `pdf_url` | string | Direct PDF link if available (null otherwise) |
| `cluster_id` | string | Google Scholar cluster ID |

---

## Request/Response Models

### Standard Response Format

All endpoints return responses in this format:

```python
class APIResponse(BaseModel, Generic[T]):
    success: bool                    # Whether the request succeeded
    data: Optional[T]                # Response data (None on error)
    error: Optional[ErrorDetail]     # Error info (None on success)
    meta: ResponseMeta               # Response metadata
```

### Response Metadata

```python
class ResponseMeta(BaseModel):
    request_id: str                  # Unique request identifier (8 chars)
    timestamp: datetime              # Response timestamp (UTC)
    rate_limit_remaining: Optional[int]  # Remaining requests in window
    rate_limit_reset: Optional[int]      # Seconds until rate limit reset
```

### Error Detail

```python
class ErrorDetail(BaseModel):
    code: str                        # Error code (e.g., "RATE_LIMIT_EXCEEDED")
    message: str                     # Human-readable error message
    details: Optional[dict]          # Additional error details
```

---

## Error Handling

### HTTP Status Codes

| Status Code | Meaning |
|-------------|---------|
| `200` | Success |
| `400` | Bad Request - Invalid parameters |
| `401` | Unauthorized - Invalid or missing API key |
| `429` | Too Many Requests - Rate limit exceeded |
| `500` | Internal Server Error |

### Error Response Format

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
    "timestamp": "2026-05-12T07:30:00.000Z",
    "rate_limit_remaining": 0,
    "rate_limit_reset": 30
  }
}
```

### Error Codes

| Code | Description |
|------|-------------|
| `PROXY_ERROR` | All proxies failed |
| `CAPTCHA_ERROR` | CAPTCHA detected |
| `TIMEOUT_ERROR` | Page load timeout |
| `PARSE_ERROR` | Failed to parse results |
| `VALIDATION_ERROR` | Request validation failed |
| `RATE_LIMIT_EXCEEDED` | Rate limit exceeded |
| `UNKNOWN_ERROR` | Unexpected error |

### Exception Hierarchy

```
APIError (base)
├── RateLimitExceededError
├── SearchError
├── FetchError
├── NewsError
└── ValidationError
```

---

## Rate Limiting

### Algorithm

The API uses a **sliding window** rate limiting algorithm:

1. Requests are tracked with timestamps
2. Each endpoint has its own counter and window
3. Window duration: 1 minute (rolling)
4. When limit is reached, `429 Too Many Requests` is returned

### Configuration

Rate limits are configurable per endpoint:

```bash
API_RATE_LIMIT_SEARCH=30    # 30 requests/minute for /search
API_RATE_LIMIT_FETCH=60     # 60 requests/minute for /fetch
API_RATE_LIMIT_NEWS=30      # 30 requests/minute for /news and /scholar
API_RATE_LIMIT_DEFAULT=100  # Default for unknown endpoints
```

### Response Headers

When rate limited, the response includes:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json
```

### Rate Limit Information

Every response includes rate limit status in `meta`:

```json
"meta": {
  "rate_limit_remaining": 28,
  "rate_limit_reset": 45
}
```

- `rate_limit_remaining`: Requests left in current window
- `rate_limit_reset`: Seconds until the oldest request exits the window

---

## Logging

### Log Directory Structure

```
logs/
└── serp_api/
    ├── api.log           # General application logs
    ├── access.log         # All HTTP requests
    ├── error.log          # ERROR and CRITICAL only
    ├── search.log         # Search endpoint logs
    ├── fetch.log          # Fetch endpoint logs
    ├── news.log           # News endpoint logs
    ├── scholar.log        # Scholar endpoint logs
    ├── serp.log           # SERP library logs
    └── serp_client.log    # SERP client logs
```

### Log Rotation

- **Rotation**: Daily at midnight
- **Retention**: 7 days (configurable via `API_LOG_RETENTION_DAYS`)
- **Format**: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`

### Log Levels

| Level | Description |
|-------|-------------|
| `DEBUG` | Detailed information for debugging |
| `INFO` | General operational information |
| `WARNING` | Potential issues |
| `ERROR` | Errors that prevent some functionality |
| `CRITICAL` | Serious errors preventing the application |

### Request Logging

Each request is logged with:
- Request ID (8-character UUID)
- Endpoint
- Parameters
- Response status
- Execution time

Example log entry:
```
2026-05-12 07:30:00.123 | INFO     | api.routers.search | Search request: query='python' source='google' | request_id=a1b2c3d4
```

---

## CLI Tools

### API Key Management

#### Generate New API Key

```bash
python -m api.cli.keys generate
```

This command:
1. Generates a cryptographically secure random key (43 characters)
2. Hashes the key using bcrypt
3. Displays the plain key (one-time view)
4. Displays the hashed key for `.env` configuration

#### Verify API Key

```python
from api.cli.keys import verify_api_key

# Verify a plain key against a stored hash
is_valid = verify_api_key("plain_key", "hashed_key")
```

---

## Architecture

### Application Structure

```
api/
├── main.py              # FastAPI app factory, lifespan management
├── config.py            # Pydantic Settings for configuration
├── deps.py              # Dependency injection (auth, rate limit)
├── exceptions.py        # Custom exception classes
├── models/
│   ├── requests.py      # SearchRequest, FetchRequest, NewsRequest, ScholarRequest
│   └── responses.py     # APIResponse, ErrorDetail, ResponseMeta
├── routers/
│   ├── health.py        # GET /health
│   ├── search.py        # POST /api/v1/search
│   ├── fetch.py         # POST /api/v1/fetch
│   ├── news.py          # POST /api/v1/news
│   └── scholar.py       # POST /api/v1/scholar
├── utils/
│   └── compression.py   # Content compression for long content truncation
├── middleware/
│   ├── rate_limit.py    # Sliding window rate limiter
│   └── logging_middleware.py  # Centralized logging setup
└── cli/
    └── keys.py          # API key generation tool
```

### Request Flow

```
1. Client Request
       │
       ▼
2. Rate Limit Check (after API key verified)
       │
       ▼
3. Request Pool Semaphore (concurrency limit)
       │
       ▼
4. Endpoint Handler
       │
       ▼
5. SERP Library Call
       │
       ▼
6. Response Construction
       │
       ▼
7. Logging
       │
       ▼
8. Client Response
```

### Dependency Injection

The API uses FastAPI's dependency injection system:

1. **API Key Verification** (`verify_api_key`):
   - Validates `X-API-Key` header
   - Returns verified key or raises 401

2. **Rate Limit Acquisition** (`search_rate_limit`, `fetch_rate_limit`, `news_rate_limit`):
   - Depends on `verify_api_key` (ensures auth before rate limiting)
   - Acquires slot in sliding window
   - Returns `RateLimitInfo`
   - Note: `/scholar` endpoint uses `news_rate_limit` (shares rate limit with `/news`)

3. **Request Pool** (`rate_limited_request`):
   - Acquires global semaphore
   - Limits concurrent requests

### Concurrency Model

- **Global Semaphore**: Limits total concurrent requests (default: 15)
- **Per-Endpoint Rate Limiting**: Sliding window per endpoint (default: 30/min)
- **Async/Await**: Non-blocking I/O for all external calls

---

## Project Structure

```
serp-scraper/
├── serp/                    # Core library
│   ├── __init__.py          # Exports
│   ├── client.py            # SerpClient
│   ├── config.py            # Configuration
│   ├── types.py             # Type definitions
│   ├── google_news.py       # Google News client
│   ├── google_scholar.py    # Google Scholar client
│   ├── parsers.py           # Browser-based parsing (nodriver)
│   ├── http_search.py       # HTTP-based search
│   ├── cache.py             # Disk caching
│   └── utils.py             # Utilities
│
├── api/                     # REST API
│   ├── __init__.py          # Version info
│   ├── main.py              # FastAPI application
│   ├── config.py            # API configuration
│   ├── deps.py              # Dependencies
│   ├── exceptions.py        # Custom exceptions
│   ├── models/              # Pydantic models
│   │   ├── requests.py      # Request schemas
│   │   └── responses.py     # Response schemas
│   ├── routers/             # API routes
│   │   ├── __init__.py
│   │   ├── health.py
│   │   ├── search.py
│   │   ├── fetch.py
│   │   ├── news.py
│   │   └── scholar.py
│   ├── utils/               # Utility functions
│   │   ├── __init__.py
│   │   └── compression.py   # Content compression
│   ├── middleware/          # Middleware
│   │   ├── rate_limit.py
│   │   └── logging_middleware.py
│   └── cli/                 # CLI tools
│       └── keys.py
│
├── tests/                   # Test suite
├── main.py                  # Interactive CLI
├── .env.example            # Environment template
└── README.md               # Project documentation
```

---

## Environment Variable Reference

### Complete `.env` Example

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
API_RATE_LIMIT_NEWS=30      # Also applies to /scholar endpoint
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
API_CORS_ORIGINS=https://example.com,https://app.example.com
```

---

## Security Considerations

1. **API Key Storage**: Always use hashed keys in production
2. **CORS**: Configure specific origins, never use `*` in production
3. **Rate Limiting**: Adjust limits based on your proxy capacity
4. **Logging**: Ensure log files are stored securely
5. **Timeouts**: Set appropriate timeouts to prevent resource exhaustion
6. **No Auth Mode**: Never enable `API_ALLOW_NO_AUTH=true` in production

---

## Troubleshooting

### Common Issues

**1. 401 Unauthorized**
- Verify `X-API-Key` header is present
- Check that `API_KEYS_HASHED` is correctly set
- Ensure plain key matches the stored hash

**2. 429 Too Many Requests**
- Wait for `Retry-After` seconds
- Check `rate_limit_remaining` in response meta
- Increase rate limits if needed

**3. 500 Internal Server Error**
- Check log files in `logs/serp_api/`
- Verify Chrome browser is installed (for browser method)
- Check proxy configuration if using proxies

**4. Slow Response Times**
- Reduce `API_MAX_CONCURRENT_REQUESTS`
- Use HTTP method instead of browser method
- Check network latency to proxies
