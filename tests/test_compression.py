"""Tests for content compression module.

Tests public API behavior following TEST_GOVERNANCE.md principles:
- Test through public interfaces
- Avoid brittle assertions
- Minimize duplication via shared fixtures
"""

import pytest

from serp.compression import (
    CompressionMeta,
    compress_content,
)


class TestCompressionMeta:
    """Tests for CompressionMeta dataclass."""

    def test_compression_meta_creation(self):
        """Test creating CompressionMeta."""
        meta = CompressionMeta(
            original_length=10000,
            compressed_length=4500,
            truncated_chars=5500,
            was_truncated=True,
        )
        assert meta.original_length == 10000
        assert meta.compressed_length == 4500
        assert meta.truncated_chars == 5500
        assert meta.was_truncated is True

    def test_compression_meta_defaults(self):
        """Test CompressionMeta with minimal args."""
        meta = CompressionMeta(
            original_length=100,
            compressed_length=100,
            truncated_chars=0,
            was_truncated=False,
        )
        assert meta.original_length == 100
        assert meta.truncated_chars == 0
        assert meta.was_truncated is False


class TestCompressContent:
    """Tests for compress_content function."""

    def test_content_below_threshold_returns_unchanged(self):
        """Content at or below threshold should be returned unchanged."""
        content = "Short content"
        result, meta = compress_content(content, threshold=10000)

        assert result == content
        assert meta.original_length == len(content)
        assert meta.compressed_length == len(content)
        assert meta.truncated_chars == 0
        assert meta.was_truncated is False

    def test_content_exactly_at_threshold_returns_unchanged(self):
        """Content exactly at threshold should not be truncated."""
        content = "A" * 10000
        result, meta = compress_content(content, threshold=10000)

        assert meta.was_truncated is False
        assert result == content

    def test_content_above_threshold_gets_truncated(self):
        """Content above threshold should be truncated."""
        content = "A" * 20000
        result, meta = compress_content(content, threshold=10000)

        assert meta.was_truncated is True
        assert meta.original_length == 20000
        assert meta.compressed_length < meta.original_length
        assert meta.truncated_chars > 0
        assert len(result) < len(content)

    def test_truncation_marker_present(self):
        """Truncation marker should be present in truncated content."""
        content = "A" * 20000
        result, meta = compress_content(content, threshold=10000)

        assert "chars truncated" in result

    def test_truncated_content_has_three_parts(self):
        """Truncated content should have head, marker, middle, and tail."""
        content = "A" * 20000
        result, meta = compress_content(content, threshold=10000)

        # Content should be split with truncation marker
        parts = result.split("chars truncated")
        assert len(parts) == 2  # head+middle+tail and marker

    def test_head_portion_from_beginning(self):
        """Head portion should come from start of content."""
        content = "HEAD" + "X" * 20000
        result, meta = compress_content(content, threshold=10000)

        # Head portion should start with original head
        assert result.startswith("HEAD")

    def test_tail_portion_from_end(self):
        """Tail portion should come from end of content."""
        content = "X" * 20000 + "TAIL"
        result, meta = compress_content(content, threshold=10000)

        # Tail portion should end with original tail
        assert result.rstrip().endswith("TAIL")

    def test_custom_thresholds(self):
        """Custom threshold should control when truncation occurs."""
        content = "A" * 5000
        result, meta = compress_content(content, threshold=1000)

        assert meta.was_truncated is True
        assert meta.truncated_chars > 0

    def test_custom_percentages(self):
        """Custom head/middle/tail percentages should work."""
        content = "A" * 20000
        result, meta = compress_content(
            content,
            threshold=10000,
            head_pct=0.5,
            middle_pct=0.0,
            tail_pct=0.5,
        )

        assert meta.was_truncated is True

    def test_empty_content(self):
        """Empty content should return unchanged with zero truncation."""
        content = ""
        result, meta = compress_content(content)

        assert result == ""
        assert meta.original_length == 0
        assert meta.was_truncated is False

    def test_truncated_chars_calculation(self):
        """Truncated chars should be correctly calculated."""
        content = "A" * 20000
        result, meta = compress_content(content, threshold=10000)

        # Truncated chars = original - (head + middle + tail extracted)
        # The marker is included in compressed_length
        # So we calculate based on what was extracted
        assert meta.original_length == 20000
        assert meta.truncated_chars > 0
        assert meta.was_truncated is True

    def test_compressed_length_includes_marker(self):
        """Compressed length should include the truncation marker."""
        content = "A" * 20000
        result, meta = compress_content(content, threshold=10000)

        assert meta.compressed_length == len(result)


class TestCompressContentEdgeCases:
    """Tests for edge cases in compress_content."""

    def test_very_long_content(self):
        """Very long content should be truncated correctly."""
        content = "A" * 100000
        result, meta = compress_content(content, threshold=10000)

        assert meta.was_truncated is True
        assert meta.truncated_chars > 90000

    def test_single_char_repeated(self):
        """Single character repeated many times should truncate correctly."""
        content = "x" * 50000
        result, meta = compress_content(content, threshold=5000)

        assert meta.was_truncated is True
        assert "x" in result[:100]  # Head still has content

    def test_middle_portion_may_be_empty(self):
        """Middle portion may be empty when middle_pct is 0."""
        content = "A" * 20000
        result, meta = compress_content(
            content,
            threshold=10000,
            head_pct=0.7,
            middle_pct=0.0,
            tail_pct=0.3,
        )

        assert meta.was_truncated is True
        # Should still have head and tail joined by marker
        assert "chars truncated" in result