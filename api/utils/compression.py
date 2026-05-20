"""Content compression utilities for long content truncation."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CompressionMeta:
    """Metadata about the compression operation."""

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

    Args:
        content: The content string to compress
        threshold: Character length threshold (default 10000). Content
                   shorter than this is returned unchanged.
        head_pct: Percentage of target length for head portion (default 0.35)
        middle_pct: Percentage of target length for middle portion (default 0.15)
        tail_pct: Percentage of target length for tail portion (default 0.50)

    Returns:
        A tuple of (compressed_content, CompressionMeta)
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

    # Build truncated marker
    marker = f"\n\n-- {truncated_chars:,} chars truncated --\n\n"

    # Combine parts: head + marker + middle + tail
    # Marker is placed before middle and tail to clearly indicate truncation
    compressed = head + marker + middle + tail

    meta = CompressionMeta(
        original_length=original_length,
        compressed_length=len(compressed),
        truncated_chars=truncated_chars,
        was_truncated=True,
    )

    return compressed, meta
