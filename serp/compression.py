"""Content compression utilities for long content truncation.

This module provides content compression/truncation functionality that can be
used both directly by library consumers and by the REST API.

Example:
    >>> from serp import compress_content, CompressionMeta
    >>>
    >>> content = "A" * 20000
    >>> compressed, meta = compress_content(content)
    >>> print(f"Truncated: {meta.was_truncated}, removed {meta.truncated_chars} chars")
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CompressionMeta:
    """Metadata about the compression operation.

    Attributes:
        original_length: Original character count before compression
        compressed_length: Character count after compression
        truncated_chars: Number of characters removed
        was_truncated: Whether content was actually truncated (False if content
                       was already within the threshold)
    """

    original_length: int
    compressed_length: int
    truncated_chars: int
    was_truncated: bool


def compress_content(
    content: str,
    threshold: int = 10000,
    head_pct: float = 0.35,
    middle_pct: float = 0.15,
    tail_pct: float = 0.50,
) -> tuple[str, CompressionMeta]:
    """Compress long content by taking head, middle, and tail portions.

    For content longer than *threshold*, the function extracts three portions:
      - **Head**: the first ``head_pct`` fraction of the target length chars
      - **Middle**: ``middle_pct`` fraction taken from the middle of the document
      - **Tail**: the last ``tail_pct`` fraction of the target length chars

    The portions are joined with a truncation marker
    ``\\n\\n-- X,XXX chars truncated --\\n\\n``.

    Content at or below *threshold* is returned unchanged with
    ``was_truncated=False``.

    Args:
        content: The content string to compress.
        threshold: Character length threshold (default 10000). Content
                   shorter than this is returned unchanged.
        head_pct: Percentage of target length for head portion (default 0.35).
        middle_pct: Percentage of target length for middle portion (default 0.15).
        tail_pct: Percentage of target length for tail portion (default 0.50).

    Returns:
        A tuple of ``(compressed_content, CompressionMeta)``.
    """
    original_length = len(content)

    # If content is within threshold, return unchanged
    if original_length <= threshold:
        return content, CompressionMeta(
            original_length=original_length,
            compressed_length=original_length,
            truncated_chars=0,
            was_truncated=False,
        )

    # Calculate target compressed length (45% of threshold)
    target_length = int(threshold * 0.45)

    # Calculate sizes for each portion
    head_size = int(target_length * head_pct)
    middle_size = int(target_length * middle_pct)
    tail_size = int(target_length * tail_pct)

    # Extract portions
    head = content[:head_size]
    tail = content[-tail_size:]

    # Calculate middle bounds (actual middle of the document between head and tail)
    remaining_start = head_size
    remaining_end = original_length - tail_size
    middle_available = remaining_end - remaining_start
    middle_start = remaining_start + (middle_available - middle_size) // 2
    middle = content[middle_start:middle_start + middle_size] if middle_size > 0 and middle_available > 0 else ""

    # Calculate truncated characters
    total_extracted = head_size + len(middle) + tail_size
    truncated_chars = original_length - total_extracted

    # Build truncation marker
    marker = f"\n\n-- {truncated_chars:,} chars truncated --\n\n"

    # Combine parts: head + marker + middle + tail
    compressed = head + marker + middle + tail

    meta = CompressionMeta(
        original_length=original_length,
        compressed_length=len(compressed),
        truncated_chars=truncated_chars,
        was_truncated=True,
    )

    return compressed, meta
