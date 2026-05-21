"""HTML and Markdown cleaning module.

This module provides unified cleaning functions for web content extraction:
- clean_html(): Remove noise elements from HTML using BeautifulSoup4
- clean_markdown(): Post-process markdown to normalize formatting
- extract_main_content(): Extract primary content from HTML
- validate_content(): Validate content quality with detailed results

CLEANING STRATEGY (Conservative + Semantic Containers):
=====================================================

REMOVED ELEMENTS (Definitely Non-Visible Content):
- <script>, <style>, <noscript>: JavaScript/CSS code, no visible content
- <iframe>, <embed>, <object>: Embedded content (ads, videos)
- <meta>, <link>: Metadata, no visible content
- HTML comments: Non-visible content
- Hidden elements: hidden attribute, display:none, visibility:hidden

REMOVED SEMANTIC CONTAINERS (Mostly Noise):
- <nav>, <footer>, <header>, <aside>: Navigation/footer/header/sidebar content
- <menu>, <sidebar>, <advertisement>: UI elements that are not main content

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
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ValidationResult:
    """Result of content validation.

    Attributes:
        is_valid: Whether content passes validation checks
        content_length: Character length of the content
        element_counts: Count of key elements (p, h2, table, etc.)
        warnings: List of warning messages
        errors: List of error messages
    """

    is_valid: bool
    content_length: int
    element_counts: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def clean_html(html_content: str) -> str:
    """Clean HTML content using BeautifulSoup4.

    Removes noise elements while preserving main content structure.

    Args:
        html_content: Raw HTML string

    Returns:
        Cleaned HTML string
    """
    from bs4 import BeautifulSoup, Comment

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script and style elements completely (they contain non-visible noise)
    for element in soup.find_all(["script", "style", "noscript", "iframe", "embed", "object"]):
        element.decompose()

    # Remove semantic containers that typically contain navigation/footer noise
    for tag in ["nav", "footer", "header", "aside", "menu", "sidebar", "advertisement"]:
        for element in soup.find_all(tag):
            element.decompose()

    # Remove meta and link tags (they don't contribute to visible content)
    for element in soup.find_all(["meta", "link"]):
        element.decompose()

    # Remove comments (may contain conditional IE code, etc.)
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove hidden elements
    # Elements with hidden attribute
    for element in soup.find_all(attrs={"hidden": True}):
        element.decompose()

    # Elements with display:none or visibility:hidden inline styles
    for element in soup.find_all(
        style=lambda s: s and ("display:none" in s.lower() or "visibility:hidden" in s.lower())
    ):
        element.decompose()

    # Remove empty paragraphs and breaks that create noise
    for p in soup.find_all("p"):
        if not p.get_text(strip=True):
            # Don't remove all empty tags, just those that are clearly spacers
            if p.find("br") or not p.contents:
                # Check if it's truly empty (no meaningful content)
                if not p.stripped_strings:
                    p.decompose()

    # Remove elements with noise-indicating class names (conservative approach)
    # Only remove if the entire element is likely noise
    noise_patterns = [
        "sidebar", "nav", "menu", "footer", "header", "advertisement",
        "social", "share", "comment", "breadcrumb", "pagination"
    ]
    for element in soup.find_all(class_=lambda x: x and any(
        pattern in str(x).lower() for pattern in noise_patterns
    )):
        # Only decompose if it doesn't contain article/main content
        # Check if it's a high-level container (div, section, aside)
        if element.name in ("div", "section", "aside", "span"):
            # Check if it contains any meaningful content tags
            meaningful_tags = element.find(["article", "main", "p", "h1", "h2", "h3", "table"])
            if not meaningful_tags:
                element.decompose()

    return str(soup)


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


def extract_main_content(html_content: str) -> str:
    """Extract main content from HTML using semantic priority.

    Priority order: <article> > <main> > <body>

    This function attempts to extract the primary content area,
    falling back to body if no article/main is found.

    Args:
        html_content: Raw HTML string

    Returns:
        HTML string containing only main content area
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, "html.parser")

    # Try article first
    article = soup.find("article")
    if article:
        return str(article)

    # Try main
    main = soup.find("main")
    if main:
        return str(main)

    # Fall back to body
    body = soup.find("body")
    if body:
        return str(body)

    # Last resort: return original
    return html_content


def validate_content(
    content: str,
    min_length: int = 100,
    min_paragraphs: int = 1,
    min_headings: int = 0,
) -> ValidationResult:
    """Validate content quality and sufficiency.

    Performs comprehensive validation:
    - Pre-cleaning: HTML parseability, encoding issues
    - Post-cleaning: Length, element counts, quality checks

    Args:
        content: Content string to validate (HTML or Markdown)
        min_length: Minimum character length (default: 100)
        min_paragraphs: Minimum number of paragraphs expected
        min_headings: Minimum number of headings expected

    Returns:
        ValidationResult with validation outcome and details
    """
    warnings = []
    errors = []
    element_counts = {}

    # Strip content for length calculation
    stripped_content = content.strip()
    content_length = len(stripped_content)

    # Check for BOM bytes
    if stripped_content.startswith("\ufeff"):
        warnings.append("BOM bytes detected at start of content")
        content_length -= 1

    # Check for encoding issues (common problematic patterns)
    if "\ufffd" in content:
        warnings.append("Replacement character (U+FFFD) detected - possible encoding issues")

    # Minimum length check
    if content_length < min_length:
        errors.append(
            f"Content too short: {content_length} chars (minimum: {min_length})"
        )

    # Parse as HTML to count elements if content looks like HTML
    from bs4 import BeautifulSoup

    is_html = "<" in content and ">" in content
    if is_html:
        try:
            soup = BeautifulSoup(content, "html.parser")

            # Count key elements
            element_counts["p"] = len(soup.find_all("p"))
            element_counts["h1"] = len(soup.find_all("h1"))
            element_counts["h2"] = len(soup.find_all("h2"))
            element_counts["h3"] = len(soup.find_all("h3"))
            element_counts["h4"] = len(soup.find_all("h4"))
            element_counts["h5"] = len(soup.find_all("h5"))
            element_counts["h6"] = len(soup.find_all("h6"))
            element_counts["table"] = len(soup.find_all("table"))
            element_counts["ul"] = len(soup.find_all("ul"))
            element_counts["ol"] = len(soup.find_all("ol"))
            element_counts["li"] = len(soup.find_all("li"))
            element_counts["blockquote"] = len(soup.find_all("blockquote"))
            element_counts["pre"] = len(soup.find_all("pre"))
            element_counts["code"] = len(soup.find_all("code"))
            element_counts["article"] = len(soup.find_all("article"))
            element_counts["main"] = len(soup.find_all("main"))

            total_headings = (
                element_counts["h1"]
                + element_counts["h2"]
                + element_counts["h3"]
                + element_counts["h4"]
                + element_counts["h5"]
                + element_counts["h6"]
            )
            element_counts["total_headings"] = total_headings

            # Check for empty content
            if element_counts["p"] == 0 and total_headings == 0:
                warnings.append("No paragraphs or headings found - content may be mostly noise")

            # Check paragraph count
            if element_counts["p"] < min_paragraphs:
                warnings.append(
                    f"Few paragraphs found: {element_counts['p']} "
                    f"(expected at least {min_paragraphs})"
                )

            # Check heading count
            if total_headings < min_headings:
                warnings.append(
                    f"Few headings found: {total_headings} "
                    f"(expected at least {min_headings})"
                )

            # Check for excessive noise elements
            nav_count = len(soup.find_all("nav"))
            footer_count = len(soup.find_all("footer"))
            aside_count = len(soup.find_all("aside"))
            noise_ratio = (nav_count + footer_count + aside_count) / max(1, content_length) * 1000

            if noise_ratio > 0.5:  # More than 0.5 noise elements per 1000 chars is suspicious
                warnings.append(
                    f"High noise element ratio: nav={nav_count}, footer={footer_count}, aside={aside_count}"
                )

        except Exception as e:
            warnings.append(f"Could not parse HTML for element counting: {e}")

    # Determine validity
    is_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_valid,
        content_length=content_length,
        element_counts=element_counts,
        warnings=warnings,
        errors=errors,
    )


def clean_html_conservative(html_content: str) -> str:
    """Conservative HTML cleaning - preserves more structure.

    This is a less aggressive cleaning that keeps more semantic elements.
    Use this when you want to preserve more of the original structure.

    Args:
        html_content: Raw HTML string

    Returns:
        Lightly cleaned HTML string
    """
    from bs4 import BeautifulSoup, Comment

    soup = BeautifulSoup(html_content, "html.parser")

    # Only remove elements that are definitely non-content
    for element in soup.find_all(["script", "style", "noscript"]):
        element.decompose()

    # Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove hidden elements
    for element in soup.find_all(attrs={"hidden": True}):
        element.decompose()

    for element in soup.find_all(
        style=lambda s: s and ("display:none" in s.lower() or "visibility:hidden" in s.lower())
    ):
        element.decompose()

    return str(soup)
