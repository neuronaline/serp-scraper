"""Tests for the cleaning module."""

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

    def test_removes_noise_elements(self):
        """Script, style, noscript, iframe, nav, footer, header, aside are removed."""
        html = """
        <html><body>
            <script>alert('x')</script>
            <style>.x{}</style>
            <noscript>enable JS</noscript>
            <iframe src="ad.html"></iframe>
            <nav>Navigation</nav>
            <header>Header</header>
            <footer>Footer</footer>
            <aside>Sidebar</aside>
            <p>Visible content</p>
        </body></html>
        """
        result = clean_html(html)
        for removed in ["<script>", "<style>", "<noscript>", "<iframe", "<nav>", "<header>", "<footer>", "<aside>"]:
            assert removed not in result
        assert "Visible content" in result

    def test_removes_hidden_elements_and_comments(self):
        """Elements with hidden attr, display:none, visibility:hidden, and HTML comments removed."""
        html = """
        <html><body>
            <p class="visible">shown</p>
            <p hidden>hidden text</p>
            <div style="display:none">gone</div>
            <div style="visibility:hidden">invisible</div>
            <!-- comment -->
            <p>after comment</p>
        </body></html>
        """
        result = clean_html(html)
        assert "shown" in result
        assert "after comment" in result
        for removed in ["hidden text", "gone", "invisible", "<!--"]:
            assert removed not in result

    def test_preserves_content_elements(self):
        """Article, main, headings, paragraphs, tables, lists, code, links, images, figures preserved."""
        html = """
        <html><body>
            <article>
                <h1>Title</h1>
                <p>Paragraph</p>
                <blockquote>Quote</blockquote>
            </article>
            <main><h2>Section</h2><p>Main content</p></main>
            <table><tr><th>H</th></tr><tr><td>D</td></tr></table>
            <ul><li>Item 1</li></ul>
            <pre><code>print("hi")</code></pre>
            <a href="https://example.com">Link</a>
            <img src="photo.jpg" alt="A beautiful photo">
            <figure>
                <img src="chart.png" alt="Chart">
                <figcaption>Chart description</figcaption>
            </figure>
        </body></html>
        """
        result = clean_html(html)
        for preserved in ["Title", "Paragraph", "Quote", "Section", "Main content",
                          "<th>H</th>", "<td>D</td>", "Item 1", 'print("hi")',
                          "https://example.com", 'alt="A beautiful photo"',
                          "Chart description", "<figure>"]:
            assert preserved in result

    def test_removes_meta_and_link_tags(self):
        html = "<html><head><meta charset='UTF-8'><link rel='stylesheet' href='s.css'></head><body><p>Content</p></body></html>"
        result = clean_html(html)
        assert "<meta" not in result
        assert "<link" not in result
        assert "Content" in result


class TestCleanMarkdown:
    """Tests for clean_markdown function."""

    def test_whitespace_normalization(self):
        result = clean_markdown("Hello      world\n\n\n\nGoodbye")
        assert "Hello world" in result
        assert result.count("\n\n") <= 1

    def test_unicode_whitespace_replaced(self):
        result = clean_markdown("Hello\u00a0world\u200btest")
        assert "Hello world test" in result
        assert "\u00a0" not in result
        assert "\u200b" not in result

    def test_html_entities_decoded(self):
        result = clean_markdown("Hello &amp; goodbye &lt;world&gt;")
        assert "Hello & goodbye <world>" in result

    def test_preserves_code_block_indentation(self):
        md = "```python\ndef hello():\n    print(\"Hello\")\n```"
        result = clean_markdown(md)
        assert 'print("Hello")' in result
        assert "    print" in result

    def test_preserves_inline_code(self):
        result = clean_markdown("Use `print()` function")
        assert "`print()`" in result

    def test_trims_lines_and_strips_blank_edges(self):
        result = clean_markdown("\n\n\n  Hello world  \n\n\n")
        assert result == "Hello world"


class TestExtractMainContent:
    """Tests for extract_main_content priority: article > main > body."""

    def test_prefers_article_over_main(self):
        html = "<html><body><article><p>Article</p></article><main><p>Main</p></main></body></html>"
        result = extract_main_content(html)
        assert "Article" in result
        assert "Main" not in result

    def test_falls_back_to_main(self):
        html = "<html><body><nav>Nav</nav><main><p>Main</p></main></body></html>"
        result = extract_main_content(html)
        assert "Main" in result

    def test_falls_back_to_body(self):
        html = "<html><body><nav>Nav</nav><p>Body</p></body></html>"
        result = extract_main_content(html)
        assert "Body" in result


class TestValidateContent:
    """Tests for validate_content function."""

    def test_too_short_content_is_invalid(self):
        result = validate_content("Short", min_length=100)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_valid_content_passes(self):
        html = "<html><body><p>A paragraph with sufficient length to pass validation.</p><h1>H</h1></body></html>"
        result = validate_content(html, min_length=50)
        assert result.is_valid
        assert result.content_length >= 50

    def test_element_counts_tracked(self):
        html = "<html><body><p>A</p><p>B</p><h1>T</h1><h2>S</h2><table><tr><td>D</td></tr></table></body></html>"
        result = validate_content(html)
        assert result.element_counts["p"] >= 2
        assert result.element_counts["h1"] == 1
        assert result.element_counts["table"] == 1

    def test_paragraph_and_heading_warnings(self):
        html = "<html><body><p>Only one</p></body></html>"
        result = validate_content(html, min_paragraphs=2, min_headings=1)
        assert any("Few paragraphs" in w for w in result.warnings)
        assert any("Few headings" in w for w in result.warnings)

    def test_bom_and_encoding_detected(self):
        bom_result = validate_content("\ufeff<html><body><p>Content</p></body></html>")
        assert any("BOM" in w for w in bom_result.warnings)

        enc_result = validate_content("<html><body><p>Bad\ufffdcontent</p></body></html>")
        assert any("encoding" in w.lower() for w in enc_result.warnings)

    def test_empty_and_whitespace_invalid(self):
        assert not validate_content("").is_valid
        assert not validate_content("   \n\t  ").is_valid


class TestIntegration:
    """End-to-end cleaning pipeline."""

    def test_full_cleaning_pipeline(self):
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <script>analytics()</script>
            <style>body{margin:0}</style>
        </head>
        <body>
            <header><nav><a href="/">Home</a></nav></header>
            <main>
                <article>
                    <h1>Article Title</h1>
                    <p>Meaningful content describing the topic in detail.</p>
                    <p>Another paragraph with more content.</p>
                    <blockquote>A notable quote.</blockquote>
                </article>
            </main>
            <footer><p>&copy; 2024</p></footer>
        </body>
        </html>
        """
        result = clean_html(html)
        for removed in ["<script>", "<nav>", "<header>", "<footer>"]:
            assert removed not in result
        for kept in ["Article Title", "Meaningful content", "Another paragraph", "notable quote"]:
            assert kept in result
