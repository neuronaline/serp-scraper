"""Interactive CLI for testing SERP scraper."""

import argparse
import asyncio
import signal
import sys
from typing import Optional, Set

from serp import SerpClient, GoogleNewsClient, ScholarClient, ProxyError, CaptchaError, PageTimeoutError, ParseError, compress_content
from serp.config_pydantic import get_default_config
from serp.output_formatter import OutputFormatter, OutputError, OUTPUT_TEXT, OUTPUT_JSON

# ── Graceful shutdown helpers ────────────────────────────────────────
_shutdown_requested = False
_running_tasks: Set[asyncio.Task] = set()


def _handle_signal(sig: int, frame) -> None:
    """Handle SIGINT/SIGTERM by cancelling all running tasks."""
    global _shutdown_requested
    if _shutdown_requested:
        # Second Ctrl+C — hard exit
        print("\n\nForced exit.")
        sys.exit(1)
    _shutdown_requested = True
    print("\n\nShutting down gracefully (press Ctrl+C again to force)...")
    for task in _running_tasks:
        task.cancel()


def _run_async_main(coro) -> None:
    """Run the main async function with proper signal handling and cleanup.

    This replaces ``asyncio.run()`` to ensure:
    - SIGINT (Ctrl+C) and SIGTERM are handled for graceful cancellation.
    - All pending tasks are cancelled before the event loop closes.
    - Subprocess transports (Playwright/Firefox) are cleaned up properly,
      avoiding ``RuntimeError: Event loop is closed`` on shutdown.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Register signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s, None))
            except NotImplementedError:
                # Windows or non-main-thread — fall back to add_signal_handler
                signal.signal(sig, _handle_signal)

        main_task = loop.create_task(coro)
        _running_tasks.add(main_task)
        main_task.add_done_callback(_running_tasks.discard)

        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        # Graceful cancellation — normal path on Ctrl+C
        pass
    finally:
        # Cancel any remaining tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        # Shutdown async generators and close the loop cleanly
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        asyncio.set_event_loop(None)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="SERP Scraper Test Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--format", "-f",
        choices=[OUTPUT_TEXT, OUTPUT_JSON],
        default=OUTPUT_TEXT,
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--compress", action="store_true",
        help="Enable content compression for URL fetch (>10K chars)",
    )
    return parser


async def test_serp(args: argparse.Namespace) -> int:
    """Test SERP search."""
    query = input("Enter search query: ").strip()
    if not query:
        print("ERROR: Empty query")
        return 1

    page_input = input("Page number [1]: ").strip()
    page = int(page_input) if page_input else 1

    config = get_default_config()
    source = config.search.source
    use_cache = config.cache.enabled

    source_name = "Google" if source == "google" else ("Bing" if source == "bing" else "Auto (Google → Bing)")
    mode = args.format

    print(f"\nSearching [{source_name}]: '{query}' (page {page})")
    print(f"Output format: {mode}")
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
            if mode == OUTPUT_JSON:
                output = OutputFormatter.format_search_results(
                    results=[],
                    mode=mode,
                    query=query,
                    source=source,
                )
                print(output)
            else:
                print("No results found")
            return 0

        output = OutputFormatter.format_search_results(
            results=results,
            mode=mode,
            query=query,
            source=source,
        )
        print(output)
        return 0

    except ProxyError as e:
        error = OutputError(code="PROXY_ERROR", message=str(e))
        output = OutputFormatter.format_search_results(
            results=[],
            mode=mode,
            query=query,
            source=source,
            error=error,
        )
        print(output)
        return 1
    except CaptchaError as e:
        error = OutputError(code="CAPTCHA_ERROR", message=str(e))
        output = OutputFormatter.format_search_results(
            results=[],
            mode=mode,
            query=query,
            source=source,
            error=error,
        )
        print(output)
        return 1
    except PageTimeoutError as e:
        error = OutputError(code="TIMEOUT_ERROR", message=str(e))
        output = OutputFormatter.format_search_results(
            results=[],
            mode=mode,
            query=query,
            source=source,
            error=error,
        )
        print(output)
        return 1
    except ParseError as e:
        error = OutputError(code="PARSE_ERROR", message=str(e))
        output = OutputFormatter.format_search_results(
            results=[],
            mode=mode,
            query=query,
            source=source,
            error=error,
        )
        print(output)
        return 1
    except Exception as e:
        error = OutputError(code="UNKNOWN_ERROR", message=str(e))
        output = OutputFormatter.format_search_results(
            results=[],
            mode=mode,
            query=query,
            source=source,
            error=error,
        )
        print(output)
        return 1


async def test_fetch(args: argparse.Namespace) -> int:
    """Test URL fetching."""
    url = input("Enter URL to fetch: ").strip()
    if not url:
        print("ERROR: Empty URL")
        return 1

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    use_compress = args.compress

    config = get_default_config()
    use_cache = config.cache.enabled
    mode = args.format

    print(f"\nFetching: {url}")
    print(f"Output format: {mode}")
    if use_compress:
        print("Compression: enabled")
    print("-" * 50)

    try:
        async with SerpClient(config=config) as client:
            content = await client.fetch(url, use_cache=use_cache, prefer_browser=True)

        # Apply compression after fetch so we can report metadata
        was_truncated = False
        original_length: int | None = None
        if use_compress:
            raw_len = len(content)
            content, meta = compress_content(content)
            was_truncated = meta.was_truncated
            original_length = raw_len if was_truncated else None

        output = OutputFormatter.format_fetch(
            content=content,
            url=url,
            char_count=len(content),
            mode=mode,
            was_truncated=was_truncated,
            original_length=original_length,
        )
        print(output)
        return 0

    except ProxyError as e:
        error = OutputError(code="PROXY_ERROR", message=str(e))
        output = OutputFormatter.format_fetch(
            content="",
            url=url,
            char_count=0,
            mode=mode,
            error=error,
        )
        print(output)
        return 1
    except CaptchaError as e:
        error = OutputError(code="CAPTCHA_ERROR", message=str(e))
        output = OutputFormatter.format_fetch(
            content="",
            url=url,
            char_count=0,
            mode=mode,
            error=error,
        )
        print(output)
        return 1
    except PageTimeoutError as e:
        error = OutputError(code="TIMEOUT_ERROR", message=str(e))
        output = OutputFormatter.format_fetch(
            content="",
            url=url,
            char_count=0,
            mode=mode,
            error=error,
        )
        print(output)
        return 1
    except Exception as e:
        error = OutputError(code="UNKNOWN_ERROR", message=str(e))
        output = OutputFormatter.format_fetch(
            content="",
            url=url,
            char_count=0,
            mode=mode,
            error=error,
        )
        print(output)
        return 1


async def test_google_news(args: argparse.Namespace) -> int:
    """Test Google News RSS scraping."""
    news_search_term = input("Enter news search term: ").strip()
    if not news_search_term:
        print("ERROR: Empty search term")
        return 1

    max_input = input("Max results [50]: ").strip()
    max_results = int(max_input) if max_input else 50

    lang_input = input("Language (tr/en) [tr]: ").strip()
    language = lang_input if lang_input in ("tr", "en") else "tr"

    country = "TR" if language == "tr" else "US"
    mode = args.format

    print(f"\nFetching news for: '{news_search_term}'")
    print(f"Language: {language}, Country: {country}")
    print(f"Max results: {max_results}")
    print(f"Output format: {mode}")
    print("-" * 50)

    try:
        async with GoogleNewsClient(language=language, country=country) as client:
            news = await client.get_news(news_search_term, max_results=max_results)

        if not news:
            if mode == OUTPUT_JSON:
                output = OutputFormatter.format_news(
                    news_list=[],
                    search_term=news_search_term,
                    language=language,
                    country=country,
                    mode=mode,
                )
                print(output)
            else:
                print("No news found")
            return 0

        output = OutputFormatter.format_news(
            news_list=news,
            search_term=news_search_term,
            language=language,
            country=country,
            mode=mode,
        )
        print(output)
        return 0

    except ProxyError as e:
        error = OutputError(code="PROXY_ERROR", message=str(e))
        output = OutputFormatter.format_news(
            news_list=[],
            search_term=news_search_term,
            language=language,
            country=country,
            mode=mode,
            error=error,
        )
        print(output)
        return 1
    except PageTimeoutError as e:
        error = OutputError(code="TIMEOUT_ERROR", message=str(e))
        output = OutputFormatter.format_news(
            news_list=[],
            search_term=news_search_term,
            language=language,
            country=country,
            mode=mode,
            error=error,
        )
        print(output)
        return 1
    except Exception as e:
        error = OutputError(code="UNKNOWN_ERROR", message=str(e))
        output = OutputFormatter.format_news(
            news_list=[],
            search_term=news_search_term,
            language=language,
            country=country,
            mode=mode,
            error=error,
        )
        print(output)
        return 1


async def test_scholar(args: argparse.Namespace) -> int:
    """Test Google Scholar search."""
    query = input("Enter search query: ").strip()
    if not query:
        print("ERROR: Empty query")
        return 1

    max_input = input("Max results [50]: ").strip()
    max_results = int(max_input) if max_input else 50

    config = get_default_config()
    use_cache = config.cache.enabled
    mode = args.format

    print(f"\nSearching Scholar: '{query}'")
    print(f"Max results: {max_results}")
    print(f"Output format: {mode}")
    print("-" * 50)

    try:
        async with ScholarClient(config=config) as client:
            results = await client.search_scholar(query, max_results=max_results)

        if not results:
            if mode == OUTPUT_JSON:
                output = OutputFormatter.format_scholar(
                    results=[],
                    query=query,
                    mode=mode,
                )
                print(output)
            else:
                print("No results found")
            return 0

        output = OutputFormatter.format_scholar(
            results=results,
            query=query,
            mode=mode,
        )
        print(output)
        return 0

    except ProxyError as e:
        error = OutputError(code="PROXY_ERROR", message=str(e))
        output = OutputFormatter.format_scholar(
            results=[],
            query=query,
            mode=mode,
            error=error,
        )
        print(output)
        return 1
    except CaptchaError as e:
        error = OutputError(code="CAPTCHA_ERROR", message=str(e))
        output = OutputFormatter.format_scholar(
            results=[],
            query=query,
            mode=mode,
            error=error,
        )
        print(output)
        return 1
    except PageTimeoutError as e:
        error = OutputError(code="TIMEOUT_ERROR", message=str(e))
        output = OutputFormatter.format_scholar(
            results=[],
            query=query,
            mode=mode,
            error=error,
        )
        print(output)
        return 1
    except Exception as e:
        error = OutputError(code="UNKNOWN_ERROR", message=str(e))
        output = OutputFormatter.format_scholar(
            results=[],
            query=query,
            mode=mode,
            error=error,
        )
        print(output)
        return 1


async def interactive_menu(args: argparse.Namespace) -> None:
    """Main interactive menu."""
    while True:
        if _shutdown_requested:
            break
        print("\n" + "=" * 50)
        print("  SERP SCRAPER - TEST TOOL")
        print("=" * 50)
        print(f"\nOutput format: {args.format}")
        print("\n1. SERP Search")
        print("2. URL Fetch")
        print("3. Google News RSS")
        print("4. Google Scholar")
        print("5. Exit")

        choice = input("Select option: ").strip()

        if _shutdown_requested:
            break

        exit_code = 0
        if choice == "1":
            exit_code = await test_serp(args)
        elif choice == "2":
            exit_code = await test_fetch(args)
        elif choice == "3":
            exit_code = await test_google_news(args)
        elif choice == "4":
            exit_code = await test_scholar(args)
        elif choice == "5":
            print("Goodbye!")
            return
        else:
            print("Invalid option")

        if exit_code != 0:
            input("\nPress Enter to continue...")

        input("\nPress Enter to continue...")


def main() -> None:
    """Entry point."""
    parser = create_parser()
    args = parser.parse_args()

    print("\n" + "=" * 50)
    print("  SERP SCRAPER - TEST TOOL")
    print("=" * 50)
    print("\nConfigure via .env file (see .env.example)")

    try:
        _run_async_main(interactive_menu(args))
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")


if __name__ == "__main__":
    main()