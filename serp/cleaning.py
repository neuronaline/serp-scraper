"""HTML and Markdown cleaning module.

This module provides unified cleaning functions for web content extraction:
- clean_html(): Remove noise elements from HTML using regex (no BS4 dependency)
- clean_markdown(): Post-process markdown to normalize formatting

CLEANING STRATEGY (Conservative + Regex-based):
================================================
Removes known non-content elements from HTML before markdown conversion.

REMOVED ELEMENTS (Definitely Non-Visible Content):
- <script>, <style>, <noscript>: JavaScript/CSS code, no visible content
- <iframe>, <embed>, <object>: Embedded content (ads, videos)
- <meta>, <link>: Metadata, no visible content
- <svg>: Vector graphics (not text content)
- HTML comments: Non-visible content
- Elements with hidden attribute, display:none, visibility:hidden

REMOVED SEMANTIC CONTAINERS (Mostly Noise):
- <nav>, <footer>, <header>, <aside>: Navigation/footer/header/sidebar content
- <menu>: UI elements that are not main content

PRESERVED CONTENT (Critical):
- <article>, <main>, <body>: Primary content containers
- <h1>-<h6>: Headlines
- <p>, <ul>, <ol>, <li>: Body text and lists
- <table>, <tr>, <th>, <td>: Tabular data
- <blockquote>: Quotes
- <pre>, <code>: Code blocks
- <a>, <img>: Links and images (with alt text)
- <figure>, <figcaption>: Figures and captions
"""

import html
import re


def clean_html(html_content: str) -> str:
    """Clean HTML content using regex-based removal of non-content elements.

    Completely removes script, style, noscript, iframe, embed, object, SVG,
    nav, footer, header, aside, menu, meta, link, and hidden elements.
    Does NOT use BeautifulSoup4 — pure regex for zero extra dependency.

    Args:
        html_content: Raw HTML string

    Returns:
        Cleaned HTML string
    """
    if not html_content:
        return html_content

    # Remove script, style, noscript, iframe, embed, object, svg (with content)
    for tag in ('script', 'style', 'noscript', 'iframe', 'embed', 'object', 'svg'):
        html_content = re.sub(
            rf'<{tag}[^>]*>.*?</{tag}>',
            '',
            html_content,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Remove semantic containers that typically contain navigation/footer noise
    for tag in ('nav', 'footer', 'header', 'aside', 'menu'):
        html_content = re.sub(
            rf'<{tag}[^>]*>.*?</{tag}>',
            '',
            html_content,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Remove meta and link tags (they don't contribute to visible content)
    html_content = re.sub(r'<meta[^>]*>', '', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'<link[^>]*>', '', html_content, flags=re.IGNORECASE)

    # Remove HTML comments
    html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)

    # Remove elements with hidden attribute
    html_content = re.sub(
        r'<[^>]*\bhidden\b[^>]*>.*?</[^>]+>',
        '',
        html_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Remove elements with display:none or visibility:hidden inline styles
    # This handles: style="display:none", style="visibility:hidden"
    html_content = re.sub(
        r'<[^>]*style="[^"]*(?:display:\s*none|visibility:\s*hidden)[^"]*"[^>]*>.*?</[^>]+>',
        '',
        html_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Remove empty paragraphs that are just spacers
    html_content = re.sub(
        r'<p[^>]*>\s*(?:<br\s*/?>)?\s*</p>',
        '',
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return html_content


def clean_markdown(markdown: str) -> str:
    """Clean Markdown content after HTML-to-Markdown conversion.

    Normalizes formatting and removes residual noise:
    - Excessive whitespace normalized
    - Unicode whitespace characters replaced
    - HTML entities decoded
    - Multiple blank lines reduced

    Args:
        markdown: Markdown string from markdownify

    Returns:
        Cleaned Markdown string
    """
    # Decode common HTML entities that markdownify might miss
    result = html.unescape(markdown)

    # Replace non-breaking spaces and other Unicode whitespace with regular space
    result = result.replace("\u00a0", " ")  # NBSP
    result = result.replace("\u200b", " ")  # Zero-width space (replace with space, not remove)
    result = result.replace("\u2003", " ")  # Em space
    result = result.replace("\u2002", " ")  # En space
    result = result.replace("\u2009", " ")  # Thin space

    # Normalize multiple newlines first (this is safe for all content)
    result = re.sub(r"\n{3,}", "\n\n", result)  # 3+ newlines -> 2

    # Split into lines and process each line
    # This preserves indentation in indented code blocks
    lines = result.split("\n")
    cleaned_lines = []

    for line in lines:
        # Check if this looks like a code block line (indented with 4+ spaces or starts with ```)
        is_code_line = line.startswith("    ") or line.startswith("\t") or line.startswith("```")

        if is_code_line:
            # Preserve code block lines as-is (don't trim or normalize spaces)
            cleaned_lines.append(line)
        else:
            # For non-code lines: normalize multiple spaces to single, then trim
            normalized = re.sub(r"[ \t]+", " ", line)
            cleaned_lines.append(normalized.strip())

    result = "\n".join(cleaned_lines)

    # Remove leading/trailing blank lines
    result = result.strip()

    return result
