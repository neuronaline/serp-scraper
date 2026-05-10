"""Configuration constants for SERP module."""

# Bing URL template
BING_URL_TEMPLATE = "https://www.bing.com/search?q={query}&first={offset}"

# Google URL template
GOOGLE_URL_TEMPLATE = "https://www.google.com/search?q={query}&start={start}"

# Essential Chrome args for headless browsing
ESSENTIAL_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

# User agents for rotation (fresh 2026 versions)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:140.0) Gecko/20100101 Firefox/140.0",
]