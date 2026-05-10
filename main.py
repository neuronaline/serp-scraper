"""Interactive CLI for testing SERP scraper."""

import asyncio
import sys

from serp import SerpClient, ProxyError, CaptchaError, PageTimeoutError, ParseError
from serp.config_pydantic import get_default_config


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

    # Use default config for source and cache settings
    config = get_default_config()
    source = config.search.source  # None means auto (google first, bing fallback)
    use_cache = config.cache.enabled

    source_name = "Google" if source == "google" else ("Bing" if source == "bing" else "Auto (Google → Bing)")
    print(f"\n🔍 Searching [{source_name}]: '{query}' (page {page})")
    print(f"   (source and cache configured via .env)")
    print("-" * 50)

    try:
        async with SerpClient(config=config) as client:
            results = await client.search(
                query,
                page_num=page,
                source=source,
                use_cache=use_cache,
            )

        if not results:
            print("No results found")
            return

        print(f"✓ Found {len(results)} results:\n")
        for r in results:
            print(f"  {r.rank}. {r.title}")
            print(f"     URL: {r.url}")
            if r.description:
                print(f"     Desc: {r.description[:100]}...")
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

    # Use default config
    config = get_default_config()
    use_cache = config.cache.enabled

    print(f"\n📄 Fetching: {url}")
    print(f"   (cache configured via .env: {use_cache})")
    print("-" * 50)

    try:
        async with SerpClient(config=config) as client:
            content = await client.fetch(url, use_cache=use_cache)

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


async def interactive_menu():
    """Main interactive menu."""
    print("\n" + "=" * 50)
    print("  SERP SCRAPER - TEST TOOL")
    print("=" * 50)
    print("\n1. SERP Search")
    print("2. URL Fetch")
    print("3. Exit")

    choice = input("\nSelect option: ").strip()

    if choice == "1":
        await test_serp()
    elif choice == "2":
        await test_fetch()
    elif choice == "3":
        print("Goodbye!")
        sys.exit(0)
    else:
        print("Invalid option")

    # Continue
    input("\nPress Enter to continue...")
    await interactive_menu()


def main():
    """Entry point."""
    print("\n🔧 SERP Scraper Test Tool")
    print("   Configure via .env file (see .env.example)")

    try:
        asyncio.run(interactive_menu())
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")


if __name__ == "__main__":
    main()