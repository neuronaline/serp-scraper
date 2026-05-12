⚠️ **WARNING**: This project is in early development stages.

# SERP Scraper

A powerful, async Python library for scraping Google and Bing Search Engine Results Pages (SERPs) with proxy rotation, intelligent caching, and stealth browsing.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Dual Search Methods**: Browser-based (`nodriver`) and HTTP-based (`httpx`) scraping
- **Google News RSS**: Scrape news articles via Google News RSS feeds
- **Proxy Rotation**: DataImpulse and custom proxy support with automatic rotation
- **Intelligent Caching**: Disk-based caching with configurable TTL
- **CAPTCHA Handling**: Automatic detection with retry logic and exponential backoff
- **Type Safety**: Full type annotations with Pydantic validation
- **Async/Await**: Modern asynchronous API design
- **Environment Config**: `.env` file support for configuration
- **CLI Tool**: Interactive command-line interface for testing
- **Dual Output Format**: Text (human-readable) and JSON (LLM-friendly) output
- **REST API**: Optional FastAPI-based REST API with rate limiting and authentication

## Installation

### Basic Installation

```bash
pip install serp-scraper
```

### From Source

```bash
git clone https://github.com/neuronaline/serp-scraper.git
cd serp-scraper
pip install -e .
```

### With Dependencies

```bash
pip install serp-scraper[dev]  # With dev tools
pip install serp-scraper[test] # With test dependencies
pip install serp-scraper[api]  # With REST API (FastAPI)
```

## Requirements

- Python 3.10 or higher
- Google Chrome browser installed

## Quick Start

### Recommended: Using SerpClient

```python
import asyncio
from serp import SerpClient

async def main():
    async with SerpClient() as client:
        results = await client.search("python programming")

        for r in results:
            print(f"{r.rank}. {r.title}")
            print(f"   {r.url}")
            print(f"   {r.description[:100]}...")

asyncio.run(main())
```

### Quick Functions

For simple use cases without creating a client:

```python
import asyncio
from serp import quick_search, quick_fetch

async def main():
    # Search
    results = await quick_search("web scraping")
    print(f"Found {len(results)} results")

    # Fetch URL
    content = await quick_fetch("https://example.com")
    print(content[:500])

asyncio.run(main())
```

### Google News RSS

Scrape news articles using Google News RSS feeds:

```python
import asyncio
from serp import GoogleNewsClient

async def main():
    async with GoogleNewsClient(language="en", country="US") as client:
        news = await client.get_news("Tesla", max_results=20)

        for r in news:
            print(f"{r.title}")
            print(f"  Source: {r.source}")
            print(f"  URL: {r.url}")
            print(f"  Date: {r.published}")

asyncio.run(main())
```

Or use the quick function:

```python
import asyncio
from serp import quick_news

async def main():
    news = await quick_news("Tesla", language="en", country="US", max_results=20)
    print(f"Found {len(news)} news articles")

asyncio.run(main())
```

### URL Fetching

```python
import asyncio
from serp import SerpClient

async def main():
    async with SerpClient() as client:
        # Fetch page content as Markdown
        content = await client.fetch("https://example.com")
        print(content)

asyncio.run(main())
```

### Using with Configuration

```python
import asyncio
from serp import SerpClient, SerpConfig

# Create configured client
config = SerpConfig(
    log_level="DEBUG",
    max_retries=5,
    cache_ttl=3600,  # 1 hour
    cache_enabled=True,
)

async with SerpClient(config) as client:
    results = await client.search("python tutorial")
```

### Environment Variables (.env file)

Create a `.env` file in your project. Copy from `.env.example` for all options:

```bash
# DataImpulse Proxy (recommended)
SERP_DATAIMPULSE_GATEWAY=http://gw.dataimpulse.com:10001
SERP_DATAIMPULSE_USER=your_username
SERP_DATAIMPULSE_PASS=your_password

# Custom Proxies (comma-separated)
SERP_CUSTOM_PROXIES=http://user:pass@proxy1.com:8080,socks5://proxy2.com:1080

# Proxy Strategy: "random" or "dataimpulse_first"
SERP_PROXY_STRATEGY=dataimpulse_first

# Logging
SERP_LOG_LEVEL=WARNING
SERP_DEBUG=false

# Cache
SERP_CACHE_ENABLED=true
SERP_CACHE_DIR=.cache/serp
SERP_CACHE_TTL=86400

# Search
SERP_DEFAULT_SOURCE=auto  # "google", "bing", or "auto"
SERP_HEADLESS=false
SERP_TIMEOUT=30

# Retry
SERP_MAX_RETRIES=3
SERP_RETRY_DELAY_MIN=0.5
SERP_RETRY_DELAY_MAX=2.0
SERP_EXPONENTIAL_BACKOFF=false

# Custom User Agent (optional)
SERP_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
```

## Configuration

### SerpConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `custom_proxies` | str | `""` | Comma-separated proxy URLs from env |
| `proxy_strategy` | str | `"dataimpulse_first"` | Proxy selection: "random" or "dataimpulse_first" |
| `dataimpulse_gateway` | str | `None` | DataImpulse gateway URL |
| `dataimpulse_user` | str | `None` | DataImpulse username |
| `dataimpulse_pass` | str | `None` | DataImpulse password |
| `log_level` | str | `"WARNING"` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `max_retries` | int | `3` | Maximum retry attempts (1-10) |
| `retry_delay_min` | float | `0.5` | Minimum retry delay in seconds |
| `retry_delay_max` | float | `2.0` | Maximum retry delay in seconds |
| `exponential_backoff` | bool | `false` | Use exponential backoff |
| `timeout` | int | `30` | Request timeout in seconds (5-120) |
| `cache_enabled` | bool | `true` | Enable/disable caching |
| `cache_dir` | str | `".cache/serp"` | Cache directory path |
| `cache_ttl` | int | `86400` | Cache TTL in seconds (min 60) |
| `default_source` | str | `"auto"` | Default search source: "google", "bing", or "auto" |
| `headless` | bool | `false` | Run browser in headless mode |
| `user_agent` | str | `None` | Custom user agent string |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SERP_DATAIMPULSE_GATEWAY` | DataImpulse gateway URL | - |
| `SERP_DATAIMPULSE_USER` | DataImpulse username | - |
| `SERP_DATAIMPULSE_PASS` | DataImpulse password | - |
| `SERP_CUSTOM_PROXIES` | Comma-separated proxy URLs | - |
| `SERP_PROXY_STRATEGY` | Proxy selection strategy | `dataimpulse_first` |
| `SERP_LOG_LEVEL` | Logging level | `WARNING` |
| `SERP_CACHE_DIR` | Cache directory path | `.cache/serp` |
| `SERP_CACHE_TTL` | Default cache TTL in seconds | `86400` |
| `SERP_CACHE_ENABLED` | Enable/disable caching | `true` |
| `SERP_MAX_RETRIES` | Maximum retry attempts | `3` |
| `SERP_RETRY_DELAY_MIN` | Minimum retry delay (seconds) | `0.5` |
| `SERP_RETRY_DELAY_MAX` | Maximum retry delay (seconds) | `2.0` |
| `SERP_EXPONENTIAL_BACKOFF` | Use exponential backoff | `false` |
| `SERP_TIMEOUT` | Request timeout in seconds | `30` |
| `SERP_DEBUG` | Enable debug logging | `false` |
| `SERP_DOTENV_FILE` | Path to .env file | Auto-detect |

## API Reference

### SerpClient

The recommended high-level interface for using the library.

```python
from serp import SerpClient

client = SerpClient(
    headless=False,              # Optional
    use_cache=True,             # Optional
    cache_ttl=86400,            # Optional
    source=None,                # Optional: "google", "bing", or None (auto)
    max_retries=3,              # Optional
    timeout=30,                 # Optional
    log_level="WARNING",        # Optional
)
```

#### Methods

##### `client.search(query, page_num=1, method=None, source=None, use_cache=None)`

Search for a query and return results.

**Parameters:**
- `query` (str): Search query string
- `page_num` (int): Page number (1-based), defaults to 1
- `method` (str): Search method - `"browser"` (nodriver), `"http"` (httpx), or `None` (auto)
- `source` (str): Search engine - `"google"`, `"bing"`, or `None` (auto: google first, bing fallback)
- `use_cache` (bool): Whether to use cache. `None` uses client default.

**Returns:**
- `list[SearchResult]`: List of SearchResult objects

**Raises:**
- `ProxyError`: All proxies failed
- `CaptchaError`: CAPTCHA detected after all retries
- `PageTimeoutError`: Page load timeout
- `ParseError`: Failed to parse results

---

##### `client.fetch(url, use_cache=None, prefer_browser=True)`

Fetch a URL and return content as Markdown.

**Parameters:**
- `url` (str): Target URL
- `use_cache` (bool): Whether to use cache. `None` uses client default.
- `prefer_browser` (bool): If True, use browser directly. If False, try HTTP first then fallback to browser.

**Returns:**
- `str`: Page content converted to Markdown

---

### SearchResult

Typed result object returned by search operations.

```python
from serp import SearchResult

result = SearchResult(
    rank=1,
    title="Example Title",
    url="https://example.com",
    description="Example description...",
    source="google"  # or "bing"
)
```

**Attributes:**
- `rank` (int): Position in search results (1-based)
- `title` (str): Result title
- `url` (str): Target URL
- `description` (str): Result snippet/description
- `source` (str): Search engine source ("google" or "bing")

**Methods:**
- `to_dict()`: Convert to dictionary for backward compatibility

---

### Quick Functions

Module-level convenience functions using default client:

```python
from serp import quick_search, quick_fetch, quick_search_http

# Quick search (auto method)
results = await quick_search("query")

# HTTP-based search only
results = await quick_search_http("query")

# Fetch URL
content = await quick_fetch("https://example.com")
```

---

### GoogleNewsClient

Client for scraping Google News via RSS feeds.

```python
from serp import GoogleNewsClient

client = GoogleNewsClient(
    language="tr",        # Language code (tr, en, etc.)
    country="TR",        # Country code (TR, US, etc.)
    time_range="d",      # Time range: "h" (hour), "d" (day), "w" (week), "m" (month)
)
```

#### Methods

##### `client.get_news(query, max_results=50, queries=None)`

Get news articles for a search term.

**Parameters:**
- `query` (str): Search term to find news for
- `max_results` (int): Maximum number of results (default: 50)
- `queries` (list[str]): Custom list of queries to use

**Returns:**
- `list[NewsResult]`: List of NewsResult objects

##### `quick_news(query, max_results=50, language="tr", country="TR")`

Convenience function for quick news retrieval.

```python
from serp import quick_news

news = await quick_news("Tesla", max_results=20, language="en", country="US")
```

---

### NewsResult

Typed result object for Google News articles.

```python
from serp import NewsResult

result = NewsResult(
    title="Tesla announces new model",
    url="https://news.google.com/rss/articles/...",
    original_url="https://example.com/article",
    published=datetime(2026, 5, 11, 8, 0, 0),
    source="BBC",
    description="Tesla unveiled...",
    query="Tesla"
)
```

**Attributes:**
- `title` (str): News headline
- `url` (str): Google News RSS URL
- `original_url` (str): Original article URL (extracted from description)
- `published` (datetime): Publication date
- `source` (str): News source name (e.g., "BBC", "NTV")
- `description` (str): News summary/snippet
- `query` (str): Search query that returned this result

**Methods:**
- `to_dict()`: Convert to dictionary

---

### NewsSettings

Configuration for Google News scraping.

```python
from serp import NewsSettings

settings = NewsSettings(
    language="tr",    # Language code
    country="TR",     # Country code
    time_range="d",   # Time range: "h", "d", "w", "m"
)
```

**Attributes:**
- `language` (str): Language code (default: "tr")
- `country` (str): Country code (default: "TR")
- `time_range` (str): Time range filter (default: "d")

---

### OutputFormatter

Structured output formatting for CLI tools and LLM integration.

```python
from serp import OutputFormatter, OUTPUT_TEXT, OUTPUT_JSON

# Format search results
output = OutputFormatter.format_search_results(
    results=search_results,
    mode=OUTPUT_JSON,
    query="python tutorial",
    source="google",
)

# Format news results
output = OutputFormatter.format_news(
    news_list=news_results,
    mode=OUTPUT_JSON,
    search_term="Tesla",
    language="en",
    country="US",
)

# Format fetch results
output = OutputFormatter.format_fetch(
    content=page_content,
    url="https://example.com",
    char_count=len(page_content),
    mode=OUTPUT_JSON,
)
```

**Constants:**
- `OUTPUT_TEXT`: Text output mode (human-readable)
- `OUTPUT_JSON`: JSON output mode (machine-parseable)

**Classes:**
- `OutputFormatter`: Main interface with static `format_*` methods
- `TextFormatter`: Human-readable text formatting
- `JSONFormatter`: JSON output formatting
- `OutputError`: Structured error representation

---

### Utility Functions

#### `set_log_level(level)`

Set the log level for all serp loggers.

```python
from serp import set_log_level

set_log_level("DEBUG")  # Enable debug logging
set_log_level("WARNING")  # Only show warnings and errors
```

---

### Exceptions

| Exception | Description |
|-----------|-------------|
| `ProxyError` | All proxies failed |
| `CaptchaError` | CAPTCHA could not be solved after retries |
| `PageTimeoutError` | Page load timeout |
| `ParseError` | Failed to parse results |

---

### Constants

| Constant | Description |
|----------|-------------|
| `MAX_RETRIES` | Maximum retry attempts (default: 3) |
| `TIMEOUT_MS` | Page timeout in milliseconds (default: 30000) |
| `USER_AGENTS` | List of user agent strings for rotation |

---

## Interactive CLI

The package includes an interactive CLI tool for testing:

```bash
python main.py
python main.py --format json  # JSON output for LLM integration
python main.py -f text        # Human-readable text output (default)
```

Features:
- SERP Search testing
- URL Fetch testing
- Google News RSS testing
- Dual output format (text/JSON)
- Proxy status checking

## REST API (Optional)

The package includes an optional FastAPI-based REST API for programmatic access.

### Installation

```bash
pip install serp-scraper[api]
```

### Running the API

```bash
python -m api.main
# Or with uvicorn directly:
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### API Endpoints

- `GET /health` - Health check
- `POST /api/v1/search` - Search SERP results
- `POST /api/v1/fetch` - Fetch URL content
- `POST /api/v1/news` - Get Google News articles
- `GET /api/v1/keys` - List API keys (admin)
- `POST /api/v1/keys` - Create API key (admin)

### Authentication

The API uses API key authentication. Set the `X-API-Key` header in your requests.

### Rate Limiting

The API includes rate limiting middleware to prevent abuse.

## Project Structure

```
serp-scraper/
├── serp/                    # Main package
│   ├── __init__.py          # Exports and API
│   ├── client.py            # SerpClient and quick functions
│   ├── config.py            # Configuration constants
│   ├── config_pydantic.py   # Pydantic-based configuration
│   ├── types.py             # Type definitions (SearchResult, etc.)
│   ├── google_news.py       # Google News RSS client
│   ├── search.py            # Browser-based search
│   ├── fetch.py             # URL fetch functionality
│   ├── simple.py            # HTTP-based search
│   ├── parsers.py           # Result parsing logic
│   ├── cache.py             # Disk-based caching
│   ├── output_formatter.py  # Text and JSON output formatting
│   └── utils.py             # Utilities and helpers
├── api/                     # REST API (optional)
│   ├── main.py              # FastAPI application
│   ├── config.py            # API configuration
│   ├── deps.py              # Dependencies
│   ├── exceptions.py        # Custom exceptions
│   ├── models/              # Pydantic models
│   │   ├── requests.py      # Request models
│   │   └── responses.py     # Response models
│   ├── routers/             # API routes
│   │   ├── __init__.py
│   │   ├── health.py        # Health check endpoint
│   │   ├── search.py        # Search endpoints
│   │   ├── fetch.py         # Fetch endpoints
│   │   └── news.py          # News endpoints
│   ├── middleware/          # Middleware
│   │   ├── rate_limit.py    # Rate limiting
│   │   └── logging_middleware.py
│   └── cli/                 # API CLI tools
│       └── keys.py          # API key management
├── tests/                   # Test suite
│   ├── conftest.py          # Test fixtures
│   ├── test_serp.py
│   ├── test_google_news.py
│   ├── test_cache.py
│   └── api/                 # API tests
├── main.py                  # Interactive CLI tool
├── .env.example            # Environment variables template
├── pyproject.toml          # Project metadata
└── README.md               # This file
```

## Testing

Run the test suite:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=serp --cov-report=html
```

Run specific test file:

```bash
pytest tests/test_serp.py
```

## Architecture

### Search Flow

1. Check cache for existing results (if `use_cache=True`)
2. Load proxy configuration from file or environment
3. Select random proxy (or DataImpulse if configured)
4. Create browser with stealth settings (browser method) or use HTTP client (http method)
5. Navigate to search URL
6. Wait for results to load
7. Check for CAPTCHA
8. Parse organic results
9. Cache results before returning

### Search Methods

**Browser Method (`method="browser"`)**:
- Uses `nodriver` for stealth Chrome automation
- More reliable, harder to detect
- Slower due to browser overhead

**HTTP Method (`method="http"`)**:
- Uses `httpx` for direct HTTP requests
- Faster, less resource intensive
- May be blocked more easily

### Caching

The caching system uses a disk-based approach:

- Cache entries stored as JSON files in `.cache/serp/`
- Keys are SHA256 hashes of query parameters
- Automatic expiration based on TTL
- Can be disabled via `cache_enabled=False` or `SERP_CACHE_ENABLED=false`

## Error Handling

The library provides specific exceptions for different failure modes:

- **ProxyError**: All configured proxies failed or returned errors
- **CaptchaError**: Search engine detected automation and presented CAPTCHA
- **PageTimeoutError**: Page did not load within the timeout period
- **ParseError**: Page loaded but results could not be parsed

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| nodriver | >=0.50.0 | Stealth Chrome automation |
| markdownify | >=0.12.0 | HTML to Markdown conversion |
| httpx | >=0.25.0 | Async HTTP client |
| beautifulsoup4 | >=4.12.0 | HTML parsing |
| pydantic | >=2.0.0 | Configuration validation |
| pydantic-settings | >=2.0.0 | Pydantic settings integration |
| python-dotenv | >=1.0.0 | .env file support |

## API Dependencies (Optional)

Install with `pip install serp-scraper[api]` for REST API support:

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.100.0 | REST API framework |
| uvicorn | >=0.23.0 | ASGI server |
| passlib | >=1.7.4 | Password hashing |

## Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | >=7.0.0 | Testing framework |
| pytest-asyncio | >=0.21.0 | Async test support |
| pytest-cov | >=4.0.0 | Coverage reporting |
| pytest-mock | >=3.10.0 | Mocking utilities |
| pytest-httpserver | >=1.0.0 | HTTP server for testing |
| ruff | >=0.1.0 | Linting |
| mypy | >=1.0.0 | Type checking |
| build | >=1.0.0 | Package building |
| twine | >=4.0.0 | Package publishing |

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

**neuronaline** - flashneuron@proton.me

## Links

- [Repository](https://github.com/neuronaline/serp-scraper)
- [Issue Tracker](https://github.com/neuronaline/serp-scraper/issues)
- [Changelog](https://github.com/neuronaline/serp-scraper/blob/main/CHANGELOG.md)

## Disclaimer

This software is provided for educational and legitimate purposes only. Users are responsible for ensuring their use complies with search engine Terms of Service and applicable laws. The authors assume no liability for misuse of this software.
