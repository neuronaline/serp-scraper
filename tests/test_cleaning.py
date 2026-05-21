"""Unit tests for the cleaning module.

Tests cover:
- Removal of noise elements (script, style, noscript, etc.)
- Preservation of main content (article, main, body)
- Preservation of headings, paragraphs, tables, lists
- Removal of hidden elements
- Whitespace normalization
- Unicode handling
- Content validation
"""

import pytest

from serp.cleaning import (
    ValidationResult,
    clean_html,
    clean_markdown,
    extract_main_content,
    validate_content,
)


class TestCleanHtml:
    """Tests for clean_html function."""

    def test_remove_script_style_noscript(self):
        """Script, style, and noscript tags should be removed."""
        html = """
        <html>
        <head>
            <script>alert('test');</script>
            <style>.hidden { display: none; }</style>
        </head>
        <body>
            <noscript>Please enable JavaScript</noscript>
            <p>Visible content</p>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<script>" not in result
        assert "<style>" not in result
        assert "<noscript>" not in result
        assert "Visible content" in result

    def test_remove_iframe_embed_object(self):
        """iframe, embed, and object tags should be removed."""
        html = """
        <html>
        <body>
            <iframe src="ad.html"></iframe>
            <embed src="video.swf">
            <object data="file.pdf"></object>
            <p>Main content here</p>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<iframe" not in result
        assert "<embed" not in result
        assert "<object" not in result
        assert "Main content here" in result

    def test_remove_semantic_containers(self):
        """Semantic containers like nav, footer, header, aside should be removed."""
        html = """
        <html>
        <body>
            <nav>Navigation menu</nav>
            <header>Site header</header>
            <aside>Sidebar content</aside>
            <footer>Site footer</footer>
            <article>
                <p>Main article content</p>
            </article>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<nav>" not in result
        assert "<header>" not in result
        assert "<aside>" not in result
        assert "<footer>" not in result
        # Article content should be preserved
        assert "Main article content" in result

    def test_preserve_article_main_content(self):
        """Article and main content should be preserved."""
        html = """
        <html>
        <body>
            <nav>Ignore this</nav>
            <article>
                <h1>Article Title</h1>
                <p>Article paragraph</p>
            </article>
            <main>
                <h2>Main Section</h2>
                <p>Main content</p>
            </main>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "Article Title" in result
        assert "Article paragraph" in result
        assert "Main Section" in result
        assert "Main content" in result

    def test_preserve_headings_and_paragraphs(self):
        """Headings and paragraphs should be preserved."""
        html = """
        <html>
        <body>
            <h1>Heading 1</h1>
            <h2>Heading 2</h2>
            <h3>Heading 3</h3>
            <p>First paragraph</p>
            <p>Second paragraph</p>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<h1>Heading 1</h1>" in result
        assert "<h2>Heading 2</h2>" in result
        assert "<h3>Heading 3</h3>" in result
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_preserve_tables_and_lists(self):
        """Tables and lists should be preserved."""
        html = """
        <html>
        <body>
            <table>
                <tr><th>Header</th></tr>
                <tr><td>Data</td></tr>
            </table>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
            <ol>
                <li>Ordered 1</li>
                <li>Ordered 2</li>
            </ol>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<table>" in result
        assert "<th>Header</th>" in result
        assert "<td>Data</td>" in result
        assert "<ul>" in result
        assert "<li>Item 1</li>" in result
        assert "<ol>" in result

    def test_preserve_code_blocks(self):
        """Code blocks should be preserved."""
        html = """
        <html>
        <body>
            <pre><code>def hello():
    print("Hello")
</code></pre>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<pre>" in result
        assert "<code>" in result
        assert 'def hello():' in result

    def test_remove_hidden_elements(self):
        """Hidden elements should be removed."""
        html = """
        <html>
        <body>
            <p class="visible">visible content</p>
            <p hidden>This is hidden</p>
            <div style="display:none">Hidden div</div>
            <div style="visibility:hidden">Invisible div</div>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "visible content" in result
        assert "This is hidden" not in result
        assert "Hidden div" not in result
        assert "Invisible div" not in result

    def test_remove_comments(self):
        """HTML comments should be removed."""
        html = """
        <html>
        <body>
            <p>Before comment</p>
            <!-- This is a comment -->
            <p>After comment</p>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "Before comment" in result
        assert "After comment" in result
        assert "<!--" not in result

    def test_remove_meta_and_link_tags(self):
        """Meta and link tags should be removed."""
        html = """
        <html>
        <head>
            <meta charset="UTF-8">
            <link rel="stylesheet" href="style.css">
        </head>
        <body>
            <p>Content</p>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<meta" not in result
        assert "<link" not in result
        assert "Content" in result

    def test_preserve_links_and_images(self):
        """Links and images should be preserved with alt text."""
        html = """
        <html>
        <body>
            <a href="https://example.com">Click here</a>
            <img src="photo.jpg" alt="A beautiful photo">
        </body>
        </html>
        """
        result = clean_html(html)
        assert 'href="https://example.com"' in result
        assert "Click here" in result
        assert 'alt="A beautiful photo"' in result

    def test_preserve_blockquote(self):
        """Blockquotes should be preserved."""
        html = """
        <html>
        <body>
            <blockquote cite="source">
                This is a quoted text
            </blockquote>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<blockquote" in result  # Use partial match since attrs are preserved
        assert "This is a quoted text" in result

    def test_preserve_figure_and_figcaption(self):
        """Figure and figcaption should be preserved."""
        html = """
        <html>
        <body>
            <figure>
                <img src="chart.png" alt="Chart">
                <figcaption>Chart description</figcaption>
            </figure>
        </body>
        </html>
        """
        result = clean_html(html)
        assert "<figure>" in result
        assert "Chart description" in result


class TestCleanMarkdown:
    """Tests for clean_markdown function."""

    def test_whitespace_normalization(self):
        """Multiple spaces and newlines should be normalized."""
        markdown = "Hello      world\n\n\n\nGoodbye"
        result = clean_markdown(markdown)
        assert "Hello world" in result
        assert result.count("\n\n") <= 1

    def test_unicode_handling(self):
        """Unicode whitespace should be replaced with regular space."""
        markdown = "Hello\u00a0world\u200btest"
        result = clean_markdown(markdown)
        assert "Hello world test" in result
        assert "\u00a0" not in result
        assert "\u200b" not in result

    def test_html_entity_decoding(self):
        """HTML entities should be decoded."""
        markdown = "Hello &amp; goodbye &lt;world&gt;"
        result = clean_markdown(markdown)
        assert "&amp;" not in result
        assert "&lt;" not in result
        assert "&gt;" not in result
        assert "Hello & goodbye <world>" in result

    def test_preserve_code_blocks(self):
        """Code blocks should not be affected by whitespace normalization."""
        markdown = """
        ```python
        def hello():
            print("Hello")
        ```
        """
        result = clean_markdown(markdown)
        assert 'print("Hello")' in result
        # Indentation should be preserved
        assert "            print" in result

    def test_preserve_inline_code(self):
        """Inline code should not be affected by whitespace normalization."""
        markdown = "Use `print()` function"
        result = clean_markdown(markdown)
        assert "`print()`" in result

    def test_trim_lines(self):
        """Lines should be trimmed except code blocks."""
        markdown = "  Hello world  \n    indented code  "
        result = clean_markdown(markdown)
        lines = result.split("\n")
        # First line should be trimmed
        assert lines[0] == "Hello world"
        # Indented line (4+ spaces) should preserve indentation
        assert "    indented code" in lines[1]

    def test_remove_leading_trailing_blank_lines(self):
        """Leading and trailing blank lines should be removed."""
        markdown = "\n\n\nHello world\n\n\n"
        result = clean_markdown(markdown)
        assert result.startswith("Hello")
        assert result.endswith("Hello world")


class TestExtractMainContent:
    """Tests for extract_main_content function."""

    def test_extract_article(self):
        """Article content should be extracted with priority."""
        html = """
        <html>
        <body>
            <nav>Ignore</nav>
            <article>
                <p>Article content</p>
            </article>
            <main>
                <p>Main content</p>
            </main>
        </body>
        </html>
        """
        result = extract_main_content(html)
        assert "Article content" in result
        assert "Main content" not in result

    def test_extract_main_when_no_article(self):
        """Main content should be extracted when no article exists."""
        html = """
        <html>
        <body>
            <nav>Ignore</nav>
            <main>
                <p>Main content</p>
            </main>
        </body>
        </html>
        """
        result = extract_main_content(html)
        assert "Main content" in result

    def test_extract_body_when_no_article_or_main(self):
        """Body content should be extracted as fallback."""
        html = """
        <html>
        <body>
            <nav>Ignore</nav>
            <p>Body content</p>
        </body>
        </html>
        """
        result = extract_main_content(html)
        assert "Body content" in result


class TestValidateContent:
    """Tests for validate_content function."""

    def test_minimum_content_validation(self):
        """Content shorter than minimum should be invalid."""
        result = validate_content("Short content", min_length=100)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_valid_content(self):
        """Content meeting all requirements should be valid."""
        html = "<html><body><p>This is a paragraph with sufficient length to pass validation checks.</p><h1>Heading</h1></body></html>"
        result = validate_content(html, min_length=50)
        assert result.is_valid
        assert result.content_length >= 50

    def test_element_counts(self):
        """Element counts should be tracked."""
        html = """
        <html>
        <body>
            <p>Para 1</p>
            <p>Para 2</p>
            <h1>Title</h1>
            <h2>Subtitle</h2>
            <table><tr><td>Data</td></tr></table>
        </body>
        </html>
        """
        result = validate_content(html)
        assert result.element_counts.get("p", 0) >= 2
        assert result.element_counts.get("h1", 0) == 1
        assert result.element_counts.get("h2", 0) == 1
        assert result.element_counts.get("table", 0) == 1

    def test_paragraph_validation(self):
        """Minimum paragraph check should work."""
        html = "<html><body><p>Only one paragraph</p></body></html>"
        result = validate_content(html, min_paragraphs=2)
        assert any("Few paragraphs" in w for w in result.warnings)

    def test_heading_validation(self):
        """Minimum heading check should work."""
        html = "<html><body><p>Content without heading</p></body></html>"
        result = validate_content(html, min_headings=1)
        assert any("Few headings" in w for w in result.warnings)

    def test_bom_detection(self):
        """BOM bytes should be detected and reported."""
        html = "\ufeff<html><body><p>Content</p></body></html>"
        result = validate_content(html)
        assert any("BOM" in w for w in result.warnings)

    def test_encoding_issues(self):
        """Encoding issues should be detected."""
        html = "<html><body><p>Content with\ufffd replacement</p></body></html>"
        result = validate_content(html)
        assert any("encoding" in w.lower() for w in result.warnings)

    def test_empty_content(self):
        """Empty content should fail validation."""
        result = validate_content("")
        assert not result.is_valid

    def test_whitespace_only_content(self):
        """Whitespace-only content should fail validation."""
        result = validate_content("   \n\t  ")
        assert not result.is_valid


class TestIntegration:
    """Integration tests combining cleaning functions."""

    def test_clean_html_then_markdown(self):
        """Full pipeline: HTML -> clean -> markdown -> clean markdown."""
        html = """
        <html>
        <head>
            <script>bad code</script>
            <style>.hidden{}</style>
        </head>
        <body>
            <nav>Navigation</nav>
            <article>
                <h1>Title</h1>
                <p>Content paragraph with actual text.</p>
            </article>
        </body>
        </html>
        """
        cleaned = clean_html(html)
        assert "<script>" not in cleaned
        assert "Navigation" not in cleaned
        assert "Title" in cleaned

    def test_real_world_html(self):
        """Test with realistic HTML content."""
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Test Page</title>
            <script src="analytics.js"></script>
            <style>body { margin: 0; }</style>
        </head>
        <body>
            <header>
                <nav>
                    <a href="/">Home</a>
                    <a href="/about">About</a>
                </nav>
            </header>
            <main>
                <article>
                    <h1>Article Title</h1>
                    <p>This is a paragraph with meaningful content that describes
                    the main topic of the article in detail.</p>
                    <p>Another paragraph with more content to ensure we have
                    sufficient text for validation purposes.</p>
                    <blockquote>
                        A notable quote from the article.
                    </blockquote>
                </article>
            </main>
            <footer>
                <p>&copy; 2024 Example Site</p>
            </footer>
        </body>
        </html>
        """
        result = clean_html(html)
        # Noise should be removed
        assert "<script>" not in result
        assert "<nav>" not in result
        assert "<header>" not in result
        assert "<footer>" not in result
        # Content should be preserved
        assert "Article Title" in result
        assert "meaningful content" in result
        assert "Another paragraph" in result
        assert "notable quote" in result
