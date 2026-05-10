"""Interactive CLI for testing SERP scraper."""

import asyncio
import json
import sys
from pathlib import Path

from serp import search, fetch, search_simple, ProxyError, CaptchaError, PageTimeoutError, ParseError
from serp.config import load_config


# Global proxy file path
_proxy_file = None


def load_proxies():
    """Load proxy file path."""
    global _proxy_file
    default_path = "proxies.json"
    proxy_file = input(f"Proxy file path [{default_path}]: ").strip()
    if not proxy_file:
        proxy_file = default_path

    if not Path(proxy_file).exists():
        print(f"⚠️  Proxy file not found: {proxy_file}")
        print("   Continuing without proxy rotation...")
        _proxy_file = None
        return None

    try:
        config = load_config(proxy_file)
        if config.has_proxies:
            if config._dataimpulse:
                print(f"✓ DataImpulse proxy configured ({config._dataimpulse.get('gateway', 'N/A')})")
            print(f"✓ Loaded {len(config._proxies)} custom proxies")
            _proxy_file = proxy_file
            return proxy_file
        else:
            print("⚠️  No proxies configured in file")
            _proxy_file = None
            return None
    except Exception as e:
        print(f"⚠️  Failed to load proxies: {e}")
        _proxy_file = None
        return None


async def test_serp():
    """Test SERP search."""
    print("\n" + "=" * 50)
    print("SERP SEARCH TEST")
    print("=" * 50)

    query = input("Enter search query: ").strip()
    if not query:
        print("✗ Empty query")
        return

    page_input = input("Page number [1]: ").strip()
    page = int(page_input) if page_input else 1

    # Source selection
    print("\nSelect search source:")
    print("  1. Google (default)")
    print("  2. Bing")
    print("  3. Auto (Google first, Bing fallback)")
    source_choice = input("Source [1]: ").strip()
    source_map = {"1": "google", "2": "bing", "3": None}
    source = source_map.get(source_choice, "google")
    if source_choice == "3":
        source = None

    # Cache selection
    cache_input = input("Use cache [Y/n]: ").strip().lower()
    use_cache = cache_input != "n"

    # Use pre-loaded proxy file if available
    if _proxy_file:
        print(f"Using proxy: {_proxy_file}")
        proxy_file = _proxy_file
    else:
        proxy_file = input(f"Proxy file [proxies.json]: ").strip() or "proxies.json"

    source_name = "Google" if source == "google" else ("Bing" if source == "bing" else "Auto (Google → Bing)")
    print(f"\n🔍 Searching [{source_name}]: '{query}' (page {page})")
    print("-" * 50)

    try:
        # Use browser-based search with nodriver
        results = await search(
            query,
            page_num=page,
            proxy_file=proxy_file,
            headless=False,
            use_cache=use_cache,
            source=source,
        )

        if not results:
            print("No results found")
            return

        print(f"✓ Found {len(results)} results:\n")
        for r in results:
            print(f"  {r['rank']}. {r['title']}")
            print(f"     URL: {r['url']}")
            if r['description']:
                print(f"     Desc: {r['description']}")
            print()

    except ProxyError as e:
        print(f"✗ ProxyError: {e}")
    except CaptchaError as e:
        print(f"✗ CaptchaError: {e}")
    except PageTimeoutError as e:
        print(f"✗ PageTimeoutError: {e}")
    except ParseError as e:
        print(f"✗ ParseError: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")


async def test_fetch():
    """Test URL fetching."""
    print("\n" + "=" * 50)
    print("URL FETCH TEST")
    print("=" * 50)

    url = input("Enter URL to fetch: ").strip()
    if not url:
        print("✗ Empty URL")
        return

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Use pre-loaded proxy file if available
    if _proxy_file:
        print(f"Using proxy: {_proxy_file}")
        proxy_file = _proxy_file
    else:
        proxy_file = input(f"Proxy file [proxies.json]: ").strip() or "proxies.json"

    print(f"\n📄 Fetching: {url}")
    print("-" * 50)

    try:
        content = await fetch(url, proxy_file=proxy_file)

        # Filter out empty/whitespace-only lines for preview
        lines = [l for l in content.split("\n") if l.strip()]
        preview_lines = lines[:30] if lines else ["(no content)"]
        preview = "\n".join(preview_lines)

        print(f"✓ Fetched {len(content)} characters\n")
        print("Preview (first 30 lines):")
        print("-" * 50)
        print(preview)

        if len(lines) > 30:
            print(f"\n... ({len(lines) - 30} more lines)")

    except ProxyError as e:
        print(f"✗ ProxyError: {e}")
    except CaptchaError as e:
        print(f"✗ CaptchaError: {e}")
    except PageTimeoutError as e:
        print(f"✗ PageTimeoutError: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")


def show_proxy_status():
    """Show current proxy configuration."""
    print("\n" + "=" * 50)
    print("PROXY STATUS")
    print("=" * 50)

    # Use pre-loaded proxy file if available
    if _proxy_file:
        proxy_file = _proxy_file
    else:
        proxy_file = input(f"Proxy file [proxies.json]: ").strip() or "proxies.json"

    if not Path(proxy_file).exists():
        print(f"✗ File not found: {proxy_file}")
        return

    try:
        with open(proxy_file) as f:
            data = json.load(f)

        print(f"\n✓ File: {proxy_file}")

        if data.get("dataimpulse"):
            di = data["dataimpulse"]
            print(f"  DataImpulse: {di.get('gateway')}")

        proxies = data.get("proxies", [])
        print(f"  Custom proxies: {len(proxies)}")
        for i, p in enumerate(proxies, 1):
            print(f"    {i}. {p.get('url', 'N/A')}")

    except Exception as e:
        print(f"✗ Error: {e}")


async def interactive_menu():
    """Main interactive menu."""
    print("\n" + "=" * 50)
    print("  SERP SCRAPER - TEST TOOL")
    print("=" * 50)
    print("\n1. SERP Search")
    print("2. URL Fetch")
    print("3. Proxy Status")
    print("4. Exit")

    choice = input("\nSelect option: ").strip()

    if choice == "1":
        await test_serp()
    elif choice == "2":
        await test_fetch()
    elif choice == "3":
        show_proxy_status()
    elif choice == "4":
        print("Goodbye!")
        sys.exit(0)
    else:
        print("Invalid option")

    # Continue
    input("\nPress Enter to continue...")
    await interactive_menu()


def main():
    """Entry point."""
    print("\n🔧 Loading proxy configuration...")
    load_proxies()

    try:
        asyncio.run(interactive_menu())
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")


if __name__ == "__main__":
    main()
