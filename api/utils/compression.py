"""Content compression utilities — re-exported from the core ``serp`` library.

This module re-exports ``CompressionMeta`` and ``compress_content`` from
``serp.compression`` for backward compatibility with code that imports from
``api.utils.compression``.

New code should import directly from ``serp``:

    >>> from serp import compress_content, CompressionMeta

"""

from serp.compression import CompressionMeta, compress_content  # noqa: F401

__all__ = [
    "CompressionMeta",
    "compress_content",
]
