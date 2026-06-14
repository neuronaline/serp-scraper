"""Tests for content compression module."""

import pytest

from serp.compression import (
    CompressionMeta,
    compress_content,
)


class TestCompressionMeta:
    """CompressionMeta is a data container."""

    def test_creation(self):
        meta = CompressionMeta(
            original_length=10000, compressed_length=4500,
            truncated_chars=5500, was_truncated=True,
        )
        assert meta.original_length == 10000
        assert meta.compressed_length == 4500
        assert meta.truncated_chars == 5500
        assert meta.was_truncated is True


class TestCompressContent:
    """Tests for compress_content function."""

    def test_below_threshold_unchanged(self):
        content = "Short"
        result, meta = compress_content(content, threshold=10000)
        assert result == content
        assert meta.was_truncated is False
        assert meta.truncated_chars == 0

    def test_exactly_at_threshold_unchanged(self):
        content = "A" * 10000
        result, meta = compress_content(content, threshold=10000)
        assert meta.was_truncated is False
        assert result == content

    def test_above_threshold_truncated_with_marker(self):
        content = "A" * 20000
        result, meta = compress_content(content, threshold=10000)
        assert meta.was_truncated is True
        assert meta.original_length == 20000
        assert meta.compressed_length == len(result)
        assert meta.truncated_chars > 0
        assert len(result) < len(content)
        assert "chars truncated" in result

    def test_head_and_tail_preserved(self):
        content = "HEAD" + "X" * 20000 + "TAIL"
        result, meta = compress_content(content, threshold=10000)
        assert result.startswith("HEAD")
        assert result.rstrip().endswith("TAIL")

    def test_empty_content(self):
        result, meta = compress_content("")
        assert result == ""
        assert meta.original_length == 0
        assert meta.was_truncated is False

    def test_custom_threshold(self):
        content = "A" * 5000
        result, meta = compress_content(content, threshold=1000)
        assert meta.was_truncated is True
        assert meta.truncated_chars > 0

    def test_middle_portion_can_be_empty(self):
        content = "A" * 20000
        result, meta = compress_content(
            content, threshold=10000,
            head_pct=0.7, middle_pct=0.0, tail_pct=0.3,
        )
        assert meta.was_truncated is True
        assert "chars truncated" in result
